"""Suggestions port backed by the kit baseline. The seam where a better detector plugs in."""

from __future__ import annotations

import csv
import json
import re
import threading
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from app import kit
from app.server.ports import Detection, TargetRow

# DECISION: patterns for "the regular hours changed" in reviews (fi/sv/nb/en). Written from the examples in the plan;
# precision is to be checked with scripts/eval_quiet.py. Closed-for-good wording is excluded (FLAG, not stale hours).
CHANGED_HOURS_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"öppettiderna har ändrats",
        r"nya öppettider",
        r"ändrade öppettider",
        r"numera öppet",
        r"aukioloajat ovat muuttuneet",
        r"aukioloaikoja on muutettu",
        r"uudet aukioloajat",
        r"nykyään auki",
        r"åpningstidene har (endret|endra)",
        r"nye åpningstider",
        r"nå (kun )?åpent",
        r"opening hours (have|has) changed",
        r"hours (have )?changed",
        r"new opening hours",
        r"now (only )?open",
    )
]
_PERM = ("lopettanut", "pysyvästi", "stängt för gott", "permanent", "lagt ned", "stengt for godt", "closed down")


class BaselineSuggestions:
    def __init__(self, snapshot: date = date(2026, 11, 6), stale_days: int = 180):
        self.snapshot, self.stale_days = snapshot, stale_days
        self._lock = threading.Lock()
        self._loaded = False
        self.extra_demo_ids: list[str] = []  # entities fetched from the Yext sandbox (shown in the demo list)

    # --- loading
    def _load(self) -> None:
        with self._lock:
            if self._loaded:
                return
            bl = kit.load_baseline(self.snapshot.year)
            self.bl = bl
            self.targets: dict[str, list[TargetRow]] = defaultdict(list)
            targets = "targets_2026.csv" if self.snapshot.year == 2026 else "targets_2025_backtest.csv"
            with open(kit.data_path("evaluation", targets), encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    self.targets[r["entity_id"]].append(
                        TargetRow(
                            entity_id=r["entity_id"],
                            date=r["date"],
                            day_key=r["day_key"],
                            day_type=r["day_type"],
                            event_id=r["event_id"] or None,
                            country=r["country"],
                            split=r["split"],
                        )
                    )
            self.cal = {(r["country"], r["date"]): r for r in bl.cal}
            with open(kit.data_path("data", "local_events.json"), encoding="utf-8") as f:
                self.events = {e["@id"]: e for e in json.load(f)["data"]}
            with open(kit.data_path("data", "splits.csv"), encoding="utf-8") as f:
                self.splits = {r["entity_id"]: r["split"] for r in csv.DictReader(f)}
            self.history_ids = {k[0] for k in bl.hol}
            self.event_hist: dict[str, dict[str, dict]] = defaultdict(dict)  # eid -> date -> latest row before snapshot
            snap = self.snapshot.isoformat()
            for (eid, d), rows in bl.hol.items():
                for r in rows:
                    if r.get("day_key") == "EVENT" and r["entered_at"] < snap:
                        cur = self.event_hist[eid].get(d)
                        if cur is None or r["entered_at"] > cur["entered_at"]:
                            self.event_hist[eid][d] = r
            self.reg_changed: dict[str, str] = {}
            with open(kit.data_path("data", "regular_hours_history.jsonl"), encoding="utf-8") as f:
                for line in f:
                    r = json.loads(line)
                    ef = r["effective_from"]
                    if ef != "before-2024" and ef > self.reg_changed.get(r["entity_id"], ""):
                        self.reg_changed[r["entity_id"]] = ef
            with open(kit.data_path("data", "reviews.json"), encoding="utf-8") as f:
                self.reviews: dict[str, list[dict]] = defaultdict(list)
                for r in json.load(f)["response"]["reviews"]:
                    self.reviews[r["locationId"]].append(r)
            with open(kit.data_path("data", "publisher_suggestions.json"), encoding="utf-8") as f:
                self.psugg: dict[str, list[dict]] = defaultdict(list)
                for s in json.load(f)["response"]["suggestions"]:
                    self.psugg[s["locationId"]].append(s)
            self._loaded = True

    # --- port
    def rows_for(self, eid: str) -> list[TargetRow]:
        self._load()
        snap = self.snapshot.isoformat()
        return sorted((r for r in self.targets.get(eid, []) if r.date > snap), key=lambda r: r.date)

    def detect(self, row: TargetRow) -> Detection:
        self._load()
        bl, eid, d = self.bl, row.entity_id, date.fromisoformat(row.date)
        act, hours, basis, ev = bl.explain(eid, d, row.day_key)
        shown = bl.displayed(eid, d)
        entered = bl.entry(eid, d, bl.snap)
        source = "exception" if entered not in (None, "REGULAR") else "regular"
        evidence: dict = {}
        if basis == "LAST_YEAR":
            last_date, last = ev
            evidence = {
                "last_year_date": last_date,
                "last_year_hours": bl.regular(eid, d) if last == "REGULAR" else last,
            }
        elif basis == "SHOPPING_CENTRE":
            evidence = {"mall": ev}
        elif basis == "PEERS":
            evidence = {"share": ev}
        elif basis == "CLOSED_SIGNALS":
            evidence = {"text": ev}
        if act == "FLAG":
            return Detection(action="FLAG", shown_hours=shown, shown_source=source, basis=basis, evidence=evidence)
        if entered is not None:  # Override 1: already entered before the snapshot
            return Detection(
                action="NO_ACTION",
                shown_hours=shown,
                shown_source=source,
                basis="ALREADY_ENTERED",
                evidence={"entered": entered},
            )
        if act == "NO_ACTION" and row.day_key == "EVENT":  # Override 2: event nights
            hist = self.event_hist.get(eid, {})
            if hist:
                hs = {dt: self._hist_hours(eid, dt, r) for dt, r in hist.items()}
                counts = Counter(hs.values())
                top = max(counts.values())
                best = max((dt for dt, h in hs.items() if counts[h] == top))  # tie → latest
                h = hs[best]
                if h != shown:
                    return Detection(
                        action="SUGGEST",
                        suggested_hours=h,
                        shown_hours=shown,
                        shown_source=source,
                        basis="LAST_EVENT",
                        evidence={"event_nights": len(hist), "hours": h, "last_date": best},
                    )
            return Detection(action="NO_ACTION", shown_hours=shown, shown_source=source, basis=basis, evidence=evidence)
        return Detection(
            action=act,
            suggested_hours=hours or None if act == "SUGGEST" else None,
            shown_hours=shown,
            shown_source=source,
            basis=basis,
            evidence=evidence,
        )

    def _hist_hours(self, eid: str, d: str, r: dict) -> str:
        h = r["holidayHours"]
        if h.get("isRegularHours"):
            return self.bl.regular(eid, date.fromisoformat(d))
        from app.kit import yext_day_to_str

        return yext_day_to_str(h)

    def has_history(self, eid: str) -> bool:
        self._load()
        return eid in self.history_ids

    def peer_change_share(self, eid: str, row: TargetRow) -> tuple[float, int] | None:
        self._load()
        bl = self.bl
        ent = bl.ents[eid]
        key = (row.country, bl.tiers[ent["address"]["city"]], ent["c_segment"], row.day_key)
        b = bl.bench.get(key)
        if not b:
            return None
        closed, special, regular = (
            float(b[k] or 0) for k in ("share_entered_closed", "share_entered_special_hours", "share_entered_regular")
        )
        entered = closed + special + regular
        if entered == 0:
            return None
        return (closed + special) / entered, int(b["n_entity_days"])

    def stale_evidence(self, eid: str) -> list[dict]:
        self._load()
        snap = datetime(self.snapshot.year, self.snapshot.month, self.snapshot.day)
        since = snap - timedelta(days=self.stale_days)
        out: list[dict] = []
        for s in self.psugg.get(eid, []):
            if (
                s["fieldName"] == "hours"
                and s["status"] == "WAITING_ON_CUSTOMER"
                and _changes_regular_day(s["suggestedContent"])
            ):
                created = datetime.fromisoformat(s["dateCreated"])
                if since <= created < snap:
                    out.append(
                        {"type": "publisher_suggestion", "date": s["dateCreated"], "text": _summ(s["suggestedContent"])}
                    )
        for r in self.reviews.get(eid, []):
            when = datetime.fromtimestamp(r["publisherDate"] / 1000)
            content = r.get("content") or ""
            if since <= when < snap and any(p.search(content) for p in CHANGED_HOURS_PATTERNS):
                if any(w in content.lower() for w in _PERM):
                    continue
                out.append({"type": "review", "date": when.date().isoformat(), "text": content[:200]})
        return out

    def day_info(self, country: str, date: str) -> dict | None:
        self._load()
        r = self.cal.get((country, date))
        if not r:
            return None
        return {k: r[k] for k in ("name_local", "name_en", "day_class", "day_type")}

    def event(self, event_id: str) -> dict | None:
        self._load()
        return self.events.get(event_id)

    def split(self, eid: str) -> str:
        self._load()
        return self.splits.get(eid, "test")

    def regular_last_changed(self, eid: str) -> str | None:
        self._load()
        return self.reg_changed.get(eid)

    def entity_ids(self, split: str | None = None) -> list[str]:
        self._load()
        ids = [e for e, s in sorted(self.splits.items()) if split is None or s == split]
        if split in (None, "demo"):
            ids += [e for e in self.extra_demo_ids if e not in ids]
        return ids


def _changes_regular_day(content: str) -> bool:
    """DECISION: only a suggestion that changes a regular weekday counts. On the dev labels, suggestions that only add
    holidayHours were right 1 of 25 times; weekday suggestions 4 of 11 (measured with scripts/eval_quiet.py)."""
    try:
        return any(k in json.loads(content) for k in kit.DAYS)
    except (ValueError, TypeError):
        return False


def _summ(content: str) -> str:
    try:
        obj = json.loads(content)
        keys = [k for k in obj if k != "holidayHours"] or list(obj)
        return "suggested: " + ", ".join(keys)
    except Exception:  # noqa: BLE001
        return content[:80]
