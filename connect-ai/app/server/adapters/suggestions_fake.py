"""In-memory Suggestions fixture for tests."""

from __future__ import annotations

from app.server.ports import Detection, TargetRow


class FakeSuggestions:
    def __init__(self) -> None:
        self.rows: dict[str, list[TargetRow]] = {}
        self.detections: dict[tuple[str, str], Detection] = {}
        self.history: set[str] = set()
        self.days: dict[tuple[str, str], dict] = {}
        self.events: dict[str, dict] = {}
        self.splits: dict[str, str] = {}
        self.peer: dict[tuple[str, str], tuple[float, int]] = {}
        self.stale: dict[str, list[dict]] = {}

    def add(
        self,
        row: TargetRow,
        det: Detection,
        day_name: tuple[str, str] = ("Jouluaatto", "Christmas Eve"),
        day_class: str = "MAJOR",
    ) -> None:
        self.rows.setdefault(row.entity_id, []).append(row)
        self.rows[row.entity_id].sort(key=lambda r: r.date)
        self.detections[(row.entity_id, row.date)] = det
        self.days.setdefault(
            (row.country, row.date),
            {"name_local": day_name[0], "name_en": day_name[1], "day_class": day_class, "day_type": row.day_type},
        )

    def rows_for(self, eid: str) -> list[TargetRow]:
        return list(self.rows.get(eid, []))

    def detect(self, row: TargetRow) -> Detection:
        return self.detections[(row.entity_id, row.date)]

    def has_history(self, eid: str) -> bool:
        return eid in self.history

    def day_info(self, country: str, date: str) -> dict | None:
        return self.days.get((country, date))

    def event(self, event_id: str) -> dict | None:
        return self.events.get(event_id)

    def split(self, eid: str) -> str:
        return self.splits.get(eid, "dev")

    def regular_last_changed(self, eid: str) -> str | None:
        return None

    def peer_change_share(self, eid: str, row: TargetRow) -> tuple[float, int] | None:
        return self.peer.get((eid, row.date))

    def stale_evidence(self, eid: str) -> list[dict]:
        return list(self.stale.get(eid, []))

    def entity_ids(self, split: str | None = None) -> list[str]:
        return sorted(self.rows)
