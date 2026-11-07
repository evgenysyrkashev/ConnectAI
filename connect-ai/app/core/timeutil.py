"""ISO timestamp helpers (pure; `now` is always passed in)."""

from datetime import UTC, datetime, timedelta


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def plus_days(dt: datetime, days: float) -> datetime:
    return dt + timedelta(days=days)
