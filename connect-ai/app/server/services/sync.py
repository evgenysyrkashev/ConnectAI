"""Inbound processing: inbox sync, matching, checks, parse, decide, apply."""

from __future__ import annotations

import email
import email.policy
import logging
from datetime import timedelta
from email.message import EmailMessage
from email.utils import parseaddr

from app.core.apply import resolve_decisions
from app.core.decide import decide
from app.core.email_checks import auth_pass, is_auto_reply, parse_auth_results, same_mailbox
from app.core.models import OutboundMessage, ParsedReply, Reply, ReplyChecks
from app.core.parsed_reply import validate_parsed
from app.core.prompts import ParseInput, items_text, weekly_text
from app.core.reply_text import (
    extract_text,
    flag_suspicious,
    is_auto,
    is_manual,
    is_stop,
    quick_intent,
    strip_quoted,
    truncate,
)
from app.core.timeutil import iso
from app.core.token import extract_tokens, verify_token
from app.server.services import followups, permission, review
from app.server.services.common import Deps, error_problem, get_permission, set_permission

log = logging.getLogger("connect.sync")

HEADER_NAMES = (
    "to",
    "cc",
    "delivered-to",
    "x-original-to",
    "authentication-results",
    "auto-submitted",
    "precedence",
    "x-autoreply",
    "x-autorespond",
    "x-auto-response-suppress",
)


def sync_inbox(deps: Deps) -> dict:
    processed = errors = 0
    for pid in deps.mail.list_unprocessed(50):
        try:
            process_provider_message(deps, pid)
            processed += 1
        except Exception as e:  # noqa: BLE001
            errors += 1
            log.warning("inbox message %s failed: %s", pid, type(e).__name__)
    return {"processed": processed, "errors": errors}


def process_provider_message(deps: Deps, pid: str) -> None:
    try:
        raw = deps.mail.get_raw(pid)
        msg = email.message_from_bytes(raw, policy=email.policy.default)
        process_raw(deps, pid, msg, source="email")  # type: ignore[arg-type]
    finally:
        deps.mail.mark_processed(pid)  # always, so one bad email cannot block the queue


def new_reply(
    deps: Deps,
    rid: str,
    *,
    source: str,
    sender: str,
    text: str,
    subject: str = "",
    headers: dict[str, list[str]] | None = None,
    rfc_message_id: str | None = None,
    message_id: str | None = None,
    entity_id: str | None = None,
) -> Reply:
    now = deps.now()
    return Reply(
        id=rid,
        message_id=message_id,
        entity_id=entity_id,
        source=source,
        sender=sender,  # type: ignore[arg-type]
        subject=subject,
        received_at=iso(now),
        rfc_message_id=rfc_message_id,
        cleaned_text=truncate(text, 4000),
        headers=headers or {},
        status="processing",
        created_at=iso(now),
        expire_at=now + timedelta(days=90),
    )


def process_raw(deps: Deps, reply_id: str, msg: EmailMessage, source: str) -> Reply | None:
    sender = parseaddr(str(msg.get("From", "")))[1].lower()
    headers = {n: [str(v) for v in msg.get_all(n, [])] for n in HEADER_NAMES}
    text = truncate(strip_quoted(extract_text(msg)), 4000)
    reply = new_reply(
        deps,
        reply_id,
        source=source,
        sender=sender,
        text=text,
        subject=str(msg.get("Subject", "")),
        headers=headers,
        rfc_message_id=str(msg.get("Message-ID", "")) or None,
    )
    if not deps.store.create_reply_if_absent(reply):
        return None
    evaluate_safely(deps, reply_id)
    return deps.store.get_reply(reply_id)


def evaluate_safely(deps: Deps, reply_id: str) -> None:
    try:
        evaluate(deps, reply_id)
    except Exception as e:  # noqa: BLE001
        log.warning("reply %s failed: %s", reply_id, type(e).__name__)
        deps.store.update_reply(reply_id, status="error", problems=[error_problem(e)])


def evaluate(deps: Deps, reply_id: str) -> None:
    """Match an email-like reply using only its stored headers (so Retry works), then continue."""
    store, cfg = deps.store, deps.cfg
    reply = store.get_reply(reply_id)
    assert reply is not None
    h = reply.headers
    tokens = extract_tokens(h.get("to", []) + h.get("cc", []) + h.get("delivered-to", []) + h.get("x-original-to", []))
    message, matched_by = None, None
    for t in tokens:
        mid = verify_token(t, cfg.token_hmac_key or "")
        if mid:
            message = store.get_message(mid)
            matched_by = "token"
            if message:
                break
    if message is None and reply.source == "email":
        thread = deps.mail.get_thread_id(reply.id)
        if thread:
            message = store.find_message_by_thread(thread)
            matched_by = "thread" if message else None
    auto = is_auto_reply({k: v[0] for k, v in h.items() if v}, reply.sender)
    if auto:
        store.update_reply(
            reply_id, status="ignored", problems=["Auto-reply"], message_id=message.id if message else None
        )
        return
    if message is None:
        store.update_reply(reply_id, status="unmatched", problems=["No matching message"])
        return
    bypass = reply.source in ("simulator", "sms")
    checks = ReplyChecks(
        token_valid=matched_by == "token",
        matched_by=matched_by,  # type: ignore[arg-type]
        sender_matches=True
        if bypass
        else bool(message.to_email) and same_mailbox(reply.sender, message.to_email or ""),
        auth_pass=True if bypass else auth_pass(parse_auth_results(h.get("authentication-results", []))),
        auto_reply=False,
        expired=bool(message.expires_at) and deps.now_iso() > (message.expires_at or ""),
        duplicate=is_duplicate(deps, message),
    )
    evaluate_matched(deps, reply, message, checks)


def is_duplicate(deps: Deps, message: OutboundMessage) -> bool:
    if deps.store.has_applied_reply(message.id) or message.superseded_by:
        return True
    return any(sib and deps.store.has_applied_reply(sib) for sib in (message.escalated_from, message.escalated_to))


def parse_with_llm(deps: Deps, message: OutboundMessage, text: str) -> tuple[ParsedReply | None, list[str]]:
    inp = ParseInput(
        kind=message.kind,
        mode=message.mode,
        language=message.language,
        items_text=items_text(message.items),
        weekly_text=weekly_text(message.weekly_shown),
        cleaned_text=text,
    )
    for _ in range(2):
        try:
            return ParsedReply.model_validate(deps.llm.parse_reply(inp)), []
        except Exception:  # noqa: BLE001, S112
            continue
    return None, ["Could not parse reply"]


def evaluate_matched(
    deps: Deps, reply: Reply, message: OutboundMessage, checks: ReplyChecks, *, quick_words: bool = False
) -> None:
    """Everything after matching; shared by email, simulator, WhatsApp text/buttons and SMS."""
    store, cfg = deps.store, deps.cfg
    text = reply.cleaned_text
    store.update_reply(reply.id, message_id=message.id, entity_id=message.entity_id, checks=checks)
    reply = store.get_reply(reply.id)  # type: ignore[assignment]
    trusted = checks.sender_matches and checks.auth_pass
    # --- short-circuits (no LLM)
    if is_stop(text):
        if trusted:  # a spoofed From must not be able to opt a business out
            store.set_state(f"optout-{message.entity_id}", {"at": deps.now_iso()})
            perm = get_permission(deps, message.entity_id)
            if perm is not None and perm.status == "granted":  # STOP also revokes the permission
                set_permission(
                    deps, message.entity_id, perm.model_copy(update={"status": "revoked", "at": deps.now_iso()})
                )
            store.update_reply(reply.id, status="applied", decided_by="auto", problems=[])
            if cfg.send_followups:
                followups.send_followup(deps, message, "stopped", reply=reply)
                store.update_reply(reply.id, followup_sent=True)
        else:
            store.update_reply(
                reply.id,
                status="needs_review",
                problems=["STOP from a sender that does not match or failed authentication"],
            )
        return
    if is_manual(text) and trusted:
        permission.revoke(deps, message, reply=reply, evidence=text)
        return
    if is_auto(text) and trusted and get_permission(deps, message.entity_id) is None:
        permission.grant(
            deps, message, reply=reply, evidence=text, actor="auto", apply_pending=message.kind == "permission"
        )
        return
    # --- parse
    problems: list[str] = []
    parsed: ParsedReply | None = None
    quick = (
        quick_intent(text, permission=True)
        if message.kind == "permission"
        else (quick_intent(text) if (quick_words and message.kind == "dates") else None)
    )
    if quick:
        parsed = ParsedReply(intent=quick, summary="quick word", confidence=1.0)  # type: ignore[arg-type]
    else:
        parsed, problems = parse_with_llm(deps, message, text)
    if parsed is not None and message.kind == "permission" and parsed.intent == "edit":
        parsed = parsed.model_copy(update={"intent": "unclear"})
    decisions = resolve_decisions(parsed, message)
    problems += validate_parsed(parsed, decisions, message)
    if flag_suspicious(text):
        problems.append("Possible abusive content or injection attempt – review manually")
    decision = decide(checks, parsed, problems, message, cfg.auto_apply, cfg.min_confidence)
    store.update_reply(reply.id, parsed=parsed, decisions=decisions, problems=decision.problems)
    if decision.action != "apply":
        store.update_reply(reply.id, status="needs_review")
        return
    fresh = store.get_reply(reply.id)
    assert fresh is not None
    if message.kind == "permission":
        permission.apply_permission_answer(deps, fresh, message, actor="auto")
    else:
        review.apply_decisions(deps, fresh, actor="auto")
