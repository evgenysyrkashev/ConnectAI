"""Building drafts."""

from __future__ import annotations

from app.core import compose, learning
from app.core.channel import channel_for, sms_text
from app.core.i18n import holiday_name
from app.core.intro_check import IntroOut, check_intro
from app.core.models import Campaign, Contact, DateItem, OutboundMessage
from app.core.priority import at_risk_views, item_priority, message_priority, weekly_priority
from app.core.prompts import IntroInput
from app.core.quiet import filter_items, message_skip
from app.core.templates import TEMPLATES
from app.core.wa_templates import wa_content_fitted
from app.kit import yext_day_to_str
from app.server.ports import Detection, TargetRow
from app.server.services import learning as learning_svc
from app.server.services.common import (
    Deps,
    dropped_key,
    effective_contact,
    live_holiday_dates,
    new_id,
    recently_asked,
    save_message,
)


# ----------------------------------------------------------------------------- intro
def intro_facts(
    template_id: str,
    lang: str,
    items: list[DateItem],
    has_history: bool,
    mode: str,
    evidence: list[str],
    event_fact: list[str] | None = None,
    extra: list[str] | None = None,
) -> list[str]:
    facts: list[str] = []
    if template_id == "holidays":
        facts.append("Upcoming special days: " + ", ".join(i.day_name for i in items))
        facts.append(f"Number of days with a suggestion: {sum(1 for i in items if i.suggested_hours is not None)}")
        if not has_history:
            facts.append("This is a new customer without earlier holiday hours")
    elif template_id == "event":
        facts += event_fact or []
    elif template_id == "stale_hours":
        types = {e["type"] for e in evidence}
        if "publisher_suggestion" in types:
            facts.append("Google users have suggested different opening hours for this business")
        if "review" in types:
            facts.append("Recent customer reviews mention that the opening hours have changed")
    elif template_id == "permission":
        facts += [
            f"We suggested opening hours for {len(items)} upcoming special days but did not get an answer",
            "Correct opening hours help customers find the business and avoid closed doors",
            "The owner is always informed after each change and can undo it",
        ]
    if mode == "inform":
        facts.append(
            "We already updated the hours because the owner gave us permission earlier; this email only informs"
        )
    facts += extra or []
    return facts


def generate_intro(deps: Deps, inp: IntroInput) -> tuple[str, str, str, str]:
    """(subject, intro, short, source). One retry with feedback, then the i18n fallback."""
    feedback: str | None = None
    for _ in range(2):
        try:
            raw = deps.llm.write_intro(inp.model_copy(update={"feedback": feedback}))
            out = IntroOut.model_validate(raw)
        except Exception as e:  # noqa: BLE001 - any LLM failure falls back
            feedback = f"invalid output ({type(e).__name__})"
            continue
        problems = check_intro(out, inp.language, inp.template_id)
        if not problems:
            return out.subject, out.intro, out.short, "llm"
        feedback = "; ".join(problems)
    tpl, lang = inp.template_id, inp.language
    return (
        compose.fallback_subject(tpl, lang),
        compose.fallback_intro(tpl, lang),
        compose.fallback_short(tpl, lang),
        "fallback",
    )


# ----------------------------------------------------------------------------- content
def build_content(
    deps: Deps, msg: OutboundMessage, contact: Contact, items: list[DateItem] | None = None
) -> OutboundMessage:
    """(Re)compute body + channel content from the current items/intro. Always computes the email body too."""
    cfg = deps.cfg
    if items is not None:
        msg = msg.model_copy(update={"items": items})
    lang = msg.language
    views = None
    if msg.kind == "dates" and msg.mode == "ask" and msg.items:
        best: tuple[int, DateItem] | None = None
        for it in msg.items:
            v = deps.findability.last_year_views(msg.entity_id, it.day_key, msg.country, it.date)
            if v is not None and (best is None or v > best[0]):
                best = (v, it)
        if best:
            views = compose.views_line(best[1], best[0], lang, cfg.views_line_min)
    if msg.kind == "permission":
        body = compose.compose_permission_body(msg, contact, lang, cfg.sender_name, msg.stats)
    else:
        body = compose.compose_body(msg, contact, lang, cfg.sender_name, views=views)
    upd: dict = {"body": body}
    if msg.channel == "whatsapp" and msg.kind != "permission":
        name, params, codes, dropped = wa_content_fitted(msg, contact, lang)
        upd.update(wa_template=name, wa_params=params, wa_payload_codes=codes, dropped_items=dropped)
    elif msg.channel == "sms" and msg.kind != "permission":
        text, dropped = sms_text(msg, contact, lang)
        upd.update(sms_text=text, dropped_items=dropped)
    else:
        upd["dropped_items"] = 0
    return msg.model_copy(update=upd)


# ----------------------------------------------------------------------------- items
def _hours_of(ent: dict) -> dict:
    return ent.get("hours") or {}


def _is_24_7(ent: dict) -> bool:
    h = _hours_of(ent)
    return all(
        yext_day_to_str(h.get(d, {})) == "00:00-23:59"
        for d in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
    )


def build_items(deps: Deps, tpl_id: str, params, ent: dict, contact: Contact) -> tuple[list[DateItem], str | None]:
    """Candidate items for a dates template and the FLAG evidence (or None). Quiet filters are applied by the caller."""
    cfg, sg, eid = deps.cfg, deps.suggestions, ent["meta"]["id"]
    lo, hi = params.date_from.isoformat(), params.date_to.isoformat()
    country = ent["meta"]["countryCode"]
    has_history = sg.has_history(eid)
    items: list[DateItem] = []
    flagged: str | None = None
    history = learning_svc.history_for(deps, eid)
    for row in sg.rows_for(eid):
        if not (lo <= row.date <= hi):
            continue
        if tpl_id == "holidays" and row.day_type == "LOCAL_EVENT":
            continue
        if tpl_id == "event" and row.day_key != "EVENT":
            continue
        det = sg.detect(row)
        if det.action == "FLAG":
            flagged = flagged or str(det.evidence.get("text") or det.basis or "flagged")
            continue
        det = _learn(history, row, det)
        if det.action == "SUGGEST":
            suggested = det.suggested_hours
        elif tpl_id == "holidays" and _is_ask_row(deps, row, det, has_history, ent):
            suggested = None
        else:
            continue
        info = sg.day_info(country, row.date)
        event = sg.event(row.event_id) if row.event_id else None
        views = deps.findability.est_views(eid, row.date, row.day_key)
        items.append(
            DateItem(
                date=row.date,
                day_key=row.day_key,
                day_name=holiday_name(country, row.day_key, row.date, contact.language, info, event),
                shown_hours=det.shown_hours,
                shown_source=det.shown_source,
                suggested_hours=suggested,
                basis=det.basis if suggested is not None else None,
                reason=compose.reason_for(det.basis, det.evidence, contact.language) if suggested is not None else "",
                event_id=row.event_id,
                est_views=views,
                priority=item_priority(views, det.confidence, suggested, det.shown_hours, cfg.closed_door_weight),
            )
        )
    return items, flagged


def _learn(history: list, row: TargetRow, det: Detection) -> Detection:
    """Let the owner's own earlier decisions for this day_key override the detector (app/core/learning.py)."""
    if det.basis == "ALREADY_ENTERED" or det.action == "FLAG" or row.day_key in ("EVENT", "SCHOOL_BREAK"):
        return det
    ov = learning.override(history, row.day_key, row.date, det.shown_hours, det.suggested_hours)
    if ov is None:
        return det
    sig = {
        "OWN_EDIT": "You changed our suggestion to these hours the last time",
        "OWN_APPROVED": "You approved these hours the last time",
        "OWN_DECLINE": "You declined this suggestion the last time",
    }[ov["basis"]]
    suggest = ov["action"] == "SUGGEST"
    return det.model_copy(
        update={
            # QUIET keeps the detector's suggestion so the dropped item can show what was declined
            "action": "NO_ACTION" if ov["action"] == "NO_ACTION" else "SUGGEST",
            "suggested_hours": ov["hours"] if suggest else (det.suggested_hours if ov["action"] == "QUIET" else None),
            "basis": ov["basis"],
            "evidence": ov["evidence"],
            "confidence": 0.95 if suggest else det.confidence,
            "signals": [sig, *det.signals],
        }
    )


def _is_ask_row(deps: Deps, row: TargetRow, det: Detection, has_history: bool, ent: dict) -> bool:
    """Ask items: new customer, MAJOR day, nothing already entered, enough peers changed hours."""
    if has_history or det.basis == "ALREADY_ENTERED":
        return False
    info = deps.suggestions.day_info(row.country, row.date) or {}
    # DECISION: EVE_MAJOR (Christmas Eve, NYE) counts as major; the plan's literal "MAJOR" would give FI-D0017 no ask items.
    if info.get("day_class") not in ("MAJOR", "EVE_MAJOR"):
        return False
    peers = deps.suggestions.peer_change_share(row.entity_id, row)
    if peers is None or peers[0] < deps.cfg.ask_min_change_share or peers[1] < deps.cfg.ask_min_peer_n:
        return False
    # DECISION: a 24/7 business has nothing to say about holidays (plan 12.3: "NO-D0015 is a 24/7 gym").
    return not _is_24_7(ent)


# ----------------------------------------------------------------------------- build one message
def build_message(
    deps: Deps, campaign_id: str, tpl_id: str, params, ent: dict, now_iso: str, today: str
) -> OutboundMessage:
    cfg, eid = deps.cfg, ent["meta"]["id"]
    tpl = TEMPLATES[tpl_id]
    contact = effective_contact(deps, eid)
    lang = contact.language if contact else "en"
    base = {
        "id": new_id(),
        "campaign_id": campaign_id,
        "entity_id": eid,
        "entity_name": ent.get("name", eid),
        "country": ent["meta"]["countryCode"],
        "template_id": tpl_id,
        "kind": tpl.kind,
        "language": lang,
        "mode": "ask",
        "contact_email": contact.email if contact else "",
        "to_email": None,
        "subject": "",
        "intro": "",
        "intro_source": "fallback",
        "body": "",
        "items": [],
        "weekly_shown": None,
        "status": "skipped",
        "created_at": now_iso,
    }
    if contact is None:
        return OutboundMessage(**base, skip_reason="no contact")
    base["contact_phone"] = contact.mobile
    skip_args = {
        "has_contact": True,
        "opted_out": contact.opted_out,
        "closed_in_yext": bool(ent.get("closed")),
        "flagged_evidence": None,
        "kept": [],
        "dropped": [],
    }
    evidence: list[dict] = []
    dropped: list = []
    kept: list[DateItem] = []
    weekly = None
    if tpl.kind == "dates":
        items, flagged = (
            ([], None) if (contact.opted_out or ent.get("closed")) else build_items(deps, tpl_id, params, ent, contact)
        )
        skip_args["flagged_evidence"] = flagged
        kept, dropped = filter_items(
            items,
            live_holiday_dates(ent),
            recently_asked(deps, eid, deps.now(), cfg.already_asked_days),
            today,
        )
        kept = sorted(kept, key=lambda i: i.date)  # DECISION: no cap
        skip_args.update(kept=kept, dropped=dropped)
    else:  # weekly
        evidence = deps.suggestions.stale_evidence(eid)
        h = _hours_of(ent)
        weekly = {
            d: yext_day_to_str(h.get(d, {}))
            for d in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
        }
        skip_args["kept"] = [None] if evidence else []  # type: ignore[list-item]
    skip = message_skip(**skip_args)
    if skip:
        code, reason = skip
        msg = OutboundMessage(**base, skip_reason=reason)
        deps.store.set_state(
            dropped_key(msg.id), {"skip_code": code, "dropped": [{"date": i.date, "code": c} for i, c in dropped]}
        )
        return msg
    mode = (
        "inform"
        if (
            tpl.kind == "dates"
            and contact.standing_permission
            and kept
            and all(i.suggested_hours is not None for i in kept)
        )
        else "ask"
    )
    channel = channel_for(contact, set(cfg.channels_enabled))
    event_fact: list[str] = []
    if tpl_id == "event" and kept:
        ev = deps.suggestions.event(kept[0].event_id) if kept[0].event_id else None
        if ev:
            names = ev.get("name") or {}
            att = round((ev.get("x_expected_attendance") or 0) / 100.0) * 100
            event_fact = [
                f"Event nearby: {names.get(lang) or names.get('en', '')}",
                f"Venue: {(ev.get('location', {}).get('name') or {}).get('en', '')}",
                f"Expected attendance: about {att}",
            ]
    inp = IntroInput(
        template_id=tpl_id,  # type: ignore[arg-type]
        language=lang,  # type: ignore[arg-type]
        business_name=ent.get("name", eid),
        first_name=contact.first_name,
        facts=intro_facts(tpl_id, lang, kept, deps.suggestions.has_history(eid), mode, evidence, event_fact),
        tone=tpl.tone,
        goal=tpl.goal,
        sender_name=cfg.sender_name,
    )
    subject, intro, short, source = generate_intro(deps, inp)
    prio = message_priority(kept) if tpl.kind == "dates" else weekly_priority(deps.findability.recent_mean(eid))
    msg = OutboundMessage(
        **{
            **base,
            "mode": mode,
            "subject": subject,
            "intro": intro,
            "intro_source": source,
            "items": kept,
            "weekly_shown": weekly,
            "status": "draft",
            "channel": channel,
            "short": short,
            "priority": prio,
            "at_risk_views": at_risk_views(kept),
        }
    )
    msg = build_content(deps, msg, contact)
    deps.store.set_state(
        dropped_key(msg.id), {"skip_code": None, "dropped": [{"date": i.date, "code": c} for i, c in dropped]}
    )
    return msg


def create_campaign(deps: Deps, template_id: str, params: dict, entity_ids: list[str], operator: str) -> Campaign:
    cfg = deps.cfg
    if template_id not in TEMPLATES or not TEMPLATES[template_id].selectable:
        raise ValueError(f"Template {template_id!r} cannot be used for a campaign")
    tpl = TEMPLATES[template_id]
    p = tpl.params_model.model_validate(params or {})
    if len(entity_ids) > cfg.max_messages_per_campaign:
        raise ValueError(f"At most {cfg.max_messages_per_campaign} businesses per campaign")
    now_iso, today = deps.now_iso(), deps.today()
    campaign = Campaign(
        id=new_id(),
        template_id=template_id,
        params=p.model_dump(mode="json"),  # type: ignore[arg-type]
        entity_ids=list(entity_ids),
        created_by=operator,
        created_at=now_iso,
        status="draft",
    )
    deps.store.create_campaign(campaign)
    ents = {e["meta"]["id"]: e for e in deps.yext.list_entities(list(entity_ids))}
    for eid in entity_ids:
        ent = ents.get(eid)
        if ent is None:
            continue
        deps.store.create_message(build_message(deps, campaign.id, template_id, p, ent, now_iso, today))
    return campaign


def pick_template(deps: Deps, ent: dict) -> str:
    """The template that fits what we found for this business: a nearby event, then special days, then stale weekly hours.

    Falls back to "holidays" so the card shows why the business would stay quiet.
    """
    eid = ent["meta"]["id"]
    contact = effective_contact(deps, eid)
    if contact is None or contact.opted_out or ent.get("closed"):
        return "holidays"
    for tpl_id in ("event", "holidays"):
        if views_at_risk(deps, tpl_id, TEMPLATES[tpl_id].params_model(), ent) > 0:
            return tpl_id
    if deps.suggestions.stale_evidence(eid):
        return "stale_hours"
    return "holidays"


def create_for_business(deps: Deps, entity_id: str, operator: str) -> tuple[Campaign, OutboundMessage | None]:
    """One message for one business (the business card). A campaign of one keeps the data model unchanged."""
    try:
        ent = deps.yext.get_entity(entity_id)
    except Exception:  # noqa: BLE001
        raise ValueError("Unknown business") from None
    campaign = create_campaign(deps, pick_template(deps, ent), {}, [entity_id], operator)
    msgs = deps.store.list_messages(campaign.id)
    return campaign, (msgs[0] if msgs else None)


# ----------------------------------------------------------------------------- draft editing
def _draft(deps: Deps, mid: str) -> OutboundMessage:
    m = deps.store.get_message(mid)
    if m is None or m.status != "draft":
        raise ValueError("Only drafts can be edited")
    return m


def regenerate(deps: Deps, mid: str) -> OutboundMessage:
    m = _draft(deps, mid)
    contact = effective_contact(deps, m.entity_id)
    tpl = TEMPLATES[m.template_id]
    inp = IntroInput(
        template_id=m.template_id,
        language=m.language,
        business_name=m.entity_name,
        first_name=contact.first_name if contact else "",
        facts=intro_facts(m.template_id, m.language, m.items, True, m.mode, []),
        tone=tpl.tone,
        goal=tpl.goal,
        sender_name=deps.cfg.sender_name,
    )
    subject, intro, short, source = generate_intro(deps, inp)
    m = m.model_copy(update={"subject": subject, "intro": intro, "short": short, "intro_source": source})
    m = build_content(deps, m, contact)
    save_message(deps, m)
    return m


def edit_intro(deps: Deps, mid: str, subject: str, intro: str) -> OutboundMessage:
    m = _draft(deps, mid)
    contact = effective_contact(deps, m.entity_id)
    problems = check_intro(
        IntroOut(subject=subject, intro=intro, short=m.short or compose.fallback_short(m.template_id, m.language)),
        m.language,
        m.template_id,
    )
    if problems:
        raise ValueError("; ".join(problems))
    m = build_content(
        deps, m.model_copy(update={"subject": subject, "intro": intro, "intro_source": "operator"}), contact
    )
    save_message(deps, m)
    return m


def change_channel(deps: Deps, mid: str, channel: str) -> OutboundMessage:
    m = _draft(deps, mid)
    contact = effective_contact(deps, m.entity_id)
    m = build_content(deps, m.model_copy(update={"channel": channel}), contact)
    save_message(deps, m)
    return m


# ----------------------------------------------------------------------------- selection helper
def views_at_risk(deps: Deps, tpl_id: str, params, ent: dict) -> int:
    """Sum of est_views over SUGGEST rows that would survive the stay-quiet rules; 0 if the business would be skipped."""
    eid = ent["meta"]["id"]
    contact = effective_contact(deps, eid)
    if contact is None or contact.opted_out or ent.get("closed"):
        return 0
    items, flagged = build_items(deps, tpl_id, params, ent, contact)
    if flagged is not None:
        return 0
    kept, _ = filter_items(
        items, live_holiday_dates(ent), recently_asked(deps, eid, deps.now(), deps.cfg.already_asked_days), deps.today()
    )
    return at_risk_views(kept)


def top_by_views_at_risk(deps: Deps, tpl_id: str, params: dict, entity_ids: list[str], n: int) -> list[tuple[str, int]]:
    """'Select top N by views at risk': descending; businesses that would stay quiet are excluded."""
    p = TEMPLATES[tpl_id].params_model.model_validate(params or {})
    ents = {e["meta"]["id"]: e for e in deps.yext.list_entities(list(entity_ids))}
    scored = [(eid, views_at_risk(deps, tpl_id, p, ents[eid])) for eid in entity_ids if eid in ents]
    return sorted(((e, v) for e, v in scored if v > 0), key=lambda x: -x[1])[:n]
