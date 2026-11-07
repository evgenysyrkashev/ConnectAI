from app.core.models import Permission
from app.server.adapters.llm_fake import FakeLlm
from app.server.services import campaigns, escalation, send
from tests.services import wa_helpers as wh
from tests.services.conftest import draft, email_reply, make_world, sent_message
from tests.world import NOW, row, suggest


def wa_chain_world(analytics=None):
    w = make_world(eids=())
    w.clock.at = NOW.replace(hour=9)
    w.add_entity("FI-T1", channel="WHATSAPP", best_contact_window="10-18")
    if analytics is not None:
        w.yext.analytics_result = analytics
    return w


def run_chain(w):
    """WhatsApp unanswered → +5 h reminder email → +24 h permission request. Returns (wa, reminder, request)."""
    wa = sent_message(w)
    w.clock.advance(5)
    escalation.run_escalations(w.deps)
    reminder = w.store.get_message(w.store.get_message(wa.id).escalated_to)
    w.clock.advance(24)
    escalation.run_escalations(w.deps)
    req_id = w.store.get_message(reminder.id).escalated_to
    return wa, reminder, (w.store.get_message(req_id) if req_id else None)


def test_52_chain_to_permission_request():
    w = wa_chain_world(
        {"GOOGLE_SEARCH_VIEWS": 1000, "GOOGLE_MAP_VIEWS": 234, "GOOGLE_PHONE_CALLS": 12, "GOOGLE_CUSTOMER_ACTIONS": 30}
    )
    _wa, reminder, req = run_chain(w)
    assert (
        reminder.channel == "email"
        and req.template_id == "permission"
        and req.kind == "permission"
        and req.channel == "email"
    )
    assert [i.date for i in req.items] == ["2026-12-24", "2026-12-31"] and req.escalated_from == reminder.id
    assert req.escalate_at is None and req.stats == {"views": 1234, "calls": 12, "actions": 30}
    body = w.mail.outbox[-1]["text"]
    assert "Miksi ajantasaiset aukioloajat" in body and "ehdotamme kiinni" in body and "1 234 kertaa" in body
    assert not any(c.isdigit() for c in req.subject + req.intro + req.short)
    # fewer than 50 views → line left out
    w2 = wa_chain_world({"GOOGLE_SEARCH_VIEWS": 30, "GOOGLE_MAP_VIEWS": 10})
    _, _, req2 = run_chain(w2)
    assert req2.stats is None and "Viime vuonna samalla ajanjaksolla" not in w2.mail.outbox[-1]["text"]


def test_53_yes_grants_and_applies():
    w = wa_chain_world()
    wa, reminder, req = run_chain(w)
    r = email_reply(w, req, "Kyllä")
    assert r.status == "applied"
    perm = Permission.model_validate(w.store.get_state("permission-FI-T1"))
    assert perm.status == "granted" and perm.evidence_text == "Kyllä" and perm.reply_id == r.id
    assert w.yext.holiday("FI-T1", "2026-12-24")["isClosed"] is True
    assert w.store.get_change(r.change_id).actor == "standing_permission"
    assert "Automaattiset päivitykset ovat nyt käytössä" in w.mail.outbox[-1]["text"]
    assert (
        w.store.get_message(wa.id).superseded_by == req.id and w.store.get_message(reminder.id).superseded_by == req.id
    )


def test_54_next_campaign_is_inform():
    w = wa_chain_world()
    _, _, req = run_chain(w)
    email_reply(w, req, "Kyllä")
    w.sugg.add(row("FI-T1", "2027-01-02", "XMAS_EVE"), suggest("closed"))
    _, msgs = draft(w)
    assert msgs[0].mode == "inform" and [i.date for i in msgs[0].items] == ["2027-01-02"]


def test_55_no_declines_and_never_asks_again():
    w = wa_chain_world()
    _, _, req = run_chain(w)
    r = email_reply(w, req, "Ei")
    assert r.status == "applied" and w.store.get_state("permission-FI-T1")["status"] == "declined"
    assert "kysymme jatkossakin" in w.mail.outbox[-1]["text"] and not w.yext.puts
    w.clock.advance(200 * 24)
    w.sugg.add(row("FI-T1", "2027-06-01", "XMAS_EVE"), suggest("closed"))
    c = campaigns.create_campaign(w.deps, "holidays", {"date_to": "2027-12-31"}, ["FI-T1"], "op")
    m = w.store.list_messages(c.id)[0]
    assert m.status == "draft" and m.channel == "whatsapp"
    send.send_message(w.deps, m.id)
    n = len(w.mail.outbox)
    w.clock.advance(30)
    escalation.run_escalations(w.deps)  # reminder email
    w.clock.advance(30)
    escalation.run_escalations(w.deps)
    assert len(w.mail.outbox) == n + 1  # the reminder only, never a permission request
    assert not any(x.template_id == "permission" and x.created_at > "2027" for x in w.store.messages.values())


def test_56_second_chain_within_ask_window():
    w = wa_chain_world()
    _, _, req = run_chain(w)
    assert req is not None
    w.clock.advance(5 * 24)
    w.sugg.add(row("FI-T1", "2027-01-03", "XMAS_EVE"), suggest("closed"))
    sent_message(w)
    sent_before = len(w.mail.outbox)
    w.clock.advance(5)
    escalation.run_escalations(w.deps)
    w.clock.advance(24)
    escalation.run_escalations(w.deps)
    assert len(w.mail.outbox) == sent_before + 1
    assert len([m for m in w.store.messages.values() if m.template_id == "permission"]) == 1


def test_57_nothing_pending_no_request():
    w = make_world()
    m = sent_message(w)
    for d in ("2026-12-24", "2026-12-31"):
        w.yext.enter_holiday("FI-T1", {"date": d, "isClosed": True})
    w.clock.advance(24)
    escalation.run_escalations(w.deps)
    assert len(w.mail.outbox) == 1 and w.store.get_state(f"escalation-note-{m.id}")["reason"] == "no_longer_needed"


def test_58_weekly_chain_no_permission():
    w = make_world()
    w.sugg.stale["FI-T1"] = [{"type": "review", "date": "2026-10-01", "text": "x"}]
    m = sent_message(w, "stale_hours")
    w.clock.advance(24)
    escalation.run_escalations(w.deps)
    assert len(w.mail.outbox) == 1 and w.store.get_state(f"escalation-note-{m.id}")["reason"] == "not_applicable"


def test_59_manual_revokes():
    w = make_world()
    w.contacts.c["FI-T1"] = w.contacts.c["FI-T1"].model_copy(update={"standing_permission": True})
    m = sent_message(w)
    assert m.mode == "inform"
    r = email_reply(w, m, "MANUAL")
    assert r.status == "applied" and w.store.get_state("permission-FI-T1")["status"] == "revoked"
    w.sugg.add(row("FI-T1", "2027-01-02", "XMAS_EVE"), suggest("closed"))
    _, msgs = draft(w)
    assert msgs[0].mode == "ask"


def test_60_auto_offer_and_grant():
    w = make_world()
    m = sent_message(w)
    r = email_reply(w, m, "OK")
    assert r.status == "applied" and "AUTOMAATTINEN" in w.mail.outbox[-1]["text"]
    calls = len(w.llm.parse_calls)
    r2 = email_reply(w, m, "AUTO")
    assert r2.status == "applied" and len(w.llm.parse_calls) == calls
    assert w.store.get_state("permission-FI-T1")["status"] == "granted"
    # declined earlier → no AUTO line
    w2 = make_world()
    w2.store.set_state(
        "permission-FI-T1",
        Permission(status="declined", at="x", message_id=None, reply_id=None, evidence_text="no").model_dump(),
    )
    m2 = sent_message(w2)
    email_reply(w2, m2, "OK")
    assert "AUTOMAATTINEN" not in w2.mail.outbox[-1]["text"]


class PercentLlm(FakeLlm):
    def write_intro(self, inp):
        out = super().write_intro(inp)
        if inp.template_id == "permission":
            out["intro"] += " Tämä voi tuoda 30 % lisää kävijöitä ja se on hyvä."
        return out


def test_61_percent_in_permission_intro_rejected():
    w = wa_chain_world()
    w.llm = PercentLlm()
    w.deps.llm = w.llm
    _, _, req = run_chain(w)
    assert req.intro_source == "fallback" and "30" not in req.intro
    assert len([c for c in w.llm.intro_calls if c.template_id == "permission"]) == 2
    _ = wh
