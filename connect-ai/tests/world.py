"""Test world: FakeYext, fixtures and helpers shared by the service tests."""

from __future__ import annotations

import copy
from datetime import UTC, datetime

from app import kit
from app.core.models import Contact
from app.server.adapters.clock import FixedClock
from app.server.adapters.findability_fake import FakeFindability
from app.server.adapters.llm_fake import FakeLlm
from app.server.adapters.mail_fake import FakeMail
from app.server.adapters.response_stats import ResponseStats
from app.server.adapters.sms_sim import SimSms
from app.server.adapters.store_memory import MemoryStore
from app.server.adapters.suggestions_fake import FakeSuggestions
from app.server.adapters.wa_fake import FakeWhatsApp
from app.server.config import load_config
from app.server.ports import Detection, TargetRow, YextError
from app.server.services.common import Deps

NOW = datetime(2026, 11, 6, 10, 0, tzinfo=UTC)
WEEK = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

LISTINGS = [
    {"entityId": "FI-T1", "publisherId": "GOOGLEMYBUSINESS", "status": "LIVE", "typicalUpdateSpeedSeconds": 120},
    {"entityId": "FI-T1", "publisherId": "APPLE", "status": "LIVE", "typicalUpdateSpeedSeconds": 172800},
]


def entity(eid="FI-T1", name="Kahvila Testi", lang="fi", country="FI", closed=False) -> dict:
    return {
        "meta": {"id": eid, "countryCode": country, "language": lang},
        "name": name,
        "address": {"city": "Helsinki"},
        "c_segment": "cafe",
        "timezone": "Europe/Helsinki",
        "closed": closed,
        "hours": {**{d: {"openIntervals": [{"start": "08:00", "end": "20:00"}]} for d in WEEK}, "holidayHours": []},
    }


class FakeYext:
    def __init__(self) -> None:
        self.entities: dict[str, dict] = {}
        self.fail_put: str | None = None
        self.puts: list[tuple[str, dict]] = []
        self.analytics_result: dict[str, int] = {}
        self.listing_rows = LISTINGS

    def add(self, ent: dict) -> None:
        self.entities[ent["meta"]["id"]] = ent

    def get_entity(self, eid: str) -> dict:
        return copy.deepcopy(self.entities[eid])

    def list_entities(self, ids: list[str]) -> list[dict]:
        return [self.get_entity(i) for i in ids if i in self.entities]

    def put_hours(self, eid: str, hours: dict) -> dict:
        if self.fail_put:
            raise YextError(self.fail_put)
        errs = kit.mock_server_module().validate_hours(hours)
        if errs:
            raise YextError("; ".join(errs))
        self.entities[eid]["hours"] = copy.deepcopy(hours)
        self.puts.append((eid, copy.deepcopy(hours)))
        return {"ok": True}

    def listings(self, eid: str) -> list[dict]:
        return list(self.listing_rows)

    def analytics(self, eid: str, start: str, end: str, metrics: list[str]) -> dict[str, int]:
        return dict(self.analytics_result)

    # test helpers
    def holiday(self, eid: str, date: str) -> dict | None:
        return next((h for h in self.entities[eid]["hours"].get("holidayHours", []) if h["date"] == date), None)

    def enter_holiday(self, eid: str, item: dict) -> None:
        self.entities[eid]["hours"].setdefault("holidayHours", []).append(item)


class FakeOwnerSim:
    def __init__(self, decision="ACCEPTED"):
        self.decision = decision

    def respond(self, eid: str, date: str, proposed_hours: str) -> dict:
        return {"decision": self.decision, "final_hours": proposed_hours if self.decision != "NO_RESPONSE" else None}


class FakeContacts:
    def __init__(self) -> None:
        self.c: dict[str, Contact] = {}
        self.raw: dict[str, str] = {}

    def add(self, eid: str, *, lang="fi", raw_lang: str | None = None, channel="EMAIL", **kw) -> Contact:
        base = {
            "entity_id": eid,
            "first_name": "Maria",
            "preferred_channel": channel,
            "language": lang,
            "email": f"owner+{eid.lower()}@example.com",
            "mobile": "+358401111111",
            "best_contact_window": "10-18",
            "standing_permission": False,
            "opted_out": False,
        }
        base.update(kw)
        self.c[eid] = Contact(**base)
        self.raw[eid] = raw_lang if raw_lang is not None else lang
        return self.c[eid]

    def get(self, eid: str) -> Contact | None:
        return self.c[eid].model_copy() if eid in self.c else None

    def raw_language(self, eid: str) -> str | None:
        return self.raw.get(eid)


def row(eid: str, date: str, key="XMAS_EVE", day_type="PUBLIC_HOLIDAY", country="FI") -> TargetRow:
    return TargetRow(entity_id=eid, date=date, day_key=key, day_type=day_type, country=country, split="dev")


def suggest(hours: str | None, shown="08:00-20:00", basis="LAST_YEAR", action="SUGGEST", **evidence) -> Detection:
    return Detection(
        action=action,
        suggested_hours=hours,
        shown_hours=shown,
        shown_source="regular",
        basis=basis,
        evidence=evidence or ({"last_year_hours": hours} if hours else {}),
    )


class World:
    """Everything a service test needs, plus handy shortcuts."""

    def __init__(self, env: dict[str, str] | None = None, eids=("FI-T1",)):
        e = {
            "DEMO_RECIPIENT_TEMPLATE": "tester+{entity}@test.example",
            "RECIPIENT_ALLOWLIST": "@test.example",
            "DEMO_PHONE_MAP": "*=+358401111111",
            "PHONE_ALLOWLIST": "+358401111111",
            "FINDABILITY_MODE": "fake",
            "SUGGESTIONS_MODE": "fake",
            "WA_APP_SECRET": "wa-secret",
            "WA_VERIFY_TOKEN": "verify-me",
        }
        e.update(env or {})
        self.cfg = load_config(e)
        self.store = MemoryStore()
        self.mail = FakeMail(self.cfg.gmail_address)
        self.llm = FakeLlm()
        self.yext = FakeYext()
        self.contacts = FakeContacts()
        self.sugg = FakeSuggestions()
        self.find = FakeFindability(default_est=100)
        self.clock = FixedClock(NOW)
        self.wa = FakeWhatsApp()
        self.deps = Deps(
            cfg=self.cfg,
            store=self.store,
            mail=self.mail,
            llm=self.llm,
            yext=self.yext,
            contacts=self.contacts,
            suggestions=self.sugg,
            findability=self.find,
            clock=self.clock,
            stats=ResponseStats(self.store, {"WHATSAPP": 0.4, "SMS": 1.1, "EMAIL": 9.4, "APP_PUSH": 5.2}),
            whatsapp=self.wa,
            sms=SimSms(self.store, self.clock),
            owner_sim=FakeOwnerSim(),
        )
        for eid in eids:
            self.add_entity(eid)

    def add_entity(
        self,
        eid: str,
        name="Kahvila Testi",
        lang="fi",
        channel="EMAIL",
        items=((("2026-12-24", "closed"), ("2026-12-31", "10:00-14:00"))),
        **contact_kw,
    ):
        self.yext.add(entity(eid, name=name, lang=lang))
        self.contacts.add(eid, lang=lang, channel=channel, **contact_kw)
        for d, h in items[0] if items and isinstance(items[0][0], tuple) else items:
            self.sugg.add(row(eid, d), suggest(h))
        return eid
