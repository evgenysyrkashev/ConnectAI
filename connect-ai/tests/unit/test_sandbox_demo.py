import json

import scripts.sandbox_demo as sd


class FakeYext:
    """A tiny Yext: PUT with None clears a field."""

    def __init__(self):
        self.ent = {"name": "Chain Reaction Bikes", "categories": {"fonecta": ["P4630"]}, "meta": {"id": "S"}}
        self._cache = {}
        self.puts = []

    def get_entity(self, sid):
        return json.loads(json.dumps(self.ent))

    def _req(self, method, path, body=None, **_):
        self.puts.append(body)
        for k, v in body.items():
            if v is None:
                self.ent.pop(k, None)
            else:
                self.ent[k] = v


def _run(monkeypatch, tmp_path, fake, *argv):
    monkeypatch.setattr(sd, "OUT", tmp_path)
    monkeypatch.setattr(sd, "_client", lambda env, entity: (fake, "FI-D0001", "S"))
    monkeypatch.setattr(sd, "read_dotenv", dict)
    return sd.main(list(argv))


def test_seed_then_restore_round_trip(monkeypatch, tmp_path):
    fake = FakeYext()
    original = json.loads(json.dumps(fake.ent))
    assert _run(monkeypatch, tmp_path, fake, "seed", "--category", "P9999", "--yes") == 0
    assert fake.ent["name"] == "Kahvila Aurora"
    assert fake.ent["hours"]["wednesday"]["openIntervals"]
    assert fake.ent["categories"]["fonecta"] == ["P9999"]
    # a second seed keeps the true original
    _run(monkeypatch, tmp_path, fake, "seed", "--yes")
    assert _run(monkeypatch, tmp_path, fake, "restore", "--yes") == 0
    assert fake.ent == original and "hours" not in fake.ent


def test_dry_run_changes_nothing(monkeypatch, tmp_path):
    fake = FakeYext()
    assert _run(monkeypatch, tmp_path, fake, "seed", "--category", "P9999") == 0
    assert fake.puts == [] and not list(tmp_path.iterdir())


def test_rename_then_restore_round_trip(monkeypatch, tmp_path):
    fake = FakeYext()
    original = json.loads(json.dumps(fake.ent))
    assert _run(monkeypatch, tmp_path, fake, "rename", "--name", "New Name", "--yes") == 0
    assert fake.ent["name"] == "New Name" and fake.ent["categories"] == original["categories"]
    assert fake.puts == [{"name": "New Name"}]
    assert _run(monkeypatch, tmp_path, fake, "restore", "--yes") == 0
    assert fake.ent["name"] == original["name"]


def test_seed_hours_only_keeps_name_and_category(monkeypatch, tmp_path):
    fake = FakeYext()
    original = json.loads(json.dumps(fake.ent))
    assert _run(monkeypatch, tmp_path, fake, "seed", "--hours-only", "--category", "P9999", "--yes") == 0
    assert fake.puts == [{"hours": fake.ent["hours"]}]
    assert fake.ent["name"] == original["name"] and fake.ent["categories"] == original["categories"]
    assert fake.ent["hours"]["wednesday"]["openIntervals"]
    assert _run(monkeypatch, tmp_path, fake, "restore", "--yes") == 0
    assert fake.ent == original
