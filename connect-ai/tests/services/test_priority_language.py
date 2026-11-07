from app.server.adapters.findability_fake import FakeFindability
from app.server.adapters.llm_fake import FakeLlm
from app.server.services import campaigns, send
from tests.services import wa_helpers as wh
from tests.services.conftest import draft, email_reply, make_world, sent_message
from tests.world import row, suggest


def test_62_keeps_all_items_listed_by_date():
    w = make_world(eids=())
    w.add_entity("FI-T1", items=())
    views = [10, 80, 20, 70, 30, 60, 40, 50]
    for i, v in enumerate(views):
        d = f"2026-12-{10 + i}"
        w.sugg.add(row("FI-T1", d), suggest("closed"))
        w.find.est[("FI-T1", d)] = v
    _, msgs = draft(w)
    dates = [i.date for i in msgs[0].items]
    assert dates == sorted(dates) and len(dates) == 8  # no cap


def test_63_send_order_by_priority_with_daily_limit():
    w = make_world({"DAILY_SEND_LIMIT": "2"}, eids=("FI-T1", "FI-T2", "FI-T3"))
    for eid, v in (("FI-T1", 100), ("FI-T2", 1000), ("FI-T3", 10)):
        for d in ("2026-12-24", "2026-12-31"):
            w.find.est[(eid, d)] = v
    c, _ = draft(w, eids=("FI-T1", "FI-T2", "FI-T3"))
    send.send_campaign(w.deps, c.id, "op")
    by = {m.entity_id: m for m in w.store.list_messages(c.id)}
    assert by["FI-T2"].status == "sent" and by["FI-T1"].status == "sent"
    assert by["FI-T3"].status == "draft" and by["FI-T3"].error == "Daily send limit reached"


def test_64_sms_drops_lowest_priority_first():
    w = make_world(eids=())
    w.add_entity("FI-T1", name="K" * 200, channel="SMS", items=())
    for i, v in enumerate([5, 90, 50, 70, 60, 80]):
        d = f"2026-12-{20 + i}"
        w.sugg.add(row("FI-T1", d), suggest("closed"))
        w.find.est[("FI-T1", d)] = v
    _, msgs = draft(w)
    m = msgs[0]
    assert len(m.items) == 6 and m.dropped_items >= 1 and len(m.sms_text) <= 480
    assert "20.12." not in m.sms_text and "21.12." in m.sms_text


def test_65_views_line():
    for views, expect in ((340, True), (12, False), (None, False)):
        w = make_world()
        w.find = FakeFindability(
            default_est=100, last_year={("FI-T1", "2026-12-24"): views} if views is not None else {}
        )
        w.deps.findability = w.find
        _, msgs = draft(w)
        has = "yrityksenne näkyi Googlessa noin 340 kertaa" in msgs[0].body
        assert has is expect
        if not expect:
            assert "näkyi Googlessa" not in msgs[0].body


def test_66_top_n_by_views_at_risk():
    w = make_world(eids=("FI-T1", "FI-T2", "FI-T3", "FI-T4"))
    for eid, v in (("FI-T1", 100), ("FI-T2", 900), ("FI-T3", 300), ("FI-T4", 5000)):
        for d in ("2026-12-24", "2026-12-31"):
            w.find.est[(eid, d)] = v
    w.contacts.c["FI-T4"] = w.contacts.c["FI-T4"].model_copy(update={"opted_out": True})  # would stay quiet
    top = campaigns.top_by_views_at_risk(w.deps, "holidays", {}, ["FI-T1", "FI-T2", "FI-T3", "FI-T4"], 3)
    assert [e for e, _ in top] == ["FI-T2", "FI-T3", "FI-T1"] and top[0][1] == 1800


class EnglishLlm(FakeLlm):
    def write_intro(self, inp):
        from app.core.prompts import FAKE_INTRO, FAKE_SHORT

        self.intro_calls.append(inp)
        return {"subject": "Opening hours", "intro": FAKE_INTRO["en"], "short": FAKE_SHORT["en"]}


def sv_world(**kw):
    w = make_world(eids=())
    w.add_entity("FI-T1", lang="sv", **kw)
    return w


def test_67_swedish_speaking_finnish_business():
    w = sv_world()
    _, msgs = draft(w)
    b = msgs[0].body
    assert "Julafton" in b and "24/12" in b and "Svara bara på detta mejl" in b and msgs[0].language == "sv"
    ww = sv_world(channel="WHATSAPP")
    _, wm = draft(ww)
    assert wm[0].wa_template == "connect_hours_suggestion" and "24/12" in wm[0].wa_params[3]
    send.send_message(ww.deps, wm[0].id)
    assert ww.wa.templates()[0]["lang"] == "sv"
    ws = sv_world(channel="SMS")
    _, sm = draft(ws)
    assert "Google visar" in sm[0].sms_text and "Vi föreslår" in sm[0].sms_text


def test_68_finnish_reply_swedish_followup():
    w = sv_world()
    m = sent_message(w)
    r = email_reply(w, m, "Käy")
    assert r.status == "applied"
    fu = w.mail.outbox[-1]["text"]
    assert "Tack Maria" in fu and "Google Sök och Maps" in fu and "Apple Kartor" in fu and "päivittäneet" not in fu


def test_69_wrong_language_falls_back():
    w = make_world()
    w.llm = EnglishLlm()
    w.deps.llm = w.llm
    _, msgs = draft(w)
    assert msgs[0].intro_source == "fallback" and msgs[0].intro.startswith("Juhlapyhät lähestyvät")
    assert len(w.llm.intro_calls) == 2  # first try + one retry


def test_70_unsupported_preferred_language():
    w = make_world(eids=())
    w.add_entity("FI-T1", lang="sv", raw_lang="de")
    _, msgs = draft(w)
    assert msgs[0].language == "sv" and "Svara bara på detta mejl" in msgs[0].body
    w2 = make_world(eids=())
    w2.add_entity("FI-T1", lang="en", raw_lang="de")
    w2.yext.entities["FI-T1"]["meta"]["language"] = "xx"
    assert draft(w2)[1][0].language == "en"
    _ = wh
