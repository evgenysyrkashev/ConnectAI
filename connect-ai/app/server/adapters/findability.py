"""Expected Google search views per day, from data/analytics_daily.parquet."""

from __future__ import annotations

from datetime import date, timedelta
from statistics import median

from app import kit

NO_MULT = {"EVENT", "SCHOOL_BREAK"}


class ParquetFindability:
    def __init__(self, snapshot: date = date(2026, 11, 6), recent_days: int = 28, calendar_path: str | None = None):
        import csv

        import pandas as pd

        df = pd.read_parquet(
            kit.data_path("data", "analytics_daily.parquet"),
            columns=["date", "entity_id", "GOOGLE_SEARCH_VIEWS", "GOOGLE_MAP_VIEWS"],
        )
        df["date"] = df["date"].astype(str)
        self._search: dict[str, dict[str, float]] = {}
        self._map: dict[str, dict[str, float]] = {}
        for eid, g in df.groupby("entity_id"):
            self._search[eid] = dict(zip(g["date"], g["GOOGLE_SEARCH_VIEWS"], strict=True))
            self._map[eid] = dict(zip(g["date"], g["GOOGLE_MAP_VIEWS"], strict=True))
        last = max(d for d in df["date"].unique() if d < snapshot.isoformat())
        end = date.fromisoformat(last)
        self._recent: dict[str, float] = {}
        win = [(end - timedelta(days=i)).isoformat() for i in range(recent_days)]
        for eid, s in self._search.items():
            vals = [s[d] for d in win if d in s]
            self._recent[eid] = sum(vals) / len(vals) if vals else 0.0
        with open(calendar_path or kit.data_path("data", "calendar_special_days.csv"), encoding="utf-8") as f:
            cal = list(csv.DictReader(f))
        self._cal = {(r["country"], r["date"]): r["day_key"] for r in cal}
        # day_multiplier[day_key]: median over businesses of views on last cycle's date / mean of 28 days before it
        ratios: dict[str, list[float]] = {}
        for r in cal:
            d = date.fromisoformat(r["date"])
            if d >= snapshot or r["day_key"] in NO_MULT:
                continue
            for eid, s in self._search.items():
                if not eid.startswith(r["country"]):
                    continue
                v = s.get(r["date"])
                base = [s[x] for x in ((d - timedelta(days=i)).isoformat() for i in range(1, 29)) if x in s]
                if v is not None and base and sum(base) > 0:
                    ratios.setdefault(r["day_key"], []).append(v / (sum(base) / len(base)))
        self.day_multiplier = {k: min(3.0, max(0.3, median(v))) for k, v in ratios.items() if v}
        self._dates_by_key: dict[tuple[str, str], list[str]] = {}
        for r in cal:
            self._dates_by_key.setdefault((r["country"], r["day_key"]), []).append(r["date"])

    def recent_mean(self, eid: str) -> float:
        return self._recent.get(eid, 0.0)

    def est_views(self, eid: str, date: str, day_key: str) -> int:
        return round(self.recent_mean(eid) * self.day_multiplier.get(day_key, 1.0))

    def last_year_views(self, eid: str, day_key: str, country: str, date: str) -> int | None:
        """Search + map views on last cycle's date of the same day_key; None if missing."""
        d = _d(date)
        cyc = d.year if d.month >= 2 else d.year - 1
        for x in self._dates_by_key.get((country, day_key), []):
            xd = _d(x)
            if (xd.year if xd.month >= 2 else xd.year - 1) == cyc - 1:
                s, m = self._search.get(eid, {}).get(x), self._map.get(eid, {}).get(x)
                if s is None and m is None:
                    return None
                return int((s or 0) + (m or 0))
        return None


def _d(s: str) -> date:
    return date.fromisoformat(s)
