"""Applying decisions to Yext, operator review actions, revert."""

from __future__ import annotations

import logging

from app.core.apply import compute_hours_update, resolve_decisions, revert_hours
from app.core.models import ParsedReply, Reply, YextChange
from app.core.parsed_reply import validate_parsed
from app.server.services import followups, learning, sandbox
from app.server.services.common import Deps, new_id

log = logging.getLogger("connect.review")


def _write(deps: Deps, message, decisions, parsed, *, actor: str, reply_id: str | None) -> YextChange | None:
    ent = deps.yext.get_entity(message.entity_id)
    new, before, after = compute_hours_update(ent.get("hours") or {}, message, decisions, parsed)
    if not after:
        return None
    deps.yext.put_hours(message.entity_id, new)
    change = YextChange(
        id=new_id(),
        entity_id=message.entity_id,
        message_id=message.id,
        reply_id=reply_id,
        actor=actor,
        before=before,
        after=after,
        created_at=deps.now_iso(),
    )
    deps.store.create_change(change)
    sandbox.mirror(deps, change)
    return change


def supersede_sibling(deps: Deps, message) -> None:
    """After an applied reply, the escalation sibling's later replies count as duplicates."""
    for sib in (message.escalated_to, message.escalated_from):
        if sib:
            deps.store.update_message(sib, superseded_by=message.id)


def apply_decisions(deps: Deps, reply: Reply, actor: str) -> Reply:
    message = deps.store.get_message(reply.message_id)
    assert message is not None
    change = _write(deps, message, reply.decisions, reply.parsed, actor=actor, reply_id=reply.id)
    learning.record(deps, message, reply.decisions)  # the owner's decisions shape the next suggestions
    deps.store.update_reply(
        reply.id, status="applied", change_id=change.id if change else None, decided_by=actor, problems=[]
    )
    supersede_sibling(deps, message)
    fresh = deps.store.get_reply(reply.id)
    assert fresh is not None
    if deps.cfg.send_followups and fresh.source != "simulator":
        followups.send_for(deps, fresh)
    return deps.store.get_reply(reply.id) or fresh


def apply_items(deps: Deps, message, actor: str) -> YextChange | None:
    """Inform mode / permission grant: apply every suggestion of the message."""
    parsed = ParsedReply(intent="approve", summary="apply suggestions", confidence=1.0)
    message = message.model_copy(update={"kind": "dates"})  # a permission request carries dates items too
    return _write(deps, message, resolve_decisions(parsed, message), parsed, actor=actor, reply_id=None)


def approve_review(deps: Deps, reply_id: str, operator: str) -> Reply:
    reply = deps.store.get_reply(reply_id)
    if reply is None or reply.status != "needs_review":
        raise ValueError("Only replies in review can be approved")
    message = deps.store.get_message(reply.message_id) if reply.message_id else None
    if message is None or reply.parsed is None or reply.parsed.intent == "unclear":
        raise ValueError("Nothing to apply: the answer is unclear or unmatched")
    problems = validate_parsed(reply.parsed, reply.decisions, message)
    if problems:
        raise ValueError("; ".join(problems))
    if message.kind == "permission":
        from app.server.services import permission

        return permission.apply_permission_answer(deps, reply, message, actor=operator)
    return apply_decisions(deps, reply, actor=operator)


def reject_review(deps: Deps, reply_id: str, operator: str) -> Reply:
    reply = deps.store.get_reply(reply_id)
    if reply is None:
        raise ValueError("Unknown reply")
    deps.store.update_reply(reply_id, status="rejected", decided_by=operator)
    return deps.store.get_reply(reply_id)  # type: ignore[return-value]


def retry(deps: Deps, reply_id: str) -> Reply:
    from app.server.services import sync

    deps.store.update_reply(reply_id, status="processing", problems=[])
    sync.evaluate_safely(deps, reply_id)
    return deps.store.get_reply(reply_id)  # type: ignore[return-value]


def revert(deps: Deps, change_id: str, operator: str) -> YextChange:
    ch = deps.store.get_change(change_id)
    if ch is None or ch.reverted_at:
        raise ValueError("Change not found or already reverted")
    ent = deps.yext.get_entity(ch.entity_id)
    hours = revert_hours(ent.get("hours") or {}, ch)
    deps.yext.put_hours(ch.entity_id, hours)
    new = YextChange(
        id=new_id(),
        entity_id=ch.entity_id,
        message_id=ch.message_id,
        reply_id=ch.reply_id,
        actor=operator,
        before=ch.after,
        after=ch.before,
        created_at=deps.now_iso(),
        revert_of=ch.id,
    )
    deps.store.create_change(new)
    sandbox.mirror(deps, new)
    deps.store.update_change(ch.id, reverted_at=deps.now_iso())
    return new
