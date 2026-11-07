"""Simulated SMS replies."""

from __future__ import annotations

import uuid

from app.core.channel import digits
from app.core.models import Reply, ReplyChecks
from app.server.services import sync
from app.server.services.common import Deps, error_problem


def process_sms(deps: Deps, phone: str, text: str) -> Reply | None:
    pd = digits(phone)
    deps.store.append_sms(
        {
            "id": f"sms-in-{uuid.uuid4().hex[:12]}",
            "direction": "in",
            "phone": phone,
            "text": text,
            "at": deps.now_iso(),
            "message_id": None,
        }
    )
    rid = f"sms-{uuid.uuid4().hex[:12]}"
    reply = sync.new_reply(deps, rid, source="sms", sender=pd, text=text)
    deps.store.create_reply_if_absent(reply)
    try:
        open_msgs = deps.store.find_open_messages_by_phone(pd, "sms")
        if not open_msgs:
            deps.store.update_reply(rid, status="unmatched", problems=["No open SMS message for this number"])
        elif len(open_msgs) > 1:
            deps.store.update_reply(rid, status="needs_review", problems=["Several open messages for this phone"])
        else:
            message = open_msgs[0]
            checks = ReplyChecks(
                token_valid=False,
                matched_by="phone",
                sender_matches=True,
                auth_pass=True,
                auto_reply=False,
                expired=bool(message.expires_at) and deps.now_iso() > (message.expires_at or ""),
                duplicate=sync.is_duplicate(deps, message),
            )
            sync.evaluate_matched(deps, reply, message, checks, quick_words=True)
    except Exception as e:  # noqa: BLE001
        deps.store.update_reply(rid, status="error", problems=[error_problem(e)])
    return deps.store.get_reply(rid)
