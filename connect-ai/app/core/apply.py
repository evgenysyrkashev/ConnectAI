"""Turning decisions into a Yext hours object. Pure."""

from __future__ import annotations

import copy

from app import kit
from app.core.models import DateDecision, DateItem, OutboundMessage, ParsedReply, YextChange


def resolve_decisions(parsed: ParsedReply | None, message: OutboundMessage) -> list[DateDecision]:
    if parsed is None or message.kind != "dates":
        return []
    if parsed.intent == "approve":
        return [
            DateDecision(date=i.date, action="accept" if i.suggested_hours is not None else "regular")
            for i in message.items
        ]
    if parsed.intent == "decline":
        return [DateDecision(date=i.date, action="decline") for i in message.items]
    if parsed.intent == "edit":
        return list(parsed.dates or [])
    return []


def holiday_item(date: str, decision: DateDecision, item: DateItem | None) -> dict | None:
    """The Yext holidayHours item to write, or None for 'no write'."""
    action = decision.action
    if action == "accept" and (item is None or item.suggested_hours is None):
        action = "regular"  # nothing to accept: the owner means normal hours
    if action == "accept":
        assert item is not None and item.suggested_hours is not None
        return {"date": date, **kit.hours_str_to_yext_day(item.suggested_hours)}
    if action == "regular":
        # Also when the shown hours came from an exception: the owner says normal hours apply.
        return {"date": date, "isRegularHours": True}
    if action == "set":
        return {"date": date, **kit.hours_str_to_yext_day(decision.hours or "closed")}
    return None


def compute_hours_update(
    current_hours: dict, message: OutboundMessage, decisions: list[DateDecision], parsed: ParsedReply | None
) -> tuple[dict, dict, dict]:
    """Returns (new_hours, before, after); before/after contain only touched keys."""
    new_hours = copy.deepcopy(current_hours or {})
    before: dict = {}
    after: dict = {}
    if message.kind == "dates":
        by_date = {i.date: i for i in message.items}
        holidays = list(new_hours.get("holidayHours") or [])
        for dec in decisions:
            new_item = holiday_item(dec.date, dec, by_date.get(dec.date))
            if new_item is None:
                continue
            prev = next((h for h in holidays if h.get("date") == dec.date), None)
            before.setdefault("holidayHours", {})[dec.date] = copy.deepcopy(prev)
            after.setdefault("holidayHours", {})[dec.date] = copy.deepcopy(new_item)
            holidays = [h for h in holidays if h.get("date") != dec.date] + [new_item]
        if "holidayHours" in after:
            new_hours["holidayHours"] = sorted(holidays, key=lambda h: h["date"])
    elif message.kind == "weekly" and parsed is not None and parsed.intent == "edit":
        for day, value in (parsed.weekly or {}).items():
            before[day] = copy.deepcopy(new_hours.get(day))
            new_hours[day] = kit.hours_str_to_yext_day(value)
            after[day] = copy.deepcopy(new_hours[day])
    return new_hours, before, after


def revert_hours(current_hours: dict, change: YextChange) -> dict:
    """Restore every key in change.before; a holiday date whose before is None is removed."""
    out = copy.deepcopy(current_hours or {})
    for key, prev in change.before.items():
        if key == "holidayHours":
            holidays = list(out.get("holidayHours") or [])
            for date, item in prev.items():
                holidays = [h for h in holidays if h.get("date") != date]
                if item is not None:
                    holidays.append(copy.deepcopy(item))
            out["holidayHours"] = sorted(holidays, key=lambda h: h["date"])
        elif prev is None:
            out.pop(key, None)
        else:
            out[key] = copy.deepcopy(prev)
    return out
