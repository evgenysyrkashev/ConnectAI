from app.server.services import send
from app.server.services.common import dropped_key
from tests.services.conftest import draft, make_world
from tests.world import NOW, row, suggest

_ = NOW


def test_36_no_action_only_is_quiet():
    w = make_world(eids=())
    w.add_entity("FI-T1", items=())
    w.sugg.add(row("FI-T1", "2026-12-24"), suggest(None, action="NO_ACTION", basis=None))
    _, msgs = draft(w)
    assert msgs[0].status == "skipped" and msgs[0].skip_reason == "no_evidence" and w.llm.intro_calls == []


def test_37_already_entered_dropped_and_listed():
    w = make_world()
    w.yext.enter_holiday("FI-T1", {"date": "2026-12-24", "isClosed": True})
    _, msgs = draft(w)
    m = msgs[0]
    assert [i.date for i in m.items] == ["2026-12-31"]
    assert w.store.get_state(dropped_key(m.id))["dropped"] == [{"date": "2026-12-24", "code": "already_entered"}]


def test_38_second_campaign_already_asked():
    w = make_world()
    _, msgs = draft(w)
    send.send_message(w.deps, msgs[0].id)
    w.clock.advance(24)
    _, again = draft(w)
    assert again[0].status == "skipped" and again[0].skip_reason == "already_asked"


def test_39_entered_between_draft_and_send():
    w = make_world()
    _, msgs = draft(w)
    for d in ("2026-12-24", "2026-12-31"):
        w.yext.enter_holiday("FI-T1", {"date": d, "isClosed": True})
    res = send.send_message(w.deps, msgs[0].id)
    assert res["status"] == "skipped" and w.store.get_message(msgs[0].id).skip_reason == "no_longer_needed"
    assert w.mail.outbox == []


def test_39b_partial_drop_at_send_recomposes():
    w = make_world()
    _, msgs = draft(w)
    w.yext.enter_holiday("FI-T1", {"date": "2026-12-24", "isClosed": True})
    assert send.send_message(w.deps, msgs[0].id)["status"] == "sent"
    m = w.store.get_message(msgs[0].id)
    assert [i.date for i in m.items] == ["2026-12-31"] and "24.12." not in w.mail.outbox[0]["text"]


def test_40_event_rows():
    w = make_world(eids=())
    w.add_entity("FI-T1", items=())
    ev = row("FI-T1", "2026-12-12", key="EVENT", day_type="LOCAL_EVENT")
    ev = ev.model_copy(update={"event_id": "ev:1"})
    w.sugg.events["ev:1"] = {
        "@id": "ev:1",
        "name": {"fi": "Konsertti", "en": "Concert"},
        "location": {"name": {"en": "Areena"}},
        "x_expected_attendance": 9839,
    }
    det = suggest("closed", basis="LAST_EVENT")
    det.evidence = {"hours": "closed"}
    w.sugg.add(ev, det, day_name=("x", "x"))
    _, msgs = draft(w, "event")
    m = msgs[0]
    assert m.status == "draft" and m.items[0].reason == "(Aiempina tapahtumailtoina olitte kiinni.)"
    assert any("Konsertti" in f for f in w.llm.intro_calls[0].facts) and any(
        "about 9800" in f for f in w.llm.intro_calls[0].facts
    )
    w2 = make_world(eids=())
    w2.add_entity("FI-T1", items=())
    w2.sugg.add(ev, suggest(None, action="NO_ACTION", basis=None), day_name=("x", "x"))
    _, none = draft(w2, "event")
    assert none[0].status == "skipped"


def _ask_world(share, n=20, have_peer=True, day_class="MAJOR", history=False):
    w = make_world(eids=())
    w.add_entity("FI-T1", items=())
    r = row("FI-T1", "2026-12-24")
    w.sugg.add(r, suggest(None, action="NO_ACTION", basis=None), day_class=day_class)
    if have_peer:
        w.sugg.peer[("FI-T1", "2026-12-24")] = (share, n)
    if history:
        w.sugg.history.add("FI-T1")
    return w


def test_41_new_customer_ask_items():
    _, ok = draft(_ask_world(0.5))
    assert ok[0].status == "draft" and ok[0].items[0].suggested_hours is None
    assert "Mitkä ovat aukioloaikanne" in ok[0].body and "Vastatkaa tähän viestiin aukioloajoillanne" in ok[0].body
    assert draft(_ask_world(0.1))[1][0].status == "skipped"
    assert draft(_ask_world(0.5, have_peer=False))[1][0].status == "skipped"
    assert draft(_ask_world(0.5, n=5))[1][0].status == "skipped"
    assert draft(_ask_world(0.5, day_class="SOFT"))[1][0].status == "skipped"
    assert draft(_ask_world(0.5, history=True))[1][0].status == "skipped"


def test_42_stale_hours_needs_evidence():
    w = make_world()
    _, msgs = draft(w, "stale_hours")
    assert msgs[0].status == "skipped" and msgs[0].skip_reason == "no_evidence"
    w.sugg.stale["FI-T1"] = [{"type": "publisher_suggestion", "date": "2026-11-01", "text": "x"}]
    _, msgs = draft(w, "stale_hours")
    assert msgs[0].status == "draft" and msgs[0].kind == "weekly"
    facts = w.llm.intro_calls[-1].facts
    assert facts == ["Google users have suggested different opening hours for this business"]


def test_closed_and_no_contact():
    w = make_world()
    w.yext.entities["FI-T1"]["closed"] = True
    assert draft(w)[1][0].skip_reason == "closed in Yext"
    w2 = make_world()
    del w2.contacts.c["FI-T1"]
    assert draft(w2)[1][0].skip_reason == "no contact"
