"""Findability priority. Pure."""

from app.core.models import DateItem


def item_priority(
    est_views: int, confidence: float | None, suggested: str | None, shown: str, closed_door_weight: float
) -> float:
    c = confidence if confidence is not None else 0.8  # baseline has no confidence
    w = closed_door_weight if (suggested == "closed" and shown != "closed") else 1.0
    return est_views * c * w if suggested is not None else est_views * 0.3  # ask items count less


def message_priority(items: list[DateItem]) -> float:
    return round(sum(i.priority for i in items), 1)


def weekly_priority(recent_mean: float) -> float:
    """stale_hours messages: a whole week of normal days, at lower certainty."""
    return 7 * recent_mean * 0.5


def at_risk_views(items: list[DateItem]) -> int:
    return sum(i.est_views for i in items if i.suggested_hours is not None)


def top_items(items: list[DateItem], n: int = 6) -> list[DateItem]:
    """Keep the n highest-priority items, listed by date."""
    best = sorted(items, key=lambda i: (-i.priority, i.date))[:n]
    return sorted(best, key=lambda i: i.date)
