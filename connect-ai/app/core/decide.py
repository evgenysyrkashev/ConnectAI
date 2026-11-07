"""Auto-apply decision. Pure."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.core.models import OutboundMessage, ParsedReply, ReplyChecks


class Decision(BaseModel):
    action: Literal["apply", "review"]
    problems: list[str] = []


def decide(
    checks: ReplyChecks,
    parsed: ParsedReply | None,
    problems: list[str],
    message: OutboundMessage,
    auto_apply: bool,
    min_confidence: float,
) -> Decision:
    p = list(problems)
    if not checks.sender_matches:
        p.append("Sender does not match the recipient mailbox")
    if not checks.auth_pass:
        p.append("Email failed DKIM/DMARC")
    if checks.expired:
        p.append("Reply arrived after the request expired")
    if checks.duplicate:
        p.append("This message already has an applied reply")
    if checks.matched_by == "thread":
        p.append("Matched by thread only (reply token missing)")
    if parsed is None:
        p.append("No parsed answer")
    else:
        if parsed.abusive:
            p.append("Model flagged the reply as abusive or instruction-injecting")
        if parsed.intent == "unclear":
            p.append("Answer is unclear")
        if parsed.confidence < min_confidence:
            p.append(f"Low confidence ({parsed.confidence:.2f})")
        if message.mode == "inform" and parsed.intent == "decline":
            p.append("Owner disputes an automatically applied change – revert?")
    if not auto_apply:
        p.append("Auto-apply is disabled")
    return Decision(action="apply" if not p else "review", problems=p)
