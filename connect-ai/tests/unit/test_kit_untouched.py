import hashlib
import json
import os

import pytest

from app import kit

pytestmark = pytest.mark.skipif(
    not os.path.exists(kit.data_path("data", "entities.json")), reason="kit data/ folder not present"
)


def test_kit_files_match_manifest():
    with open(kit.data_path("MANIFEST.json")) as f:
        manifest = json.load(f)
    bad = []
    for item in manifest:
        path = kit.data_path(item["path"])
        if not os.path.exists(path):
            bad.append(f"missing: {item['path']}")
            continue
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        if h.hexdigest() != item["sha256"]:
            bad.append(f"changed: {item['path']}")
    assert not bad, bad
