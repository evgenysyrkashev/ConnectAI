"""Validation of a ParsedReply against the message it answers. Pure."""

from __future__ import annotations

from app import kit
from app.core.models import WEEKDAYS, DateDecision, OutboundMessage, ParsedReply


def valid_hours(s: str) -> bool:
    """Kit validity plus: no interval whose start equals its end (except none)."""
    if not kit.is_valid_hours(s):
        return False
    if s.strip().lower() == "closed":
        return True
    return all(iv.split("-")[0] != iv.split("-")[1] for iv in s.split(","))


def validate_parsed(parsed: ParsedReply | None, decisions: list[DateDecision], message: OutboundMessage) -> list[str]:
    if parsed is None:
        return []
    problems: list[str] = []
    if message.kind == "dates" and parsed.weekly is not None:
        problems.append("Weekly hours given for a dates message")
    if message.kind == "weekly" and parsed.dates is not None:
        problems.append("Dates given for a weekly message")
    if message.kind == "permission" and (parsed.dates is not None or parsed.weekly is not None):
        problems.append("Hours given in answer to a permission request")
    item_dates = {i.date for i in message.items}
    seen: set[str] = set()
    for d in parsed.dates or []:
        if d.date not in item_dates:
            problems.append(f"Date {d.date} is not one we asked about")
        if d.date in seen:
            problems.append(f"Date {d.date} appears twice")
        seen.add(d.date)
        if d.action == "set":
            if not d.hours or not valid_hours(d.hours):
                problems.append(f"Invalid hours for {d.date}: {d.hours!r}")
        elif d.hours is not None:
            problems.append(f"Hours given for {d.date} with action {d.action}")
    for day, hours in (parsed.weekly or {}).items():
        if day not in WEEKDAYS:
            problems.append(f"Unknown weekday {day!r}")
        elif not valid_hours(hours):
            problems.append(f"Invalid hours for {day}: {hours!r}")
    if parsed.intent == "edit":
        nothing = (message.kind == "dates" and all(d.action == "decline" for d in decisions)) or (
            message.kind == "weekly" and not parsed.weekly
        )
        if nothing:
            problems.append("Edit would not change anything")
    if parsed.permanently_closed:
        problems.append("Owner says the business closed for good – flag for a human")
    return problems
