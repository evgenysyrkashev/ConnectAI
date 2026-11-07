import os

import pytest

from app import kit
from app.core.models import Contact, DateItem, OutboundMessage

NOW = "2026-11-06T10:00:00Z"
KIT_MINI = os.path.join(os.path.dirname(__file__), "fixtures", "kit_mini")


@pytest.fixture(autouse=True)
def _kit_data_fallback(monkeypatch):
    """Use the tiny excerpt in tests/fixtures/kit_mini when the real kit data/<file> is not present."""
    real = kit.data_path

    def data_path(*parts: str) -> str:
        path = real(*parts)
        if parts and parts[0] == "data" and not os.path.exists(path):
            mini = os.path.join(KIT_MINI, *parts)
            if os.path.exists(mini):
                return mini
        return path

    monkeypatch.setattr(kit, "data_path", data_path)


def make_contact(lang="fi", channel="EMAIL", **kw) -> Contact:
    base = {
        "entity_id": "FI-T1",
        "first_name": "Maria",
        "preferred_channel": channel,
        "language": lang,
        "email": "owner@example.com",
        "mobile": "+358401111111",
        "best_contact_window": "10-18",
        "standing_permission": False,
        "opted_out": False,
    }
    base.update(kw)
    return Contact(**base)


def make_item(date="2026-12-24", suggested="closed", shown="08:00-20:00", **kw) -> DateItem:
    base = {
        "date": date,
        "day_key": "XMAS_EVE",
        "day_name": "Jouluaatto",
        "shown_hours": shown,
        "shown_source": "regular",
        "suggested_hours": suggested,
        "basis": "LAST_YEAR" if suggested else None,
        "reason": "",
        "est_views": 100,
        "priority": 80.0,
    }
    base.update(kw)
    return DateItem(**base)


def make_message(items=None, kind="dates", mode="ask", lang="fi", **kw) -> OutboundMessage:
    if items is None:
        items = [make_item("2026-12-24", "closed"), make_item("2026-12-31", "10:00-14:00")]
    base = {
        "id": "a" * 16,
        "campaign_id": "c1",
        "entity_id": "FI-T1",
        "entity_name": "Kahvila Testi",
        "country": "FI",
        "template_id": "holidays" if kind == "dates" else "stale_hours",
        "kind": kind,
        "language": lang,
        "mode": mode,
        "contact_email": "owner@example.com",
        "to_email": "tester@test.example",
        "subject": "Subject here",
        "intro": "Intro text goes here for the owner.",
        "intro_source": "fallback",
        "body": "",
        "items": items if kind != "weekly" else [],
        "weekly_shown": None
        if kind != "weekly"
        else {d: "09:00-17:00" for d in ("monday", "tuesday", "wednesday", "thursday", "friday")}
        | {"saturday": "closed", "sunday": "closed"},
        "status": "draft",
        "created_at": NOW,
        "short": "",
    }
    base.update(kw)
    return OutboundMessage(**base)


@pytest.fixture
def contact():
    return make_contact()


@pytest.fixture
def message():
    return make_message()
