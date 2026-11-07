"""WhatsApp webhook events: statuses, button taps, free text."""

from __future__ import annotations

import logging
from datetime import timedelta

from app.core.apply import resolve_decisions
from app.core.channel import digits
from app.core.decide import decide
from app.core.i18n import TEXT
from app.core.models import DateDecision, ParsedReply, Reply, ReplyChecks
from app.core.parsed_reply import validate_parsed
from app.core.timeutil import iso
from app.core.token import verify_token
from app.server.ports import OutsideWindow
from app.server.services import review, sync
from app.server.services.common import Deps, error_problem

log = logging.getLogger("connect.whatsapp")


def process_payload(deps: Deps, payload: dict) -> None:
    """Statuses update delivery_status; messages go to process_whatsapp. Never raises for bad content."""
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") != "messages":
                continue
            value = change.get("value", {})
            for st in value.get("statuses", []):
                msg = deps.store.find_message_by_provider_id(st.get("id", ""))
                if msg is None:
                    continue
                upd: dict = {"delivery_status": st.get("status")}
                if st.get("status") == "failed":
                    errs = st.get("errors") or [{}]
                    upd.update(error=errs[0].get("title") or "WhatsApp delivery failed", escalate_at=deps.now_iso())
                deps.store.update_message(msg.id, **upd)
            for m in value.get("messages", []):
                try:
                    process_whatsapp(deps, m)
                except Exception as e:  # noqa: BLE001
                    log.warning("whatsapp message failed: %s", type(e).__name__)


def _say(deps: Deps, phone: str, text: str) -> None:
    try:
        deps.whatsapp.send_text(phone, text)
    except OutsideWindow:
        pass


def process_whatsapp(deps: Deps, m: dict) -> Reply | None:
    store = deps.store
    phone = str(m.get("from", ""))
    rid = "wa-" + str(m["id"])
    reply = sync.new_reply(deps, rid, source="whatsapp", sender=phone, text="")
    if not store.create_reply_if_absent(reply):
        return None
    store.set_state(f"wa-last-inbound-{phone}", {"at": deps.now_iso()})
    try:
        _handle(deps, rid, phone, m)
    except Exception as e:  # noqa: BLE001
        store.update_reply(rid, status="error", problems=[error_problem(e)])
    return store.get_reply(rid)


def _checks(deps: Deps, message, phone: str, matched_by: str, token_valid: bool) -> ReplyChecks:
    return ReplyChecks(
        token_valid=token_valid,
        matched_by=matched_by,  # type: ignore[arg-type]
        sender_matches=digits(phone) == message.to_phone_digits,
        auth_pass=True,
        auto_reply=False,
        expired=bool(message.expires_at) and deps.now_iso() > (message.expires_at or ""),
        duplicate=sync.is_duplicate(deps, message),
    )


def _handle(deps: Deps, rid: str, phone: str, m: dict) -> None:
    store, cfg = deps.store, deps.cfg
    mtype = m.get("type")
    if mtype in ("button", "interactive"):
        if mtype == "button":
            payload, label = m["button"].get("payload", ""), m["button"].get("text", "")
        else:
            br = m.get("interactive", {}).get("button_reply", {})
            payload, label = br.get("id", ""), br.get("title", "")
        code, _, token = payload.partition(":")
        mid = verify_token(token, cfg.token_hmac_key or "")
        message = store.get_message(mid) if mid else None
        store.update_reply(rid, cleaned_text="[button] " + label)
        if message is None:
            store.update_reply(rid, status="unmatched", problems=["Unknown or invalid button payload"])
            return
        checks = _checks(deps, message, phone, "button", True)
        store.update_reply(rid, message_id=message.id, entity_id=message.entity_id, checks=checks)
        if code in ("E", "X", "W"):
            store.set_state(
                f"wa-await-{phone}", {"message_id": message.id, "until": iso(deps.now() + timedelta(hours=24))}
            )
            key = "wa_prompt_edit_weekly" if message.kind == "weekly" else "wa_prompt_edit"
            _say(deps, phone, TEXT[message.language][key])
            store.update_reply(rid, status="ignored", decided_by="button:edit")
            return
        if message.kind == "weekly":
            parsed = ParsedReply(intent="approve", summary=f"button: {code}", confidence=1.0)
            decisions: list[DateDecision] = []
        elif code == "R":
            parsed = ParsedReply(
                intent="edit",
                summary=f"button: {code}",
                confidence=1.0,
                dates=[DateDecision(date=i.date, action="regular") for i in message.items],
            )
            decisions = list(parsed.dates or [])
        else:
            parsed = ParsedReply(
                intent="decline" if code == "D" else "approve", summary=f"button: {code}", confidence=1.0
            )
            decisions = resolve_decisions(parsed, message)
        problems = validate_parsed(parsed, decisions, message)
        decision = decide(checks, parsed, problems, message, cfg.auto_apply, cfg.min_confidence)
        store.update_reply(rid, parsed=parsed, decisions=decisions, problems=decision.problems)
        if decision.action == "apply":
            review.apply_decisions(deps, store.get_reply(rid), actor="auto")  # type: ignore[arg-type]
        else:
            store.update_reply(rid, status="needs_review")
        return
    if mtype == "text":
        text = m["text"]["body"]
        store.update_reply(rid, cleaned_text=text[:4000])
        message, matched_by = None, None
        ctx = (m.get("context") or {}).get("id")
        if ctx:
            message = store.find_message_by_provider_id(ctx)
            matched_by = "context" if message else None
        if message is None:
            aw = store.get_state(f"wa-await-{phone}")
            if aw and aw.get("until", "") > deps.now_iso() and aw.get("message_id"):
                message = store.get_message(aw["message_id"])
                matched_by = "phone" if message else None
                store.set_state(f"wa-await-{phone}", {})
        if message is None:
            open_msgs = store.find_open_messages_by_phone(digits(phone), "whatsapp")
            if not open_msgs:
                store.update_reply(rid, status="unmatched", problems=["No open WhatsApp message for this number"])
                return
            if len(open_msgs) > 1:
                store.update_reply(rid, status="needs_review", problems=["Several open messages for this phone"])
                return
            message, matched_by = open_msgs[0], "phone"
        checks = _checks(deps, message, phone, matched_by, False)  # type: ignore[arg-type]
        sync.evaluate_matched(deps, store.get_reply(rid), message, checks)  # type: ignore[arg-type]
        return
    # image, audio, sticker, reaction, location ...
    store.update_reply(rid, status="ignored", problems=[f"Unsupported message type: {mtype}"])
    flag = f"wa-unsupported-sent-{phone}"
    if not store.get_state(flag):
        store.set_state(flag, {"at": deps.now_iso()})
        lang = "en"
        open_msgs = store.find_open_messages_by_phone(digits(phone), "whatsapp")
        if open_msgs:
            lang = open_msgs[0].language
        _say(deps, phone, TEXT[lang]["wa_unsupported"])
