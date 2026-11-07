"""Fixture findability for tests: numbers from dicts, 0 by default."""

from __future__ import annotations


class FakeFindability:
    def __init__(
        self,
        est: dict[tuple[str, str], int] | None = None,
        last_year: dict[tuple[str, str], int] | None = None,
        default_est: int = 0,
        recent: dict[str, float] | None = None,
    ):
        self.est, self.last_year, self.default_est, self.recent = est or {}, last_year or {}, default_est, recent or {}

    def est_views(self, eid: str, date: str, day_key: str) -> int:
        return self.est.get((eid, date), self.default_est)

    def last_year_views(self, eid: str, day_key: str, country: str, date: str) -> int | None:
        return self.last_year.get((eid, date))

    def recent_mean(self, eid: str) -> float:
        return self.recent.get(eid, 0.0)
