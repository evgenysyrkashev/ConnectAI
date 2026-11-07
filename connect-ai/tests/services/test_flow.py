import re

import pytest

from app.server.services import campaigns, review, send, sync
from tests.services.conftest import draft, email_reply, make_world, sent_message
from tests.world import NOW, row, suggest


def test_01_campaign_makes_one_finnish_draft(world):
    _c, msgs = draft(world)
    assert len(msgs) == 1
    m = msgs[0]
    assert m.status == "draft" and m.language == "fi" and m.channel == "email" and m.mode == "ask"
    assert "24.12." in m.body and "kiinni" in m.body and "Vastatkaa vain tähän viestiin" in m.body
    assert m.intro_source == "llm" and m.at_risk_views == 200 and len(m.items) == 2


def test_02_send(world):
    m = sent_message(world)
    assert len(world.mail.outbox) == 1
    out = world.mail.outbox[0]
    assert out["to"] == "tester+fi-t1@test.example" and re.search(r"\+[0-9a-f]{32}@", out["reply_to"])
    assert m.status == "sent" and m.to_email == out["to"] and m.expires_at and m.sent_at
    assert m.escalate_at is not None and m.escalation_basis  # email → permission request later


def test_03_ok_reply_applies(world):
    m = sent_message(world)
    r = email_reply(world, m, "OK")
    assert r.status == "applied" and r.decided_by == "auto" and r.checks.matched_by == "token"
    assert world.yext.holiday("FI-T1", "2026-12-24")["isClosed"] is True
    assert world.yext.holiday("FI-T1", "2026-12-31")["openIntervals"] == [{"start": "10:00", "end": "14:00"}]
    assert r.change_id and world.store.get_change(r.change_id).actor == "auto"
    assert len(world.mail.outbox) == 2
    fu = world.mail.outbox[1]
    assert fu["thread_id"] == world.mail.outbox[0]["thread_id"] and fu["subject"].startswith("Re: ")
    assert "päivittäneet" in fu["text"] and "Google-haku ja Google Maps" in fu["text"]
    assert world.store.get_reply(r.id).followup_sent is True


def test_04_second_reply_is_duplicate(world):
    m = sent_message(world)
    email_reply(world, m, "OK")
    r2 = email_reply(world, m, "OK")
    assert r2.status == "needs_review" and any("already has an applied reply" in p for p in r2.problems)


def test_05_stranger_sender(world):
    m = sent_message(world)
    r = email_reply(world, m, "OK", from_email="stranger@test.example")
    assert r.status == "needs_review" and any("Sender does not match" in p for p in r.problems)
    assert not world.yext.puts


def test_06_failed_auth(world):
    m = sent_message(world)
    r = email_reply(world, m, "OK", auth_pass=False)
    assert r.status == "needs_review" and any("DKIM" in p for p in r.problems)


def test_07_auto_reply_ignored_without_llm(world):
    m = sent_message(world)
    r = email_reply(world, m, "I am away", auto_reply=True)
    assert r.status == "ignored" and world.llm.parse_calls == []


def test_08_thread_only_match_needs_review(world):
    m = sent_message(world)
    r = email_reply(world, m, "OK", token=False)
    assert r.checks.matched_by == "thread" and r.status == "needs_review"
    assert any("thread only" in p for p in r.problems)


def test_09_unrelated_email_unmatched(world):
    sent_message(world)
    r = email_reply(world, type("M", (), {"id": "0" * 16, "subject": "x", "thread_id": None})(), "hello", token=False)
    assert r.status == "unmatched" and r.message_id is None


def test_10_stop_opts_out(world):
    m = sent_message(world)
    r = email_reply(world, m, "STOP")
    assert r.status == "applied" and world.store.get_state("optout-FI-T1")
    assert "Ette saa enää" in world.mail.outbox[-1]["text"]
    _, msgs = draft(world)
    assert msgs[0].status == "skipped" and msgs[0].skip_reason == "opted out"


def test_11_recipient_not_allowlisted(world):
    w = make_world({"RECIPIENT_ALLOWLIST": "@other.example"})
    _, msgs = draft(w)
    res = send.send_message(w.deps, msgs[0].id)
    assert res["status"] == "failed" and res["error"] == "Recipient not in allowlist"
    assert w.mail.outbox == [] and w.store.get_message(msgs[0].id).status == "failed"


def test_12_daily_limit(world):
    w = make_world({"DAILY_SEND_LIMIT": "1"}, eids=("FI-T1", "FI-T2"))
    c, _ = draft(w, eids=("FI-T1", "FI-T2"))
    send.send_campaign(w.deps, c.id, "op")
    statuses = sorted(m.status for m in w.store.list_messages(c.id))
    assert statuses == ["draft", "sent"]
    left = next(m for m in w.store.list_messages(c.id) if m.status == "draft")
    assert left.error == "Daily send limit reached"
    assert w.store.get_campaign(c.id).status == "partially_sent"


def test_13_same_provider_message_twice(world):
    m = sent_message(world)
    pid = world.mail.inject_reply(to=world.cfg.gmail_address, from_email="tester@test.example", text="OK")
    sync.process_provider_message(world.deps, pid)
    sync.process_provider_message(world.deps, pid)
    assert len(world.store.replies) == 1
    _ = m


def test_14_llm_error(world):
    m = sent_message(world)
    r = email_reply(world, m, "[llm-error] hello")
    assert r.status == "needs_review" and "Could not parse reply" in r.problems and r.parsed is None


def test_15_bad_llm_falls_back():
    w = make_world()
    w.yext.entities["FI-T1"]["name"] = "Kahvila [bad-llm]"
    _, msgs = draft(w)
    assert msgs[0].intro_source == "fallback" and msgs[0].intro.startswith("Juhlapyhät lähestyvät")
    assert len(w.llm.intro_calls) == 2  # first try + one retry


def test_16_standing_permission_inform():
    w = make_world()
    w.contacts.c["FI-T1"] = w.contacts.c["FI-T1"].model_copy(update={"standing_permission": True})
    seen = {}
    orig = w.mail.send

    def spy(m):
        seen["applied_before_send"] = w.yext.holiday("FI-T1", "2026-12-24") is not None
        return orig(m)

    w.mail.send = spy
    m = sent_message(w)
    assert m.mode == "inform" and seen["applied_before_send"] and m.auto_change_id and m.escalate_at is None
    assert "olemme jo asettaneet" in m.body
    r = email_reply(w, m, "ei kiitos")
    assert r.status == "needs_review" and any("disputes" in p for p in r.problems)
    before = w.yext.get_entity("FI-T1")["hours"]
    review.revert(w.deps, m.auto_change_id, "op@example.com")
    after = w.yext.get_entity("FI-T1")["hours"]
    assert before["holidayHours"] and after["holidayHours"] == []


def test_17_flag_row_skipped():
    w = make_world()
    w.sugg.add(
        row("FI-T1", "2027-01-01", "NEW_YEARS_DAY"),
        suggest(None, action="FLAG", basis="CLOSED_SIGNALS", text="reviews say closed"),
    )
    _, msgs = draft(w)
    assert msgs[0].status == "skipped" and msgs[0].skip_reason.startswith("flagged")


def test_18_opted_out_skipped():
    w = make_world()
    w.contacts.c["FI-T1"] = w.contacts.c["FI-T1"].model_copy(update={"opted_out": True})
    _, msgs = draft(w)
    assert msgs[0].status == "skipped" and msgs[0].skip_reason == "opted out"


def test_18b_opted_out_gets_no_followup(world):
    m = sent_message(world)
    sent = len(world.mail.outbox)
    world.contacts.c["FI-T1"] = world.contacts.c["FI-T1"].model_copy(update={"opted_out": True})
    email_reply(world, m, "OK")
    assert len(world.mail.outbox) == sent


def test_19_weekly_edit():
    w = make_world()
    w.sugg.stale["FI-T1"] = [{"type": "publisher_suggestion", "date": "2026-11-01", "text": "x"}]
    _, msgs = draft(w, "stale_hours")
    assert msgs[0].kind == "weekly" and msgs[0].status == "draft" and "maanantai: 8–20" in msgs[0].body
    m = sent_message(w, "stale_hours")
    r = email_reply(w, m, "ma-pe 9-17")
    assert r.status == "applied"
    h = w.yext.get_entity("FI-T1")["hours"]
    for d in WEEK5:
        assert h[d]["openIntervals"] == [{"start": "09:00", "end": "17:00"}]
    assert h["saturday"]["openIntervals"] == [{"start": "08:00", "end": "20:00"}]
    assert "maanantai: 9–17" in w.mail.outbox[-1]["text"]


WEEK5 = ("monday", "tuesday", "wednesday", "thursday", "friday")


def test_20_permanently_closed(world):
    m = sent_message(world)
    r = email_reply(world, m, "Olemme lopettaneet pysyvästi")
    assert r.status == "needs_review" and any("closed for good" in p for p in r.problems)


def test_21_edit_one_date(world):
    m = sent_message(world)
    r = email_reply(world, m, "24.12. 10-14")
    assert r.status == "applied"
    assert world.yext.holiday("FI-T1", "2026-12-24")["openIntervals"] == [{"start": "10:00", "end": "14:00"}]


def test_22_yext_failure_then_retry(world):
    m = sent_message(world)
    world.yext.fail_put = "boom"
    r = email_reply(world, m, "OK")
    assert r.status == "error" and "boom" in r.problems[0]
    world.yext.fail_put = None
    r2 = review.retry(world.deps, r.id)
    assert r2.status == "applied" and world.yext.holiday("FI-T1", "2026-12-24")


def test_review_actions(world):
    m = sent_message(world)
    r = email_reply(world, m, "OK", from_email="stranger@test.example")
    with pytest.raises(ValueError):
        review.approve_review(world.deps, "nope", "op")
    ok = review.approve_review(world.deps, r.id, "op@example.com")
    assert ok.status == "applied" and ok.decided_by == "op@example.com"
    r2 = email_reply(world, m, "OK", from_email="stranger@test.example")
    assert review.reject_review(world.deps, r2.id, "op").status == "rejected"


def test_edit_intro_and_regenerate(world):
    _, msgs = draft(world)
    mid = msgs[0].id
    with pytest.raises(ValueError):
        campaigns.edit_intro(world.deps, mid, "Hi", "too short")
    m = campaigns.edit_intro(
        world.deps,
        mid,
        "Aukioloajat juhlapyhinä",
        "Tämä on viesti, ja se koskee teidän aukioloaikojanne. Tarkistakaa tiedot alta.",
    )
    assert m.intro_source == "operator" and "Tarkistakaa tiedot alta" in m.body
    assert campaigns.regenerate(world.deps, mid).intro_source == "llm"
    send.send_message(world.deps, mid)
    with pytest.raises(ValueError):
        campaigns.regenerate(world.deps, mid)


_ = (NOW,)


# ---------------------------------------------------------------- learning from the owner's decisions (brief 04)
def _next_season(world, date="2027-12-24", hours="closed"):
    from tests.world import row, suggest

    world.sugg.add(row("FI-T1", date), suggest(hours))
    c = campaigns.create_campaign(
        world.deps, "holidays", {"date_from": "2027-12-01", "date_to": "2028-01-06"}, ["FI-T1"], "op@example.com"
    )
    return world.store.list_messages(c.id)[0]


def test_edit_is_remembered_for_next_season(world):
    m = sent_message(world)
    assert email_reply(world, m, "24.12. 10-14").status == "applied"
    nxt = _next_season(world)
    item = next(i for i in nxt.items if i.date == "2027-12-24")
    assert (item.suggested_hours, item.basis) == ("10:00-14:00", "OWN_EDIT")
    assert "viimeksi" in item.reason  # Finnish reason text


def test_decline_blocks_the_same_suggestion_next_season(world):
    m = sent_message(world)
    assert email_reply(world, m, "Ei kiitos").status == "applied"
    # the fixture gives both dates the day_key XMAS_EVE; the latest one (2026-12-31, 10-14) is the memory
    nxt = _next_season(world, date="2027-12-31", hours="10:00-14:00")
    assert not [i for i in nxt.items if i.date == "2027-12-31"]
    assert nxt.skip_reason  # nothing else to send, and the reason is recorded
    code = world.store.get_state(f"dropped-{nxt.id}")
    assert code["dropped"][0]["code"] == "owner_declined"
