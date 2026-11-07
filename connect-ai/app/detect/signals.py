"""Features for DetectorV2. Every feature uses only data timestamped before `as_of`."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from app import kit
from app.detect.aliases import mentions_closed_on
from app.server.adapters.suggestions_baseline import BaselineSuggestions

REVIEW_DAYS = 450
_PERM = ("lopettanut", "pysyvästi", "stängt för gott", "permanent", "lagt ned", "stengt for godt", "closed down")


def cycle(d: date) -> int:
    return d.year if d.month >= 2 else d.year - 1


def day_str(obj: dict | None) -> str:
    if not obj or obj.get("isClosed"):
        return "closed"
    return ",".join(f"{i['start']}-{i['end']}" for i in obj.get("openIntervals", [])) or "closed"


def peer_bucket(share: float | None) -> str:
    if share is None:
        return "none"
    return "<0.2" if share < 0.2 else "0.2-0.5" if share < 0.5 else "0.5-0.8" if share < 0.8 else ">=0.8"


class Signals:
    """Computes `features(row)` as of `as_of`. `sg` is a loaded BaselineSuggestions (shared data, never mutated)."""

    def __init__(self, sg: BaselineSuggestions, as_of: date):
        sg._load()
        self.sg, self.bl, self.as_of = sg, sg.bl, as_of
        self._iso = as_of.isoformat()
        self._ms = datetime(as_of.year, as_of.month, as_of.day).timestamp() * 1000
        self._has_history = {
            eid for (eid, _d), rows in self.bl.hol.items() if any(r["entered_at"] < self._iso for r in rows)
        }
        self._closed_signal = self._build_closed_signal()
        self._edits: dict[str, dict[str, list[dict]]] = {}
        for eid, items in sg.psugg.items():
            for s in items:
                if s["fieldName"] != "hours" or s["dateCreated"] >= self._iso:
                    continue
                try:
                    hh = json.loads(s["suggestedContent"]).get("holidayHours") or []
                except (ValueError, TypeError, AttributeError):
                    continue
                for h in hh:
                    if isinstance(h, dict) and h.get("date"):
                        self._edits.setdefault(eid, {}).setdefault(h["date"], []).append(
                            {"created": s["dateCreated"], "status": s["status"], "hours": day_str(h)}
                        )
        since = self._ms - REVIEW_DAYS * 86400000
        self._reviews = {
            eid: [r for r in rs if since <= r["publisherDate"] < self._ms and r.get("content")]
            for eid, rs in sg.reviews.items()
        }

    def _build_closed_signal(self) -> set[str]:
        out: set[str] = set()
        for eid, rs in self.sg.reviews.items():
            for r in rs:
                if self._ms - 150 * 86400000 < r["publisherDate"] < self._ms and any(
                    w in (r.get("content") or "").lower() for w in _PERM
                ):
                    out.add(eid)
        for eid, items in self.sg.psugg.items():
            if any(s["fieldName"] == "closed" and s["dateCreated"] < self._iso for s in items):
                out.add(eid)
        return out

    # --- as-of versions of the kit baseline helpers (kit code stays untouched)
    def regular(self, eid: str, d: date) -> str:
        cands = [r for r in self.bl.reg[eid] if r["effective_from"] == "before-2024" or r["effective_from"] < self._iso]
        best = max(cands, key=lambda r: "0000" if r["effective_from"] == "before-2024" else r["effective_from"])
        return day_str(best["hours"][kit.DAYS[d.weekday()]])

    def displayed(self, eid: str, d: date) -> str:
        e = self.bl.entry(eid, d, self.as_of)
        return self.regular(eid, d) if e is None or e == "REGULAR" else e

    def features(self, eid: str, d: date, day_key: str) -> dict:
        bl, ent = self.bl, self.bl.ents[eid]
        country = ent["meta"]["countryCode"]
        segment = ent.get("c_segment")
        shown = self.displayed(eid, d)
        entered = bl.entry(eid, d, self.as_of)
        f: dict = {
            "country": country,
            "segment": segment,
            "day_key": day_key,
            "shown": shown,
            "shown_source": "exception" if entered not in (None, "REGULAR") else "regular",
            "regular": self.regular(eid, d),
            "already_entered": entered is not None,
            "flag": eid in self._closed_signal and not ent.get("closed"),
            "no_history": eid not in self._has_history,
        }
        # shopping-centre hours
        mall = ent.get("c_shoppingCenterEntityId")
        m = bl.entry(mall, d, self.as_of) if mall else None
        f["mall_hours"] = m if m and m != "REGULAR" else None
        f["mall"] = bl.ents[mall]["name"] if f["mall_hours"] else None
        # last year's exception for the same day_key
        f["last_year_exception"], f["last_year_date"] = None, None
        prev = [x for x in bl.dates_by_key[(country, day_key)] if cycle(x) == cycle(d) - 1]
        for p in prev:
            last = bl.entry(eid, p, self.as_of)
            if last is not None:
                f["last_year_exception"] = self.regular(eid, d) if last == "REGULAR" else last
                f["last_year_date"] = p.isoformat()
        # latest Google user edit for last cycle's date of this day_key
        f["last_year_user_edit"], f["last_year_user_edit_status"] = None, None
        best = None
        for p in (
            prev if len(prev) == 1 else ()
        ):  # DECISION: INTERDAY has several dates a cycle; the match would be a guess
            for e in self._edits.get(eid, {}).get(p.isoformat(), []):
                if best is None or e["created"] > best["created"]:
                    best = e
        if best:
            f["last_year_user_edit"], f["last_year_user_edit_status"] = best["hours"], best["status"]
        # reviews that mention this holiday and a closed word
        f["review_closed"] = any(mentions_closed_on(r["content"], day_key) for r in self._reviews.get(eid, ()))
        # peers
        b = bl.bench.get((country, bl.tiers[ent["address"]["city"]], segment, day_key))
        f["peer_closed"], f["peer_n"], f["peer_special"], f["peer_entered_closed"] = None, None, None, None
        if b:
            cs = b.get("closed_share_among_entered")
            f["peer_closed"] = float(cs) if cs not in (None, "") else None
            f["peer_n"] = int(b["n_entity_days"])
            f["peer_entered_closed"] = float(b["share_entered_closed"] or 0)
            if b.get("median_open_special") and b.get("median_close_special"):
                f["peer_special"] = f"{b['median_open_special']}-{b['median_close_special']}"
        f["peer_bucket"] = peer_bucket(f["peer_closed"])
        return f

    def features_for_row(self, row) -> dict:
        return self.features(row.entity_id, date.fromisoformat(row.date), row.day_key)


def window(as_of: date, days: int = 61) -> tuple[str, str]:
    return as_of.isoformat(), (as_of + timedelta(days=days)).isoformat()
