"""Operator UI: pages and HTMX actions."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates

from app.core.prompts import pick_locale
from app.core.quiet import filter_items
from app.core.templates import TEMPLATES
from app.core.timeutil import iso, parse_iso
from app.server.security import csrf_guard, operator_identity
from app.server.services import campaigns, escalation, review, scheduler, send
from app.server.services.common import (
    Deps,
    demo_phone,
    dropped_key,
    effective_contact,
    get_permission,
    live_holiday_dates,
    recently_asked,
    recipient_email,
)

HERE = Path(__file__).parent
MAX_BUSINESS_ROWS = 200
PANEL_COOKIE = "demo_panel"
PANEL_MAX_MESSAGES = 40
STEPS = ("Detect", "Suggest", "Contact", "Decide", "Apply")


def banners(deps: Deps) -> list[tuple[str, str]]:
    cfg = deps.cfg
    out: list[tuple[str, str]] = []
    if cfg.mail_mode == "fake":
        out.append(("warn", "FAKE MAIL – nothing is sent"))
    else:
        out.append(("danger", f"REAL EMAIL – recipients limited to: {'; '.join(cfg.recipient_allowlist)}"))
    out += [
        ("badge", f"LLM: {cfg.llm_mode}"),
        (
            "badge",
            ("Yext: embedded mock" if cfg.yext_mode == "embedded" else f"Yext: http {cfg.yext_base_url}")
            + (
                " + sandbox DIRECT"
                if cfg.yext_sandbox_direct
                else (" + sandbox mirror" if cfg.yext_sandbox_mirror else "")
            ),
        ),
        ("badge", "WhatsApp: fake" if cfg.wa_mode == "fake" else "WhatsApp: Meta (test number)"),
        ("badge", "SMS: simulated"),
        ("badge", f"AUTO_APPLY {'on' if cfg.auto_apply else 'off'}"),
    ]
    off = getattr(deps.clock, "offset_hours", None)
    if off and off() != 0:
        out.append(("warn", f"Clock: +{off():g} h (demo)"))
    return out


BASIS_LABELS = {
    "SHOPPING_CENTRE": "Shopping centre hours",
    "LAST_YEAR": "Same day last year",
    "USER_EDIT": "Owner's edit last year",
    "PEERS": "Similar businesses",
    "PATTERN": "Typical pattern",
    "PATTERN_HOURS": "Typical hours pattern",
    "CLOSED_SIGNALS": "Signs it is closed",
    "ALREADY_ENTERED": "Already entered",
    "LAST_EVENT": "Same event last time",
    "OWN_EDIT": "Owner edited before",
    "OWN_APPROVED": "Owner approved before",
    "OWN_DECLINE": "Owner declined before",
}


def day_label(key: str | None) -> str:
    """FATHERS_DAY -> 'Fathers Day' (display only)."""
    return (key or "").replace("_", " ").title()


def basis_label(key: str | None) -> str:
    return BASIS_LABELS.get(key or "", day_label(key))


def make_router(deps: Deps) -> APIRouter:
    cfg = deps.cfg
    templates = Jinja2Templates(directory=str(HERE / "templates"))
    templates.env.filters["day_label"] = day_label
    templates.env.filters["basis_label"] = basis_label
    r = APIRouter(dependencies=[Depends(operator_identity)])
    post = Depends(csrf_guard)

    def demo_panel(request: Request, focus: list[str]) -> dict | None:
        """The demo sidebar: None unless a simulator or a fake channel is on."""
        has = {
            "clock": cfg.enable_simulator,
            "simulate": cfg.enable_simulator,
            "mail": cfg.mail_mode == "fake",
            "wa": cfg.wa_mode == "fake",
        }
        if not any(has.values()):
            return None
        is_open = request.cookies.get(PANEL_COOKIE, "1") != "0"
        sent = []
        if is_open:
            for c in deps.store.list_campaigns(20):
                sent += [m for m in deps.store.list_messages(c.id) if m.status == "sent"]
            sent.sort(key=lambda m: m.sent_at or "", reverse=True)
            sent = sent[:PANEL_MAX_MESSAGES]
        wanted = set(focus)
        default = next((m.id for m in sent if m.id in wanted), "")
        return {"has": has, "open": is_open, "messages": sent, "default": default}

    def page(request: Request, name: str, focus: list[str] | None = None, **ctx) -> Response:
        needs = len(deps.store.list_replies("needs_review", 500))
        base = {
            "panel": demo_panel(request, focus or []),
            "banners": banners(deps),
            "needs_review": needs,
            "cfg": cfg,
            "simulator": cfg.enable_simulator,
            "fake_mail": cfg.mail_mode == "fake",
            "now": deps.now_iso(),
            "locale": pick_locale(request.headers.get("accept-language")),
        }
        return templates.TemplateResponse(request, name, {**base, **ctx})

    @r.post("/ui/demo-panel", dependencies=[post])
    def demo_panel_toggle(open_: str = Form("1", alias="open")) -> Response:
        resp = Response(status_code=204, headers={"HX-Refresh": "true"})
        resp.set_cookie(PANEL_COOKIE, "0" if open_ == "0" else "1", path="/", samesite="lax", httponly=True)
        return resp

    def refresh() -> Response:
        return Response(status_code=204, headers={"HX-Refresh": "true"})

    def reply_item(rep) -> dict:
        from app.core.apply import compute_hours_update
        from app.core.parsed_reply import validate_parsed

        msg = deps.store.get_message(rep.message_id) if rep.message_id else None
        proposed = None
        blocking: list[str] = []
        if msg and rep.parsed and rep.parsed.intent != "unclear" and msg.kind != "permission":
            blocking = validate_parsed(rep.parsed, rep.decisions, msg)
            if not blocking:
                ent = deps.yext.get_entity(msg.entity_id)
                _, before, after = compute_hours_update(ent.get("hours") or {}, msg, rep.decisions, rep.parsed)
                proposed = []
                for k, v in after.items():
                    if k == "holidayHours":
                        for d, item in sorted(v.items()):
                            proposed.append(
                                {"key": d, "before": json.dumps(before[k].get(d)), "after": json.dumps(item)}
                            )
                    else:
                        proposed.append({"key": k, "before": json.dumps(before.get(k)), "after": json.dumps(v)})
        truth = deps.store.get_state(f"simtruth-{rep.id}")
        match = None
        if truth and rep.decisions:
            tdates = truth["dates"]
            match = all(
                (d.date in tdates)
                and (
                    (tdates[d.date]["decision"] == "ACCEPTED" and d.action in ("accept", "regular"))
                    or (
                        tdates[d.date]["decision"] == "EDITED"
                        and d.action == "set"
                        and d.hours == tdates[d.date]["final_hours"]
                    )
                    or (tdates[d.date]["decision"] == "REJECTED" and d.action == "decline")
                )
                for d in rep.decisions
            )
        return {"r": rep, "msg": msg, "proposed": proposed, "blocking": blocking, "match": match}

    def message_card(m) -> dict:
        contact = effective_contact(deps, m.entity_id)
        if m.channel == "email":
            to = m.to_email or (recipient_email(cfg, m.entity_id, contact) if contact else "?")
        else:
            to = m.to_phone or (demo_phone(cfg, m.entity_id) or (contact.mobile if contact else "?"))
        return {
            "m": m,
            "to": to,
            "contact": contact,
            "dropped": (deps.store.get_state(dropped_key(m.id)) or {}).get("dropped", []),
            "note": (deps.store.get_state(f"escalation-note-{m.id}") or {}).get("reason"),
            "no_answer": deps.store.get_state(f"sim-noanswer-{m.id}") is not None,
            "replies": [reply_item(x) for x in deps.store.list_replies_for_message(m.id)],
        }

    def default_params() -> object:
        return TEMPLATES["holidays"].params_model()

    # ------------------------------------------------------------------ businesses
    def attention_rows() -> list[dict]:
        """Businesses needing a human: replies to review or in error, and messages that failed to send."""
        reasons: dict[str, list[str]] = {}

        def add(eid: str | None, why: str) -> None:
            if eid and why not in reasons.setdefault(eid, []):
                reasons[eid].append(why)

        for status, why in (("needs_review", "Reply needs review"), ("error", "Reply processing error")):
            for rep in deps.store.list_replies(status, 500):
                add(rep.entity_id, why)
        for camp in deps.store.list_campaigns(20):
            for m in deps.store.list_messages(camp.id):
                if m.status == "failed":
                    add(m.entity_id, "Send failed" + (f": {m.error}" if m.error else ""))
        if not reasons:
            return []
        ents = {e["meta"]["id"]: e for e in deps.yext.list_entities(list(reasons))}
        return sorted(
            (
                {"id": eid, "name": (ents.get(eid) or {}).get("name", ""), "reasons": why}
                for eid, why in reasons.items()
            ),
            key=lambda x: (-len(x["reasons"]), x["id"]),
        )

    def schedule_cell(eid: str, tz: str) -> dict:
        """Text for the "Scheduled" column: the real schedule if there is one, else when it would go out."""
        zone = ZoneInfo(tz)

        def local(iso_s: str) -> str:
            return parse_iso(iso_s).astimezone(zone).strftime("%a %d %b %H:%M")

        st = scheduler.schedule_state(deps, eid)
        if st and st["status"] == "sent":
            return {"state": "sent", "text": "sent " + local(st["sent_at"] or st["at"])}
        if st and st["status"] == "draft":
            return {"state": "scheduled", "text": local(st["at"])}
        if st:  # skipped by the quiet rules, or failed
            return {
                "state": "skipped",
                "text": f"skipped: {st['skip_reason']}" if st.get("skip_reason") else st["status"],
            }
        at = scheduler.planned_time(deps, eid)
        return {"state": "none", "text": local(iso(at)) if at else "no contact"}

    @r.get("/")
    def index(
        request: Request,
        split: str = "demo",
        country: Annotated[list[str], Query()] = [],  # noqa: B006 - FastAPI copies query defaults
        segment: Annotated[list[str], Query()] = [],  # noqa: B006
        city: Annotated[list[str], Query()] = [],  # noqa: B006
    ) -> Response:
        country = [c.upper() for c in country if c]
        ids = deps.suggestions.entity_ids(split)
        if country:
            ids = [i for i in ids if i[:2] in country]
        # City/segment live on the entity records, so load them for the whole (country-filtered) set.
        all_ents = {e["meta"]["id"]: e for e in deps.yext.list_entities(ids)}

        def seg_of(i: str) -> str:
            return str(all_ents[i].get("c_segment") or "")

        def city_of(i: str) -> str:
            return str((all_ents[i].get("address") or {}).get("city") or "")

        known = [i for i in ids if i in all_ents]
        # Faceted options: each list only offers values that exist given the *other* filters,
        # and selections that no longer exist (e.g. after changing country) are dropped.
        segment = [x for x in segment if x]
        city = [x for x in city if x]
        cities = sorted({city_of(i) for i in known if not segment or seg_of(i) in segment} - {""})
        city = [c for c in city if c in cities]
        segments = sorted({seg_of(i) for i in known if not city or city_of(i) in city} - {""})
        segment = [x for x in segment if x in segments]
        cities = sorted({city_of(i) for i in known if not segment or seg_of(i) in segment} - {""})
        if segment:
            ids = [i for i in known if seg_of(i) in segment]
        else:
            ids = known
        if city:
            ids = [i for i in ids if city_of(i) in city]
        shown_ids = ids[:MAX_BUSINESS_ROWS]
        # The "with suggestions" table is independent of the All-businesses filters.
        base_ids = deps.suggestions.entity_ids(split)[:MAX_BUSINESS_ROWS]
        ents = {i: all_ents[i] for i in shown_ids}
        missing = [i for i in base_ids if i not in all_ents]
        if missing:
            for e in deps.yext.list_entities(missing):
                all_ents[e["meta"]["id"]] = e
        for i in base_ids:
            if i in all_ents:
                ents[i] = all_ents[i]
        p = default_params()
        lo, hi = p.date_from.isoformat(), p.date_to.isoformat()  # type: ignore[attr-defined]
        review_ids = {x.entity_id for x in deps.store.list_replies("needs_review", 500) if x.entity_id}
        built: dict[str, dict] = {}

        def build_row(eid: str) -> dict | None:
            if eid in built:
                return built[eid]
            ent = ents.get(eid)
            if ent is None:
                return None
            c = effective_contact(deps, eid)
            dets = [deps.suggestions.detect(x) for x in deps.suggestions.rows_for(eid) if lo <= x.date <= hi]
            perm = get_permission(deps, eid)
            row = {
                "id": eid,
                "name": ent.get("name"),
                "city": (ent.get("address") or {}).get("city", ""),
                "segment": ent.get("c_segment", ""),
                "contact": c,
                "perm": perm.status if perm else None,
                "history": deps.suggestions.has_history(eid),
                "needs_review": eid in review_ids,
                "n_suggest": sum(d.action == "SUGGEST" for d in dets),
                "n_flag": sum(d.action == "FLAG" for d in dets),
                "views": campaigns.views_at_risk(deps, "holidays", p, ent),
            }
            if row["n_suggest"] > 0:
                row["sched"] = schedule_cell(eid, ent.get("timezone") or scheduler.DEFAULT_TZ)
            built[eid] = row
            return row

        rows = [x for x in (build_row(i) for i in shown_ids) if x]
        rows.sort(key=lambda x: -x["views"])
        base_rows = [x for x in (build_row(i) for i in base_ids) if x]
        base_rows.sort(key=lambda x: -x["views"])
        # Businesses the quiet rules skipped are not shown here; only ones with something to act on.
        suggested = [x for x in base_rows if x["n_suggest"] > 0 and x["sched"]["state"] not in ("skipped", "sent")]
        return page(
            request,
            "businesses.html",
            attention=attention_rows(),
            suggested=suggested,
            rows=rows,
            split=split,
            country=country,
            segment=segment,
            city=city,
            segments=segments,
            cities=cities,
            total=len(ids),
            capped=len(ids) > MAX_BUSINESS_ROWS,
        )

    @r.get("/businesses/{eid}")
    def business(request: Request, eid: str) -> Response:
        try:
            ent = deps.yext.get_entity(eid)
        except Exception:  # noqa: BLE001
            raise HTTPException(status_code=404, detail="Unknown business") from None
        contact = effective_contact(deps, eid)
        live = live_holiday_dates(ent)
        asked = recently_asked(deps, eid, deps.now(), cfg.already_asked_days)
        today = deps.today()
        rows = []
        for row in deps.suggestions.rows_for(eid):
            det = deps.suggestions.detect(row)
            if det.action == "FLAG":
                quiet = "flagged"
            elif det.action == "NO_ACTION":
                quiet = "ALREADY_ENTERED" if det.basis == "ALREADY_ENTERED" else "no evidence"
            elif row.date in live:
                quiet = "already_entered"
            elif row.date in asked:
                quiet = "already asked"
            elif row.date <= today:
                quiet = "date passed"
            elif det.suggested_hours == det.shown_hours:
                quiet = "no evidence"
            else:
                quiet = "included"
            rows.append(
                {
                    "row": row,
                    "det": det,
                    "quiet": quiet,
                    "evidence": json.dumps(det.evidence, ensure_ascii=False),
                }
            )
        messages = deps.store.list_messages_for_entity(eid, 20)
        # The card shows one live message: an open draft (or failed send) first, else the latest one.
        current = next((m for m in messages if m.status in ("draft", "failed")), messages[0] if messages else None)
        replies = [x for m in messages for x in deps.store.list_replies_for_message(m.id)]
        changes = deps.store.list_changes_for_entity(eid) if hasattr(deps.store, "list_changes_for_entity") else []
        last = messages[0] if messages else None
        done = {
            "Detect": bool(rows),
            "Suggest": any(x["det"].action == "SUGGEST" for x in rows),
            "Contact": bool(last and last.status == "sent"),
            "Decide": any(x.status in ("applied", "needs_review", "rejected") for x in replies),
            "Apply": any(x.status == "applied" for x in replies),
        }
        return page(
            request,
            "business.html",
            focus=[m.id for m in messages],
            ent=ent,
            eid=eid,
            contact=contact,
            rows=rows,
            messages=messages,
            current=message_card(current) if current else None,
            older=[message_card(m) for m in messages if current is None or m.id != current.id],
            can_create=current is None or current.status not in ("draft", "failed"),
            replies=replies,
            changes=changes,
            perm=get_permission(deps, eid),
            steps=[(s, done[s]) for s in STEPS],
            hours=ent.get("hours") or {},
        )

    # ------------------------------------------------------------------ business card: create / send one message
    @r.post("/ui/businesses/{eid}/messages", dependencies=[post])
    def business_message_create(eid: str, operator: str = Depends(operator_identity)) -> Response:
        try:
            campaigns.create_for_business(deps, eid, operator)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from None
        return refresh()

    @r.post("/ui/messages/{mid}/send", dependencies=[post])
    def message_send(mid: str) -> Response:
        if deps.store.get_message(mid) is None:
            raise HTTPException(status_code=404, detail="Unknown message")
        res = send.send_one(deps, mid)
        if res["status"] == "limit":
            raise HTTPException(status_code=400, detail=res["error"])
        return refresh()

    # ------------------------------------------------------------------ message actions
    def _draft_action(fn) -> Response:
        try:
            fn()
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from None
        return refresh()

    @r.post("/ui/messages/{mid}/regenerate", dependencies=[post])
    def regenerate(mid: str) -> Response:
        return _draft_action(lambda: campaigns.regenerate(deps, mid))

    @r.post("/ui/messages/{mid}/intro", dependencies=[post])
    def intro(mid: str, subject: str = Form(...), intro: str = Form(...)) -> Response:
        return _draft_action(lambda: campaigns.edit_intro(deps, mid, subject, intro))

    @r.post("/ui/messages/{mid}/channel", dependencies=[post])
    def channel(mid: str, channel: str = Form(...)) -> Response:
        if channel not in cfg.channels_enabled:
            raise HTTPException(status_code=400, detail="Channel not enabled")
        return _draft_action(lambda: campaigns.change_channel(deps, mid, channel))

    @r.post("/ui/messages/{mid}/escalation", dependencies=[post])
    def esc(mid: str, action: str = Form(...)) -> Response:
        m = deps.store.get_message(mid)
        if m is None:
            raise HTTPException(status_code=404)
        if action == "now":
            deps.store.update_message(mid, escalate_at=deps.now_iso())
            escalation.run_escalations(deps)
        elif action == "cancel":
            deps.store.update_message(mid, escalate_at=None)
            deps.store.set_state(f"escalation-note-{mid}", {"reason": "cancelled by operator", "at": deps.now_iso()})
        else:
            raise HTTPException(status_code=400, detail="Unknown action")
        return refresh()

    # ------------------------------------------------------------------ replies / changes
    def _review_action(fn) -> Response:
        try:
            fn()
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from None
        return refresh()

    @r.post("/ui/replies/{rid}/approve", dependencies=[post])
    def approve(rid: str, operator: str = Depends(operator_identity)) -> Response:
        return _review_action(lambda: review.approve_review(deps, rid, operator))

    @r.post("/ui/replies/{rid}/reject", dependencies=[post])
    def reject(rid: str, operator: str = Depends(operator_identity)) -> Response:
        return _review_action(lambda: review.reject_review(deps, rid, operator))

    @r.post("/ui/replies/{rid}/retry", dependencies=[post])
    def retry(rid: str) -> Response:
        return _review_action(lambda: review.retry(deps, rid))

    @r.post("/ui/replies/{rid}/translate", dependencies=[post])
    def translate_reply(request: Request, rid: str, to: str = Form("")) -> Response:
        """Inline translation of an owner's reply into the operator's locale. Nothing is stored or logged."""
        rep = deps.store.get_reply(rid)
        if rep is None:
            raise HTTPException(status_code=404, detail="Reply not found")
        target = pick_locale(to) if to else pick_locale(request.headers.get("accept-language"))
        try:
            text = deps.llm.translate(rep.cleaned_text, target)
        except Exception:  # noqa: BLE001 - never echo provider errors (they may contain the text)
            raise HTTPException(status_code=502, detail="Translation failed, try again") from None
        return templates.TemplateResponse(
            request, "partials/translation.html", {"text": text, "target": target, "rid": rid}
        )

    @r.post("/ui/changes/{chid}/revert", dependencies=[post])
    def revert(chid: str, operator: str = Depends(operator_identity)) -> Response:
        return _review_action(lambda: review.revert(deps, chid, operator))

    # ------------------------------------------------------------------ phone / outbox
    @r.get("/phone")
    def phone(request: Request, p: str = "") -> Response:
        log = deps.store.list_sms(None)
        phones = sorted({e["phone"] for e in log})
        sel = p or (phones[0] if phones else "")
        return page(request, "phone.html", phones=phones, sel=sel, thread=[e for e in log if e["phone"] == sel])

    @r.get("/outbox")
    def outbox(request: Request) -> Response:
        if cfg.mail_mode != "fake":
            raise HTTPException(status_code=404, detail="Outbox exists only with fake mail")
        return page(
            request,
            "outbox.html",
            mails=list(reversed(deps.mail.outbox)),
            wa=list(reversed(getattr(deps.whatsapp, "calls", []))),
        )

    return r


_ = (date, filter_items, json)
