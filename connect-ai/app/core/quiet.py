"""Stay quiet unless there is a reason. Pure."""

from __future__ import annotations

from collections import Counter
from typing import Literal

from app.core.models import DateItem

SkipCode = Literal[
    "no_evidence",
    "already_entered",
    "already_asked",
    "flagged",
    "opted_out",
    "closed_in_yext",
    "no_contact",
    "no_longer_needed",
    "date_passed",
    "answered",
    "owner_declined",
]


def filter_items(
    items: list[DateItem],
    live_holiday_dates: set[str],
    recently_asked: set[str],
    today: str,
    exempt_dates: set[str] = frozenset(),  # type: ignore[assignment]
) -> tuple[list[DateItem], list[tuple[DateItem, SkipCode]]]:
    """Drop items that need no message. Returns (kept, dropped-with-reason); kept keeps its input order."""
    kept: list[DateItem] = []
    dropped: list[tuple[DateItem, SkipCode]] = []
    for it in items:
        code: SkipCode | None = None
        if it.date in live_holiday_dates:
            code = "already_entered"
        elif it.date in recently_asked and it.date not in exempt_dates:
            code = "already_asked"
        elif it.basis == "OWN_DECLINE":
            code = "owner_declined"  # the owner declined this day in an earlier season (learning.py)
        elif it.date <= today:
            code = "date_passed"
        elif it.suggested_hours is not None and it.suggested_hours == it.shown_hours:
            code = "no_evidence"  # redundant confirmation
        if code is None:
            kept.append(it)
        else:
            dropped.append((it, code))
    return kept, dropped


def message_skip(
    *,
    has_contact: bool,
    opted_out: bool,
    closed_in_yext: bool,
    flagged_evidence: str | None,
    kept: list[DateItem],
    dropped: list[tuple[DateItem, SkipCode]],
) -> tuple[SkipCode, str] | None:
    """Message-level skip order: no_contact → opted_out → closed_in_yext → flagged → no items left.

    Returns (code, human-readable skip_reason) or None when the message should be built.
    """
    if not has_contact:
        return "no_contact", "no contact"
    if opted_out:
        return "opted_out", "opted out"
    if closed_in_yext:
        return "closed_in_yext", "closed in Yext"
    if flagged_evidence is not None:
        return "flagged", f"flagged: {flagged_evidence}"
    if kept:
        return None
    if dropped:
        # most common drop code; ties resolved by first appearance
        counts = Counter(code for _, code in dropped)
        top = max(counts.values())
        code = next(c for _, c in dropped if counts[c] == top)
        return code, code
    return "no_evidence", "no_evidence"
