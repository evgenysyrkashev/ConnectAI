"""Owner-decision memory: seed from the 2025 pilot log, extend with every answer we process."""

from __future__ import annotations

import csv
import logging
from functools import lru_cache

from app import kit
from app.core import learning
from app.core.learning import HistoryEntry
from app.server.services.common import Deps

log = logging.getLogger("connect.learning")
_OUTCOME = {"ACCEPTED": "approved", "EDITED": "edited", "REJECTED": "declined"}


@lru_cache(maxsize=1)
def pilot_history() -> dict[str, list[HistoryEntry]]:
    """entity_id -> decisions from data/pilot_decision_log_2025.csv (NO_RESPONSE rows say nothing and are skipped)."""
    out: dict[str, list[HistoryEntry]] = {}
    try:
        with open(kit.data_path("data", "pilot_decision_log_2025.csv"), encoding="utf-8") as f:
            for r in csv.DictReader(f):
                outcome = _OUTCOME.get(r["decision"])
                if outcome is None:
                    continue
                hours = r["suggested_hours"] if outcome != "edited" else r["final_hours"]
                if not hours:
                    continue
                out.setdefault(r["entity_id"], []).append(
                    {"date": r["date"], "day_key": r["day_key"], "outcome": outcome, "hours": hours}  # type: ignore[typeddict-item]
                )
    except FileNotFoundError:
        log.warning("pilot decision log not found; learning starts empty")
    return out


def _key(eid: str) -> str:
    return f"owner-history-{eid}"


def history_for(deps: Deps, eid: str) -> list[HistoryEntry]:
    seed = pilot_history().get(eid, []) if deps.cfg.learn_from_pilot else []
    own = (deps.store.get_state(_key(eid)) or {}).get("entries", [])
    return learning.merge(seed, own)


def record(deps: Deps, message, decisions) -> int:
    """Remember what the owner decided for each date of `message`. Returns the number of entries stored."""
    if message.kind != "dates" or not decisions:
        return 0
    by_date = {i.date: i for i in message.items}
    new: list[HistoryEntry] = []
    for d in decisions:
        item = by_date.get(d.date)
        if item is None:
            continue
        e = learning.entry_from_decision(d.date, item.day_key, d.action, item.suggested_hours, d.hours)
        if e:
            new.append(e)
    if new:
        own = (deps.store.get_state(_key(message.entity_id)) or {}).get("entries", [])
        deps.store.set_state(_key(message.entity_id), {"entries": learning.merge(own, new)})
    return len(new)
