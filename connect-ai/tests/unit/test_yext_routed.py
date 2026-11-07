from app.server.adapters.yext_routed import RoutedYext


class _Y:
    def __init__(self, tag):
        self.tag, self.writes = tag, []

    def get_entity(self, eid):
        return {"name": self.tag, "meta": {"id": eid}}

    def list_entities(self, ids):
        return [self.get_entity(i) for i in ids]

    def put_hours(self, eid, hours):
        self.writes.append(eid)
        return {}

    def listings(self, eid):
        return []

    def analytics(self, eid, s, e, m):
        return {}


def test_mapped_entity_goes_to_sandbox_with_local_id():
    mock, sbx = _Y("mock"), _Y("sandbox")
    y = RoutedYext(mock, sbx, {"FI-D0001": "SinceAI14"})
    ents = y.list_entities(["FI-D0002", "FI-D0001"])
    assert [(e["meta"]["id"], e["name"]) for e in ents] == [("FI-D0002", "mock"), ("FI-D0001", "sandbox")]
    y.put_hours("FI-D0001", {})
    y.put_hours("FI-D0002", {})
    assert sbx.writes == ["SinceAI14"] and mock.writes == ["FI-D0002"]


def test_kit_only_fields_are_merged_but_sandbox_wins():
    class Kit(_Y):
        def get_entity(self, eid):
            return {"name": "Kit", "c_segment": "cafe", "categoryIds": ["1001"], "meta": {"id": eid}}

    class Sbx(_Y):
        def get_entity(self, eid):
            return {"name": "Sbx", "c_segment": "bike", "meta": {"id": eid}}

    e = RoutedYext(Kit("k"), Sbx("s"), {"FI-D0001": "S"}).get_entity("FI-D0001")
    assert (e["name"], e["c_segment"], e["categoryIds"]) == ("Sbx", "bike", ["1001"])


def test_sandbox_read_failure_does_not_hide_the_list():
    class Boom(_Y):
        def get_entity(self, eid):
            raise RuntimeError("down")

    y = RoutedYext(_Y("mock"), Boom("x"), {"FI-D0001": "S"})
    assert [e["meta"]["id"] for e in y.list_entities(["FI-D0002", "FI-D0001"])] == ["FI-D0002"]
