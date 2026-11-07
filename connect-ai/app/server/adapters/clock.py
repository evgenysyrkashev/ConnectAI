"""Clocks: system, demo offset (advance time for escalation demos) and fixed (tests)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FixedClock:
    def __init__(self, at: datetime):
        self.at = at

    def now(self) -> datetime:
        return self.at

    def advance(self, hours: float) -> None:
        self.at += timedelta(hours=hours)


class OffsetClock:
    """System time plus an offset in hours stored in state/clock."""

    def __init__(self, base, store):
        self.base, self.store = base, store

    def offset_hours(self) -> float:
        return float((self.store.get_state("clock") or {}).get("hours", 0))

    def now(self) -> datetime:
        return self.base.now() + timedelta(hours=self.offset_hours())

    def advance(self, hours: float) -> None:
        self.store.set_state("clock", {"hours": self.offset_hours() + hours})

    def reset(self) -> None:
        self.store.set_state("clock", {"hours": 0})
