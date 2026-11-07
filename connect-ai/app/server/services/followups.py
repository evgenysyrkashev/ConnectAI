"""Confirmation messages on the channel the owner used."""

from __future__ import annotations

import logging
from datetime import date

from app.core import compose
from app.core.allowlist import is_allowed
from app.core.channel import digits, phone_allowed
from app.core.i18n import TEXT, WEEKDAY_SHORT, fmt_date, fmt_hours, weekday_short
from app.core.models import WEEKDAYS, OutboundMessage, Reply, YextChange
from app.core.wa_templates import updated_params
from app.kit import yext_day_to_str
from app.server.ports import OutgoingMail, OutsideWindow
from app.server.services.common import Deps, effective_contact, get_permission, token_for, tokenized_reply_to

log = logging.getLogger("connect.followups")


def applied_pairs(deps: Deps, message: OutboundMessage, change: YextChange) -> tuple[list[tuple[str, str]], bool]:
    """[(date|weekday, hours string)] from a change's `after`, and whether it is a weekly change."""
    after = change.after
    if "holidayHours" in after:
        regular: dict = {}
        out = []
        for d, item in sorted(after["holidayHours"].items()):
            if item.get("isRegularHours"):
                if not regular:
                    regular = deps.yext.get_entity(message.entity_id).get("hours") or {}
                hours = yext_day_to_str(regular.get(WEEKDAYS[date.fromisoformat(d).weekday()], {}))
            else:
                hours = yext_day_to_str(item)
            out.append((d, hours))
        return out, False
    return [(day, yext_day_to_str(after[day])) for day in WEEKDAYS if day in after], True


def _oneline(pairs: list[tuple[str, str]], lang: str, weekly: bool) -> str:
    parts = []
    for label, hours in pairs:
        if weekly:
            parts.append(f"{WEEKDAY_SHORT[lang][WEEKDAYS.index(label)]} {fmt_hours(hours, lang)}")
        else:
            parts.append(f"{weekday_short(label, lang)} {fmt_date(label, lang)} {fmt_hours(hours, lang)}")
    return "; ".join(parts)


def send_followup(
    deps: Deps,
    message: OutboundMessage,
    kind: str,
    *,
    reply: Reply | None = None,
    applied: list[tuple[str, str]] | None = None,
    weekly: bool = False,
) -> bool:
    """kind: applied | declined | stopped | perm_granted | perm_declined | revoked. Returns True if something was sent."""
    cfg = deps.cfg
    contact = effective_contact(deps, message.entity_id)
    if contact is None:
        return False
    if contact.opted_out and kind != "stopped":  # only the one-off STOP confirmation may reach an opted-out contact
        return False
    lang, applied = message.language, applied or []
    try:
        listings = deps.yext.listings(message.entity_id) if kind in ("applied", "perm_granted") else []
    except Exception:  # noqa: BLE001
        listings = []
    if kind == "applied":
        perm = get_permission(deps, message.entity_id)
        offer = (
            cfg.offer_permission_in_followup
            and perm is None
            and message.mode != "inform"
            and message.kind != "permission"
        )
        text = compose.compose_followup_applied(
            contact,
            lang,
            applied,
            listings,
            deps.now(),
            weekly=weekly,
            offer_permission=offer,
            sender_name=cfg.sender_name,
        )
        sms = TEXT[lang]["sms_updated"].format(business=message.entity_name, applied=_oneline(applied, lang, weekly))
    elif kind == "declined":
        text = compose.compose_followup_declined(contact, lang)
        sms = TEXT[lang]["sms_declined"]
    elif kind == "stopped":
        text = compose.compose_followup_stopped(lang)
        sms = TEXT[lang]["sms_stopped"]
    elif kind == "perm_granted":
        text = compose.compose_followup_permission_granted(contact, lang, applied, listings)
        sms = TEXT[lang]["fu_perm_granted"] + " " + _oneline(applied, lang, False)
    elif kind == "perm_declined":
        text = sms = compose.compose_followup_permission_declined(lang)
    else:  # revoked
        text = sms = compose.compose_followup_revoked(lang)

    if message.channel == "email":
        if not message.to_email or not is_allowed(message.to_email, cfg.recipient_allowlist):
            return False
        if not deps.store.try_increment_daily_sends(deps.today(), cfg.daily_send_limit):
            return False
        deps.mail.send(
            OutgoingMail(
                to=message.to_email,
                reply_to=tokenized_reply_to(cfg, message.id),
                subject=TEXT[lang]["fu_subject_prefix"] + message.subject,
                text=text,
                thread_id=message.thread_id,
                in_reply_to=reply.rfc_message_id if reply else None,
            )
        )
        return True
    if message.channel == "whatsapp":
        if not message.to_phone or not phone_allowed(message.to_phone, cfg.phone_allowlist):
            return False
        if not deps.store.try_increment_daily_sends(deps.today(), cfg.daily_send_limit):
            return False
        to = digits(message.to_phone)
        try:
            deps.whatsapp.send_text(to, text)
        except OutsideWindow:
            if kind == "applied":
                deps.whatsapp.send_template(
                    to,
                    "connect_hours_updated",
                    lang,
                    updated_params(contact.first_name, message.entity_name, _oneline(applied, lang, weekly), lang),
                    [f"W:{token_for(cfg, message.id)}"],
                )
            else:
                return False
        return True
    # sms (simulated)
    if message.to_phone and deps.sms is not None:
        deps.sms.send(message.to_phone, sms, message.id)
        return True
    return False


def send_for(deps: Deps, reply: Reply) -> bool:
    """Follow-up for an applied or declined reply. Sets reply.followup_sent."""
    message = deps.store.get_message(reply.message_id) if reply.message_id else None
    if message is None:
        return False
    sent = False
    if reply.status == "applied" and reply.change_id:
        change = deps.store.get_change(reply.change_id)
        if change and change.after:
            pairs, weekly = applied_pairs(deps, message, change)
            sent = send_followup(deps, message, "applied", reply=reply, applied=pairs, weekly=weekly)
    elif reply.parsed is not None and reply.parsed.intent == "decline" and reply.status == "applied":
        sent = send_followup(deps, message, "declined", reply=reply)
    if sent:
        deps.store.update_reply(reply.id, followup_sent=True)
    return sent
