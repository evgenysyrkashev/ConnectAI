"""Learning from the owner's own decisions. Pure.

The history holds what this owner answered in earlier seasons, per `day_key`. For the same day in a later year:
- they edited our hours   -> suggest *their* hours (basis OWN_EDIT);
- they approved our hours -> suggest the same again (basis OWN_APPROVED);
- they declined hours X   -> never suggest X again for that day (basis OWN_DECLINE). A different suggestion still goes
  out: in the 2025 pilot a declined suggestion was right for 2026 only 2 times in 28, but the day still needed action
  19 times in 28, so staying quiet for the whole day would lose real corrections.
"""

from __future__ import annotations

from typing import Literal, TypedDict


class HistoryEntry(TypedDict):
    date: str  # the holiday date the decision was about, YYYY-MM-DD
    day_key: str
    outcome: Literal["approved", "edited", "declined"]
    hours: str | None  # approved/edited: the hours the owner ended up with; declined: the hours they turned down


class Override(TypedDict):
    action: Literal["SUGGEST", "NO_ACTION", "QUIET"]
    hours: str | None
    basis: str
    evidence: dict


def latest_before(history: list[HistoryEntry], day_key: str, date: str) -> HistoryEntry | None:
    """The most recent decision on the same day_key from an earlier year than `date`."""
    year = date[:4]
    prior = [h for h in history if h["day_key"] == day_key and h["date"][:4] < year]
    return max(prior, key=lambda h: h["date"]) if prior else None


def override(
    history: list[HistoryEntry], day_key: str, date: str, shown: str, suggested: str | None = None
) -> Override | None:
    """`suggested` is what the detector would suggest now (None for no suggestion)."""
    h = latest_before(history, day_key, date)
    if h is None:
        return None
    ev = {"own_date": h["date"], "outcome": h["outcome"]}
    if h["outcome"] == "declined":
        if suggested is not None and suggested == h["hours"]:
            return {"action": "QUIET", "hours": None, "basis": "OWN_DECLINE", "evidence": ev}
        return None
    hours = h["hours"]
    if not hours:
        return None
    basis = "OWN_EDIT" if h["outcome"] == "edited" else "OWN_APPROVED"
    ev["hours"] = hours
    if hours == shown:
        return {"action": "NO_ACTION", "hours": None, "basis": basis, "evidence": ev}
    return {"action": "SUGGEST", "hours": hours, "basis": basis, "evidence": ev}


def entry_from_decision(
    date: str, day_key: str, action: str, suggested: str | None, set_hours: str | None
) -> HistoryEntry | None:
    """Map one resolved DateDecision (accept | regular | set | decline) to a history entry. 'regular' says nothing about hours."""
    if action == "decline":
        return {"date": date, "day_key": day_key, "outcome": "declined", "hours": suggested}
    if action == "accept" and suggested:
        return {"date": date, "day_key": day_key, "outcome": "approved", "hours": suggested}
    if action == "set" and set_hours:
        return {"date": date, "day_key": day_key, "outcome": "edited", "hours": set_hours}
    return None


def merge(*histories: list[HistoryEntry]) -> list[HistoryEntry]:
    """Later sources win for the same (date, day_key)."""
    out: dict[tuple[str, str], HistoryEntry] = {}
    for hist in histories:
        for h in hist:
            out[(h["date"], h["day_key"])] = h
    return list(out.values())
