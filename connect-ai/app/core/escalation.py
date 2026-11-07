"""When to send the fallback message. Pure."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.models import Channel

DEFAULT_CHAIN = "whatsapp>email;sms>email;email>permission"


def parse_chain(spec: str | list[str]) -> dict[str, str]:
    """'whatsapp>email;sms>email' (or a list of 'a>b') -> {'whatsapp': 'email', 'sms': 'email'}."""
    parts = spec if isinstance(spec, list) else spec.split(";")
    out: dict[str, str] = {}
    for p in parts:
        if ">" in p:
            a, b = p.split(">", 1)
            out[a.strip().lower()] = b.strip().lower()
    return out


def _parse_window(w: str) -> tuple[int, int] | None:
    m = re.fullmatch(r"\s*(\d{1,2})\s*-\s*(\d{1,2})\s*", w or "")
    if not m:
        return None
    s, e = int(m.group(1)), int(m.group(2))
    return (s, e) if 0 <= s <= 24 and 0 <= e <= 24 and s != e else None


def in_window(local_hour: int, start: int, end: int) -> bool:
    return start <= local_hour < end if start < end else (local_hour >= start or local_hour < end)


def next_window_start(t: datetime, contact_window: str, tz: str) -> datetime:
    """`t` itself if it is inside the contact window (or the window is unusable), else the next window start."""
    win = _parse_window(contact_window)
    if win is None:
        return t
    start, end = win
    zone = ZoneInfo(tz)
    local = t.astimezone(zone)
    if in_window(local.hour, start, end):
        return t
    day = local.date()
    if local.hour >= start and start < end:  # after the window: next day
        day = day + timedelta(days=1)
    # (before the window, or the gap of a wrapping window: later today)
    return datetime(day.year, day.month, day.day, start % 24, 0, tzinfo=zone).astimezone(t.tzinfo)


def plan_escalation(
    sent_at: datetime,
    channel: Channel,
    usual_h: float,
    usual_source: str,
    contact_window: str,
    tz: str,
    chain: dict[str, str],
    factor: float,
    min_hours: float,
    respect_window: bool,
) -> tuple[datetime | None, str | None]:
    """Returns (escalate_at in UTC, human-readable basis) or (None, None) if the channel has no fallback."""
    if channel not in chain:
        return None, None
    wait_h = max(factor * usual_h, min_hours)
    t = sent_at + timedelta(hours=wait_h)
    win = _parse_window(contact_window) if respect_window else None
    if win is None:
        note = "no window"
    else:
        moved = next_window_start(t, contact_window, tz)
        note = f"inside window {win[0]}–{win[1]}" if moved == t else f"moved to window {win[0]}–{win[1]}"
        t = moved
    basis = f"{factor:g}× usual {usual_h:.1f} h ({usual_source}) → wait {wait_h:.1f} h → {note}"
    return t, basis
