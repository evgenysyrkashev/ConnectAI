"""Fallback when there is no answer."""

from __future__ import annotations

import logging
from datetime import date, timedelta

from app.core.escalation import parse_chain
from app.core.models import OutboundMessage
from app.core.priority import at_risk_views, message_priority
from app.core.prompts import IntroInput
from app.core.quiet import filter_items
from app.core.templates import TEMPLATES
from app.server.services import campaigns, send
from app.server.services.common import (
    Deps,
    effective_contact,
    get_permission,
    live_holiday_dates,
    new_id,
    recently_asked,
)

log = logging.getLogger("connect.escalation")
ANALYTICS = ["GOOGLE_SEARCH_VIEWS", "GOOGLE_MAP_VIEWS", "GOOGLE_PHONE_CALLS", "GOOGLE_CUSTOMER_ACTIONS"]


def _clear(deps: Deps, m: OutboundMessage, reason: str) -> None:
    deps.store.update_message(m.id, escalate_at=None)
    deps.store.set_state(f"escalation-note-{m.id}", {"reason": reason, "at": deps.now_iso()})


def run_escalations(deps: Deps) -> dict:
    escalated = skipped = 0
    for m in deps.store.list_due_escalations(deps.now_iso()):
        try:
            if _escalate_one(deps, m):
                escalated += 1
            else:
                skipped += 1
        except Exception as e:  # noqa: BLE001
            log.warning("escalation of %s failed: %s", m.id, type(e).__name__)
            skipped += 1
    return {"escalated": escalated, "skipped": skipped}


def _answered(deps: Deps, m: OutboundMessage) -> bool:
    for r in deps.store.list_replies_for_message(m.id):
        if r.status not in ("ignored", "unmatched") or (r.decided_by or "").startswith("button:edit"):
            return True
    return False


def _escalate_one(deps: Deps, m: OutboundMessage) -> bool:
    cfg = deps.cfg
    if _answered(deps, m):
        _clear(deps, m, "answered")
        return False
    contact = effective_contact(deps, m.entity_id)
    if contact is None or contact.opted_out:
        _clear(deps, m, "opted_out")
        return False
    target = parse_chain(cfg.escalation_chain).get(m.channel)
    if target is None:
        _clear(deps, m, "no_fallback")
        return False
    own_dates = {i.date for i in m.items}
    kept = m.items
    if m.kind == "dates":
        ent = deps.yext.get_entity(m.entity_id)
        kept, _ = filter_items(
            m.items,
            live_holiday_dates(ent),
            recently_asked(deps, m.entity_id, deps.now(), cfg.already_asked_days),
            deps.today(),
            own_dates,
        )
        if target == "permission":  # keep what is still pending, also asked-only items
            pass
        if not kept:
            _clear(deps, m, "no_longer_needed")
            return False
    if target == "permission":
        return _permission_request(deps, m, contact, kept, own_dates)
    return _fallback_copy(deps, m, contact, target, kept, own_dates)


def _new_message(deps: Deps, m: OutboundMessage, contact, **upd) -> OutboundMessage:
    base = m.model_copy(
        update={
            "id": new_id(),
            "status": "draft",
            "to_email": None,
            "to_phone": None,
            "to_phone_digits": None,
            "provider_message_id": None,
            "thread_id": None,
            "sent_at": None,
            "expires_at": None,
            "created_at": deps.now_iso(),
            "escalate_at": None,
            "escalation_basis": None,
            "escalated_to": None,
            "superseded_by": None,
            "error": None,
            "auto_change_id": None,
            "delivery_status": None,
            **upd,
        },
        deep=True,
    )
    return base


def _fallback_copy(deps: Deps, m: OutboundMessage, contact, target: str, kept, own_dates: set[str]) -> bool:
    tpl = TEMPLATES[m.template_id]
    fact = f"The owner did not answer our {'WhatsApp' if m.channel == 'whatsapp' else 'SMS'} message earlier; this email is a friendly reminder with the same request"
    inp = IntroInput(
        template_id=m.template_id,
        language=m.language,
        business_name=m.entity_name,
        first_name=contact.first_name,
        facts=campaigns.intro_facts(m.template_id, m.language, kept, True, m.mode, [], extra=[fact]),
        tone=tpl.tone,
        goal=tpl.goal,
        sender_name=deps.cfg.sender_name,
    )
    subject, intro, short, source = campaigns.generate_intro(deps, inp)
    new = _new_message(
        deps,
        m,
        contact,
        channel=target,
        escalated_from=m.id,
        subject=subject,
        intro=intro,
        short=short,
        intro_source=source,
        items=kept,
        priority=message_priority(kept),
        at_risk_views=at_risk_views(kept),
    )
    new = campaigns.build_content(deps, new, contact)
    deps.store.create_message(new)
    res = send.send_message(deps, new.id, exempt=own_dates)
    if res["status"] == "sent":
        deps.store.update_message(m.id, escalated_to=new.id, escalate_at=None)
        return True
    if res["status"] == "skipped" and res.get("error") == "no_longer_needed":
        _clear(deps, m, "no_longer_needed")
    elif res["status"] != "limit":
        _clear(deps, m, f"fallback not sent: {res.get('error')}")
    return False


def _permission_request(deps: Deps, m: OutboundMessage, contact, kept, own_dates: set[str]) -> bool:
    cfg = deps.cfg
    if m.kind != "dates" or m.template_id == "permission" or m.mode == "inform":
        _clear(deps, m, "not_applicable")
        return False
    perm = get_permission(deps, m.entity_id)
    if contact.standing_permission or (perm is not None and perm.status in ("declined", "revoked")):
        _clear(deps, m, "permission_state")
        return False
    asked = deps.store.get_state(f"permission-asked-{m.entity_id}")
    if asked and asked["at"] >= (deps.now() - timedelta(days=cfg.permission_ask_days)).strftime("%Y-%m-%dT%H:%M:%SZ"):
        _clear(deps, m, "asked_recently")
        return False
    tpl = TEMPLATES["permission"]
    inp = IntroInput(
        template_id="permission",
        language=m.language,
        business_name=m.entity_name,
        first_name=contact.first_name,
        facts=campaigns.intro_facts("permission", m.language, kept, True, "ask", []),
        tone=tpl.tone,
        goal=tpl.goal,
        sender_name=cfg.sender_name,
    )
    subject, intro, short, source = campaigns.generate_intro(deps, inp)
    stats = _stats(deps, m.entity_id, kept)
    new = _new_message(
        deps,
        m,
        contact,
        template_id="permission",
        kind="permission",
        mode="ask",
        channel="email",
        escalated_from=m.id,
        subject=subject,
        intro=intro,
        short=short,
        intro_source=source,
        items=kept,
        stats=stats,
        weekly_shown=None,
        priority=message_priority(kept),
        at_risk_views=at_risk_views(kept),
    )
    new = campaigns.build_content(deps, new, contact)
    deps.store.create_message(new)
    deps.store.set_state(f"permission-asked-{m.entity_id}", {"at": deps.now_iso()})
    res = send.send_message(deps, new.id, exempt=own_dates)
    if res["status"] == "sent":
        deps.store.update_message(m.id, escalated_to=new.id, escalate_at=None)
        return True
    deps.store.set_state(f"permission-asked-{m.entity_id}", {"at": "1970-01-01T00:00:00Z"})  # not actually asked
    if res["status"] == "skipped":
        _clear(deps, m, "no_longer_needed")
    elif res["status"] != "limit":
        _clear(deps, m, f"permission request not sent: {res.get('error')}")
    return False


def _stats(deps: Deps, eid: str, items) -> dict | None:
    """Last year's Google numbers for the same span; None if unavailable or under 50 views."""
    first, last = date.fromisoformat(items[0].date), date.fromisoformat(items[-1].date)
    start, end = first - timedelta(days=365), last - timedelta(days=365)
    if (end - start).days < 6:
        end = start + timedelta(days=6)
    try:
        r = deps.yext.analytics(eid, start.isoformat(), end.isoformat(), ANALYTICS)
    except Exception:  # noqa: BLE001
        return None
    views = int(r.get("GOOGLE_SEARCH_VIEWS", 0)) + int(r.get("GOOGLE_MAP_VIEWS", 0))
    if views < 50:
        return None
    return {
        "views": views,
        "calls": int(r.get("GOOGLE_PHONE_CALLS", 0)),
        "actions": int(r.get("GOOGLE_CUSTOMER_ACTIONS", 0)),
    }
