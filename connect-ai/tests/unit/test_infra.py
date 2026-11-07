"""Deploy helpers: the webhooks-only mail stand-in and the wipe script."""

import pytest

from scripts import wipe_staging
from tests.fake_firestore import FakeFirestore


def test_webhooks_role_builds_without_gmail(monkeypatch):
    from app.server.adapters.mail_unavailable import UnavailableMail

    um = UnavailableMail()
    assert um.list_unprocessed(5) == [] and um.renew_watch() is None
    with pytest.raises(RuntimeError):
        um.get_raw("x")


def test_wipe_requires_typed_project_id():
    db = FakeFirestore()
    for c in wipe_staging.COLLECTIONS:
        for i in range(3):
            db.collection(c).document(f"{c}{i}").set({"a": i})
    with pytest.raises(SystemExit):
        wipe_staging.wipe(db, "my-project", "wrong")
    assert all(len(db.data[c]) == 3 for c in wipe_staging.COLLECTIONS)
    counts = wipe_staging.wipe(db, "my-project", "my-project")
    assert set(counts.values()) == {3} and all(not db.data[c] for c in wipe_staging.COLLECTIONS)
