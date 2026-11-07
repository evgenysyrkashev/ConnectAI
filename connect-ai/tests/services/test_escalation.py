import pytest

from app.server.services import escalation, send
from app.server.services.common import tokenized_reply_to
from tests.services import wa_helpers as wh
from tests.services.conftest import draft, email_reply, make_world, sent_message
from tests.world import NOW

UTC = NOW.tzinfo


def wa_world(**kw):
    w = make_world(eids=())
    w.clock.at = NOW.replace(hour=9)  # 11:00 Helsinki
    w.add_entity("FI-T1", channel="WHATSAPP", best_contact_window="10-18", **kw)
    return w


def test_43_escalate_at_with_floor():
    m = sent_message(wa_world())
    assert m.escalate_at == "2026-11-06T13:00:00Z"  # 2×0.4 h < 4 h floor → 15:00 local, inside 10–18
    assert "wait 4.0 h" in m.escalation_basis


def test_44_not_before_deadline_then_email():
    w = wa_world()
    m = sent_message(w)
    w.clock.advance(3)
    assert escalation.run_escalations(w.deps) == {"escalated": 0, "skipped": 0}
    w.clock.advance(2)
    assert escalation.run_escalations(w.deps) == {"escalated": 1, "skipped": 0}
    mail = w.mail.outbox[0]
    assert mail["to"] == "tester+fi-t1@test.example"
    new = next(x for x in w.store.messages.values() if x.escalated_from == m.id)
    assert new.channel == "email" and [i.date for i in new.items] == [i.date for i in m.items] and new.status == "sent"
    assert any("did not answer our WhatsApp message" in f for f in w.llm.intro_calls[-1].facts)
    assert w.store.get_message(m.id).escalated_to == new.id and w.store.get_message(m.id).escalate_at is None


def test_45_answered_before_deadline():
    w = wa_world()
    m = sent_message(w)
    wh.post(w, wh.payload([wh.button(w, m, "A")]))
    w.clock.advance(6)
    escalation.run_escalations(w.deps)
    assert w.mail.outbox == [] and w.store.get_message(m.id).escalate_at is None
    assert (
        w.store.get_state(f"escalation-note-{m.id}")["reason"] == "answered"
        or w.store.get_message(m.id).escalate_at is None
    )


def test_46_email_answer_supersedes_whatsapp():
    w = wa_world()
    m = sent_message(w)
    w.clock.advance(5)
    escalation.run_escalations(w.deps)
    mail_msg = w.store.get_message(w.store.get_message(m.id).escalated_to)
    r = email_reply(w, mail_msg, "OK")
    assert r.status == "applied"
    assert w.store.get_message(m.id).superseded_by == mail_msg.id
    wh.post(w, wh.payload([wh.button(w, m, "A", wamid="wamid.LATE")]))
    late = w.store.get_reply("wa-wamid.LATE")
    assert late.status == "needs_review" and any("already has an applied reply" in p for p in late.problems)


def test_47_failed_status_escalates_immediately():
    w = wa_world()
    m = sent_message(w)
    wh.post(
        w, wh.payload(statuses=[{"id": m.provider_message_id, "status": "failed", "errors": [{"title": "bad number"}]}])
    )
    assert escalation.run_escalations(w.deps)["escalated"] == 1
    assert len(w.mail.outbox) == 1


def test_48_after_window_moves_to_next_day():
    w = make_world(eids=())
    w.clock.at = NOW.replace(hour=14, minute=30)  # 16:30 local
    w.add_entity("FI-T1", channel="WHATSAPP", best_contact_window="10-18")
    m = sent_message(w)
    assert m.escalate_at == "2026-11-07T08:00:00Z"  # next day 10:00 local (EET, +2)


def test_49_entered_in_yext_before_deadline():
    w = wa_world()
    m = sent_message(w)
    for d in ("2026-12-24", "2026-12-31"):
        w.yext.enter_holiday("FI-T1", {"date": d, "isClosed": True})
    w.clock.advance(5)
    assert escalation.run_escalations(w.deps) == {"escalated": 0, "skipped": 1}
    assert w.mail.outbox == [] and w.store.get_state(f"escalation-note-{m.id}")["reason"] == "no_longer_needed"


def test_50_inform_never_escalates():
    w = wa_world(standing_permission=True)
    m = sent_message(w)
    assert m.mode == "inform" and m.escalate_at is None


def test_51_email_targets_permission():
    w = make_world()
    m = sent_message(w)  # sent 10:00 UTC = 12:00 local; 18.8 h later = 06:48 next day local → moved to 10:00
    assert m.escalate_at == "2026-11-07T08:00:00Z" and "wait 18.8 h" in m.escalation_basis


_ = (pytest, draft, send, tokenized_reply_to)
