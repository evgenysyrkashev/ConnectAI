"""Yext port that sends some entities to the real Yext sandbox and everything else to the default (mock).

DECISION: the kit's businesses only exist in the mock, so the demo list keeps using it. Entities in
YEXT_SANDBOX_ENTITY_MAP (`LOCAL_ID=SANDBOX_ID`) are read and written **directly** in the sandbox, with the local id
shown in the app. Nothing is invented: a sandbox entity without `hours` stays without `hours`.
"""

from __future__ import annotations

import logging

log = logging.getLogger("connect.yext")

# Kit-only fields filled in from the kit entity when the sandbox entity lacks them (in memory, never written).
KIT_FIELDS = ("categoryIds", "c_segment", "c_connectProduct", "c_connectCustomerSince")


class RoutedYext:
    def __init__(self, default, sandbox, id_map: dict[str, str]):
        self.default, self.sandbox, self.map = default, sandbox, id_map

    def _local(self, eid: str, ent: dict) -> dict:
        ent["meta"] = {**ent.get("meta", {}), "id": eid}
        try:  # DECISION: merge kit-only fields (e.g. c_segment=cafe) so the app sees one business; sandbox wins
            kit_ent = self.default.get_entity(eid)
        except Exception:  # noqa: BLE001 - not a kit entity, or the default is unavailable
            kit_ent = {}
        for f in KIT_FIELDS:
            if f not in ent and f in kit_ent:
                ent[f] = kit_ent[f]
        return ent

    def get_entity(self, eid: str) -> dict:
        sid = self.map.get(eid)
        if sid is None:
            return self.default.get_entity(eid)
        return self._local(eid, self.sandbox.get_entity(sid))

    def list_entities(self, ids: list[str]) -> list[dict]:
        found = {e["meta"]["id"]: e for e in self.default.list_entities([i for i in ids if i not in self.map])}
        for eid in (i for i in ids if i in self.map):
            try:
                found[eid] = self.get_entity(eid)
            except Exception as exc:  # noqa: BLE001 - one bad sandbox entity must not hide the whole list
                log.warning("sandbox read of %s failed: %s", eid, exc)
        return [found[i] for i in ids if i in found]

    def put_hours(self, eid: str, hours: dict) -> dict:
        sid = self.map.get(eid)
        if sid is None:
            return self.default.put_hours(eid, hours)
        return self.sandbox.put_hours(sid, hours)

    def listings(self, eid: str) -> list[dict]:
        sid = self.map.get(eid)
        return self.sandbox.listings(sid) if sid else self.default.listings(eid)

    def analytics(self, eid: str, start: str, end: str, metrics: list[str]) -> dict[str, int]:
        sid = self.map.get(eid)
        return (
            self.sandbox.analytics(sid, start, end, metrics)
            if sid
            else self.default.analytics(eid, start, end, metrics)
        )
