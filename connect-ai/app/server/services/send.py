"""Sending."""

from __future__ import annotations

import logging
from datetime import timedelta

from app.core.allowlist import is_allowed
from app.core.channel import digits, phone_allowed
from app.core.escalation import parse_chain, plan_escalation
from app.core.models import OutboundMessage
from app.core.quiet import filter_items
from app.core.timeutil import iso
from app.server.ports import OutgoingMail
from app.server.services import campaigns, review
from app.server.services.common import (
    Deps,
    demo_phone,
    dropped_key,
    effective_contact,
    live_holiday_dates,
    recently_asked,
    recipient_email,
    save_message,
    token_for,
    tokenized_reply_to,
)

log = logging.getLogger("connect.send")


def _fail(deps: Deps, mid: str, error: str) -> dict:
    deps.store.update_message(mid, status="failed", error=error)
    return {"id": mid, "status": "failed", "error": error}


def _skip(deps: Deps, mid: str, reason: str) -> dict:
    deps.store.update_message(mid, status="skipped", skip_reason=reason)
    return {"id": mid, "status": "skipped", "error": reason}


def recheck(deps: Deps, msg: OutboundMessage, contact, exempt: set[str] | None = None) -> OutboundMessage | None:
    """Re-run the stay-quiet filter with fresh Yext data. None = nothing left."""
    if msg.kind != "dates" or not msg.items:
        return msg
    ent = deps.yext.get_entity(msg.entity_id)
    asked = recently_asked(deps, msg.entity_id, deps.now(), deps.cfg.already_asked_days)
    kept, dropped = filter_items(msg.items, live_holiday_dates(ent), asked, deps.today(), exempt or set())
    if dropped:
        prev = deps.store.get_state(dropped_key(msg.id)) or {"dropped": []}
        prev["dropped"] += [{"date": i.date, "code": c} for i, c in dropped]
        deps.store.set_state(dropped_key(msg.id), prev)
    if not kept:
        return None
    if dropped:
        from app.core.priority import at_risk_views, message_priority

        msg = campaigns.build_content(deps, msg, contact, kept)
        msg = msg.model_copy(update={"priority": message_priority(kept), "at_risk_views": at_risk_views(kept)})
        save_message(deps, msg)
    return msg


def send_message(deps: Deps, mid: str, *, do_recheck: bool = True, exempt: set[str] | None = None) -> dict:
    """Steps 1-7 for one message. Status 'limit' means the daily limit stopped us."""
    cfg, store = deps.cfg, deps.store
    msg = store.get_message(mid)
    if msg is None or msg.status not in ("draft", "failed"):
        return {"id": mid, "status": "ignored", "error": None}
    contact = effective_contact(deps, msg.entity_id)
    if contact is None or contact.opted_out:
        return _skip(deps, mid, "opted out" if contact else "no contact")
    if do_recheck:
        newer = recheck(deps, msg, contact, exempt)
        if newer is None:
            return _skip(deps, mid, "no_longer_needed")
        msg = newer
    # recipient
    to_email = to_phone = None
    if msg.channel == "email":
        to_email = recipient_email(cfg, msg.entity_id, contact)
        if not is_allowed(to_email, cfg.recipient_allowlist):
            return _fail(deps, mid, "Recipient not in allowlist")
    elif msg.channel == "whatsapp":
        to_phone = demo_phone(cfg, msg.entity_id) or contact.mobile
        if not phone_allowed(to_phone, cfg.phone_allowlist):
            return _fail(deps, mid, "Recipient not in allowlist")
    else:
        to_phone = contact.mobile
    if not store.claim_message_for_sending(mid):
        return {"id": mid, "status": "ignored", "error": None}
    if not store.try_increment_daily_sends(deps.today(), cfg.daily_send_limit):
        store.update_message(mid, status="draft", error="Daily send limit reached")
        return {"id": mid, "status": "limit", "error": "Daily send limit reached"}
    auto_change_id = None
    try:
        if msg.mode == "inform":
            change = review.apply_items(deps, msg, actor="standing_permission")
            auto_change_id = change.id if change else None
        token = token_for(cfg, mid)
        provider_id, thread_id = None, None
        if msg.channel == "email":
            provider_id, thread_id = deps.mail.send(
                OutgoingMail(to=to_email, reply_to=tokenized_reply_to(cfg, mid), subject=msg.subject, text=msg.body)  # type: ignore[arg-type]
            )
        elif msg.channel == "whatsapp":
            provider_id = deps.whatsapp.send_template(
                digits(to_phone),
                msg.wa_template,
                msg.language,
                msg.wa_params,  # type: ignore[arg-type]
                [f"{c}:{token}" for c in msg.wa_payload_codes],
            )
        else:
            provider_id = deps.sms.send(to_phone, msg.sms_text or "", mid)  # type: ignore[arg-type]
    except Exception as e:  # noqa: BLE001
        log.warning("send failed for %s: %s", mid, type(e).__name__)
        return _fail(deps, mid, str(e) or type(e).__name__)
    now = deps.now()
    esc_at, basis = None, None
    if msg.mode != "inform" and msg.template_id != "permission":
        usual_h, src = deps.stats.usual_hours(msg.entity_id, msg.channel)
        tz = (deps.yext.get_entity(msg.entity_id).get("timezone")) or "Europe/Helsinki"
        at, basis = plan_escalation(
            now,
            msg.channel,
            usual_h,
            src,
            contact.best_contact_window,
            tz,
            parse_chain(cfg.escalation_chain),
            cfg.escalation_factor,
            cfg.min_escalation_hours,
            cfg.respect_contact_window,
        )
        esc_at = iso(at) if at else None
    store.update_message(
        mid,
        status="sent",
        error=None,
        to_email=to_email,
        to_phone=to_phone,
        to_phone_digits=digits(to_phone) if to_phone else None,
        provider_message_id=provider_id,
        thread_id=thread_id,
        sent_at=iso(now),
        expires_at=iso(now + timedelta(days=45)),
        escalate_at=esc_at,
        escalation_basis=basis,
        auto_change_id=auto_change_id,
    )
    return {"id": mid, "status": "sent", "error": None}


def send_campaign(deps: Deps, campaign_id: str, operator: str) -> list[dict]:
    store = deps.store
    msgs = [m for m in store.list_messages(campaign_id) if m.status in ("draft", "failed")]
    msgs.sort(key=lambda m: -m.priority)
    results: list[dict] = []
    for m in msgs:
        res = send_message(deps, m.id)
        results.append(res)
        if res["status"] == "limit":
            break
    all_msgs = store.list_messages(campaign_id)
    live = [m for m in all_msgs if m.status != "skipped"]
    store.update_campaign(
        campaign_id, status="sent" if live and all(m.status == "sent" for m in live) else "partially_sent"
    )
    return results


def send_one(deps: Deps, mid: str) -> dict:
    """Send a single draft from the business card; keeps the parent campaign's status in step."""
    res = send_message(deps, mid)
    msg = deps.store.get_message(mid)
    if msg is not None:
        live = [m for m in deps.store.list_messages(msg.campaign_id) if m.status != "skipped"]
        deps.store.update_campaign(
            msg.campaign_id,
            status="sent" if live and all(m.status == "sent" for m in live) else "partially_sent",
        )
    return res
