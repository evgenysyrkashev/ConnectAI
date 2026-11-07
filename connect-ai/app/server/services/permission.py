"""Standing-permission handling."""

from __future__ import annotations

from app.core.models import Permission, Reply
from app.core.quiet import filter_items
from app.server.services import followups, review
from app.server.services.common import Deps, get_permission, live_holiday_dates, set_permission


def _chain(deps: Deps, message) -> list:
    """The permission message and every ancestor it escalated from."""
    out, cur = [message], message
    while cur.escalated_from:
        parent = deps.store.get_message(cur.escalated_from)
        if parent is None:
            break
        out.append(parent)
        cur = parent
    return out


def grant(
    deps: Deps, message, *, reply: Reply | None, evidence: str, actor: str, apply_pending: bool = True
) -> Reply | None:
    """Record consent, apply the pending items that still pass the quiet filter, send the confirmation."""
    prev = get_permission(deps, message.entity_id)
    now = deps.now_iso()
    set_permission(
        deps,
        message.entity_id,
        Permission(
            status="granted",
            at=now,
            message_id=message.id,
            reply_id=reply.id if reply else None,
            evidence_text=evidence[:300],
            asked_at=prev.asked_at if prev else None,
        ),
    )
    change = None
    pairs: list[tuple[str, str]] = []
    if apply_pending and message.items:
        ent = deps.yext.get_entity(message.entity_id)
        kept, _ = filter_items(message.items, live_holiday_dates(ent), set(), deps.today(), set())
        kept = [i for i in kept if i.suggested_hours is not None]
        if kept:
            change = review.apply_items(deps, message.model_copy(update={"items": kept}), actor="standing_permission")
            if change:
                change_obj = deps.store.get_change(change.id)
                pairs, _ = followups.applied_pairs(deps, message, change_obj)  # type: ignore[arg-type]
    for m in _chain(deps, message):
        if m.id != message.id:
            deps.store.update_message(m.id, superseded_by=message.id)
    if reply is not None:
        deps.store.update_reply(
            reply.id, status="applied", change_id=change.id if change else None, decided_by=actor, problems=[]
        )
        review.supersede_sibling(deps, message)
    if deps.cfg.send_followups and (reply is None or reply.source != "simulator"):
        followups.send_followup(deps, message, "perm_granted", reply=reply, applied=pairs)
        if reply is not None:
            deps.store.update_reply(reply.id, followup_sent=True)
    return deps.store.get_reply(reply.id) if reply else None


def decline(deps: Deps, message, *, reply: Reply, evidence: str, actor: str) -> Reply | None:
    prev = get_permission(deps, message.entity_id)
    set_permission(
        deps,
        message.entity_id,
        Permission(
            status="declined",
            at=deps.now_iso(),
            message_id=message.id,
            reply_id=reply.id,
            evidence_text=evidence[:300],
            asked_at=prev.asked_at if prev else deps.now_iso(),
        ),
    )
    deps.store.update_reply(reply.id, status="applied", decided_by=actor, problems=[])
    for m in _chain(deps, message):
        if m.id != message.id:
            deps.store.update_message(m.id, superseded_by=message.id)
    if deps.cfg.send_followups and reply.source != "simulator":
        followups.send_followup(deps, message, "perm_declined", reply=reply)
        deps.store.update_reply(reply.id, followup_sent=True)
    return deps.store.get_reply(reply.id)


def revoke(deps: Deps, message, *, reply: Reply, evidence: str, actor: str = "auto") -> None:
    prev = get_permission(deps, message.entity_id)
    set_permission(
        deps,
        message.entity_id,
        Permission(
            status="revoked",
            at=deps.now_iso(),
            message_id=message.id,
            reply_id=reply.id,
            evidence_text=evidence[:300],
            asked_at=prev.asked_at if prev else None,
        ),
    )
    deps.store.update_reply(reply.id, status="applied", decided_by=actor, problems=[])
    if deps.cfg.send_followups:
        followups.send_followup(deps, message, "revoked", reply=reply)
        deps.store.update_reply(reply.id, followup_sent=True)


def apply_permission_answer(deps: Deps, reply: Reply, message, *, actor: str) -> Reply:
    assert reply.parsed is not None
    text = reply.cleaned_text
    if reply.parsed.intent == "approve":
        out = grant(deps, message, reply=reply, evidence=text, actor=actor)
    else:
        out = decline(deps, message, reply=reply, evidence=text, actor=actor)
    return out or deps.store.get_reply(reply.id)  # type: ignore[return-value]
