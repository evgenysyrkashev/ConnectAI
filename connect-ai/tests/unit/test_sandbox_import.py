from app.server.services.sandbox import import_entities


class _Client:
    def get_entity(self, eid):
        if eid == "boom":
            raise RuntimeError("down")
        return {"name": "Shop", "meta": {"id": eid}}


def test_import_maps_id_adds_hours_and_skips_failures():
    out = import_entities(_Client(), "LOCAL1=sbx1;LOCAL2=boom")
    assert [e["meta"]["id"] for e in out] == ["LOCAL1"]
    assert out[0]["hours"]["sunday"] == {"isClosed": True}


def test_import_without_map_is_empty():
    assert import_entities(_Client(), None) == []
