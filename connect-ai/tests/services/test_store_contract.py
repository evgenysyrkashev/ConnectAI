"""The same behaviour for MemoryStore and FirestoreStore (run against an in-memory Firestore fake)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.core.models import Campaign, DateDecision, ParsedReply, Reply, ReplyChecks, YextChange
from app.server.adapters.store_firestore import FirestoreStore
from app.server.adapters.store_memory import MemoryStore
from tests.conftest import make_item, make_message
from tests.fake_firestore import FakeFirestore


@pytest.fixture(params=["memory", "firestore"])
def store(request):
    if request.param == "memory":
        return MemoryStore()
    return FirestoreStore(FakeFirestore(), transactional=lambda f: f)


def reply(rid="r1", message_id="m1", status="processing", **kw) -> Reply:
    base = {
        "id": rid,
        "message_id": message_id,
        "entity_id": "FI-T1",
        "source": "email",
        "sender": "a@b.c",
        "subject": "s",
        "received_at": "2026-11-06T10:00:00Z",
        "rfc_message_id": None,
        "cleaned_text": "ok",
        "status": status,
        "created_at": f"2026-11-06T10:00:0{rid[-1]}Z",
        "expire_at": datetime(2027, 2, 1, tzinfo=UTC),
    }
    base.update(kw)
    return Reply(**base)


def test_campaigns(store):
    for i in (1, 2):
        store.create_campaign(
            Campaign(
                id=f"c{i}",
                template_id="holidays",
                params={"a": 1},
                entity_ids=["x"],
                created_by="op",
                created_at=f"2026-11-0{i}T00:00:00Z",
                status="draft",
            )
        )
    assert [c.id for c in store.list_campaigns(10)] == ["c2", "c1"] and len(store.list_campaigns(1)) == 1
    store.update_campaign("c1", status="sent")
    assert store.get_campaign("c1").status == "sent" and store.get_campaign("nope") is None


def test_messages_roundtrip_and_update_with_models(store):
    m = make_message(id="m1", campaign_id="c1", thread_id="t1", provider_message_id="p1")
    store.create_message(m)
    got = store.get_message("m1")
    assert got == m and got.items[0].day_name == "Jouluaatto"
    store.update_message("m1", items=[make_item("2027-01-01", "closed")], status="sent", sent_at="2026-11-06T10:00:00Z")
    got = store.get_message("m1")
    assert got.items[0].date == "2027-01-01" and got.status == "sent"
    assert store.find_message_by_thread("t1").id == "m1" and store.find_message_by_provider_id("p1").id == "m1"
    assert store.find_message_by_thread("zz") is None
    store.create_message(make_message(id="m2", campaign_id="c1", created_at="2026-11-07T00:00:00Z", entity_id="FI-T2"))
    assert [x.id for x in store.list_messages("c1")] == ["m1", "m2"]
    assert [x.id for x in store.list_messages_for_entity("FI-T2", 5)] == ["m2"]


def test_claim_is_atomic(store):
    store.create_message(make_message(id="m1"))
    assert store.claim_message_for_sending("m1") is True
    assert store.claim_message_for_sending("m1") is False
    assert store.get_message("m1").status == "sending"
    store.update_message("m1", status="failed")
    assert store.claim_message_for_sending("m1") is True
    assert store.claim_message_for_sending("nope") is False


def test_daily_sends(store):
    assert [store.try_increment_daily_sends("2026-11-06", 2) for _ in range(3)] == [True, True, False]
    assert store.try_increment_daily_sends("2026-11-07", 2) is True


def test_due_escalations(store):
    store.create_message(make_message(id="m1", status="sent", escalate_at="2026-11-06T12:00:00Z"))
    store.create_message(make_message(id="m2", status="sent", escalate_at="2026-11-06T09:00:00Z", escalated_to="x"))
    store.create_message(make_message(id="m3", status="sent", escalate_at="2026-11-06T09:00:00Z", superseded_by="x"))
    store.create_message(make_message(id="m4", status="draft", escalate_at="2026-11-06T09:00:00Z"))
    store.create_message(make_message(id="m5", status="sent"))
    assert store.list_due_escalations("2026-11-06T11:00:00Z") == []
    assert [m.id for m in store.list_due_escalations("2026-11-06T12:00:00Z")] == ["m1"]


def test_open_messages_by_phone(store):
    far = (datetime.now(UTC) + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    past = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    kw = {"status": "sent", "channel": "whatsapp", "to_phone_digits": "358401", "expires_at": far}
    store.create_message(make_message(id="m1", sent_at="2026-11-06T10:00:00Z", **kw))
    store.create_message(make_message(id="m2", sent_at="2026-11-06T11:00:00Z", **kw))
    store.create_message(make_message(id="m3", sent_at="2026-11-06T12:00:00Z", **{**kw, "expires_at": past}))
    store.create_message(make_message(id="m4", sent_at="2026-11-06T12:00:00Z", **{**kw, "channel": "sms"}))
    store.create_reply_if_absent(reply("r1", "m2", "applied"))
    assert [m.id for m in store.find_open_messages_by_phone("358401", "whatsapp")] == ["m1"]
    assert store.find_open_messages_by_phone("999", "whatsapp") == []


def test_replies(store):
    assert store.create_reply_if_absent(reply("r1", "m1")) is True
    assert store.create_reply_if_absent(reply("r1", "m1")) is False
    store.create_reply_if_absent(reply("r2", "m1", "needs_review"))
    store.update_reply(
        "r1",
        status="applied",
        parsed=ParsedReply(intent="approve", summary="s", confidence=0.9),
        decisions=[DateDecision(date="2026-12-24", action="accept")],
        checks=ReplyChecks(
            token_valid=True,
            matched_by="token",
            sender_matches=True,
            auth_pass=True,
            auto_reply=False,
            expired=False,
            duplicate=False,
        ),
    )
    got = store.get_reply("r1")
    assert got.status == "applied" and got.parsed.intent == "approve" and got.decisions[0].action == "accept"
    assert got.checks.matched_by == "token" and got.expire_at.year == 2027
    assert store.has_applied_reply("m1") and not store.has_applied_reply("m9")
    assert [r.id for r in store.list_replies(None, 10)] == ["r2", "r1"]
    assert [r.id for r in store.list_replies("needs_review", 10)] == ["r2"]
    assert [r.id for r in store.list_replies_for_message("m1")] == ["r1", "r2"]


def test_changes_state_sms(store):
    ch = YextChange(
        id="c1",
        entity_id="FI-T1",
        message_id="m1",
        reply_id=None,
        actor="auto",
        before={"x": {"a": None}},
        after={"x": {"a": 1}},
        created_at="2026-11-06T10:00:00Z",
    )
    store.create_change(ch)
    store.update_change("c1", reverted_at="2026-11-07T00:00:00Z")
    assert store.get_change("c1").reverted_at and store.get_change("zz") is None
    assert [c.id for c in store.list_changes_for_entity("FI-T1")] == ["c1"]
    assert store.get_state("k") is None
    store.set_state("k", {"a": 1})
    assert store.get_state("k") == {"a": 1}
    store.append_sms(
        {"id": "s2", "direction": "in", "phone": "+1", "text": "b", "at": "2026-11-06T10:01:00Z", "message_id": None}
    )
    store.append_sms(
        {"id": "s1", "direction": "out", "phone": "+1", "text": "a", "at": "2026-11-06T10:00:00Z", "message_id": "m1"}
    )
    store.append_sms(
        {"id": "s3", "direction": "out", "phone": "+2", "text": "c", "at": "2026-11-06T10:02:00Z", "message_id": "m1"}
    )
    assert [e["id"] for e in store.list_sms("+1")] == ["s1", "s2"] and len(store.list_sms(None)) == 3
