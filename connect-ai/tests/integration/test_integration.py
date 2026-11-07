import os

import pytest

from app import kit
from app.server.adapters.response_stats import channel_medians
from app.server.adapters.yext_http import HttpYext
from app.server.services import campaigns

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.path.exists(kit.data_path("data", "entities.json")),
        reason="needs the kit's data/ folder (set KIT_ROOT or place the kit next to this project)",
    ),
]


def test_yext_http_roundtrip(mock_url):
    y = HttpYext(mock_url)
    ent = y.get_entity("FI-D0001")
    hours = ent["hours"]
    hours["holidayHours"] = [*hours.get("holidayHours", []), {"date": "2027-03-03", "isClosed": True}]
    y.put_hours("FI-D0001", hours)
    assert any(h["date"] == "2027-03-03" for h in y.get_entity("FI-D0001")["hours"]["holidayHours"])
    listings = y.listings("FI-D0001")
    assert listings and any("expectedLiveBy" in x for x in listings)
    assert [e["meta"]["id"] for e in y.list_entities(["FI-D0001", "FI-D0002"])] == ["FI-D0001", "FI-D0002"]
    assert y.analytics("FI-D0001", "2025-12-01", "2025-12-31", ["GOOGLE_SEARCH_VIEWS"])["GOOGLE_SEARCH_VIEWS"] > 0


def test_baseline_suggestions(suggestions):
    rows = suggestions.rows_for("FI-D0001")
    assert rows and all(r.date > "2026-11-06" for r in rows)
    assert {suggestions.detect(r).action for r in suggestions.rows_for("FI-D0011")} == {"FLAG"}
    assert suggestions.has_history("FI-D0017") is False
    ev = [suggestions.detect(r) for r in suggestions.rows_for("FI-D0010") if r.day_key == "EVENT"]
    assert any(d.action == "SUGGEST" and d.basis == "LAST_EVENT" for d in ev)
    assert suggestions.stale_evidence("SE-D0016")


def test_findability(findability):
    assert findability.recent_mean("FI-D0001") > 0
    assert 1.3 <= findability.day_multiplier["XMAS_EVE"] <= 2.0
    assert findability.est_views("FI-D0001", "2026-12-12", "EVENT") == round(findability.recent_mean("FI-D0001"))
    assert findability.last_year_views("FI-D0001", "XMAS_EVE", "FI", "2026-12-24") is not None


def test_response_stats_medians():
    m = channel_medians()
    for ch, expect in (("WHATSAPP", 0.4), ("SMS", 1.1), ("EMAIL", 9.4)):
        assert abs(m[ch] - expect) <= 0.1, (ch, m[ch])


def test_quiet_demo(real_deps):
    demo = real_deps.suggestions.entity_ids("demo")
    assert len(demo) == 17
    c = campaigns.create_campaign(real_deps, "holidays", {}, demo, "op")
    by = {m.entity_id: m for m in real_deps.store.list_messages(c.id)}
    assert by["FI-D0011"].skip_reason.startswith("flagged")
    assert by["FI-D0013"].status == "skipped" and by["FI-D0013"].skip_reason in ("no_evidence", "already_entered")
    assert by["NO-D0015"].status == "skipped" and by["NO-D0015"].skip_reason == "no_evidence"
    assert by["FI-D0017"].status == "draft" and by["FI-D0017"].items


def test_demo_loop_over_http(real_deps):
    """The demo walk-through, driven through the HTTP layer with real baseline and kit mock."""
    from fastapi.testclient import TestClient

    from app.server.main import create_app

    hx = {"HX-Request": "true"}
    c = TestClient(create_app(real_deps.cfg, real_deps))
    st = real_deps.store
    demo = real_deps.suggestions.entity_ids("demo")
    for eid in demo:
        assert c.post(f"/ui/businesses/{eid}/messages", headers=hx).status_code == 204
    all_msgs = list(st.messages.values())
    assert any(m.status == "skipped" for m in all_msgs)
    by = {m.entity_id: m for m in all_msgs}
    assert by["FI-D0012"].mode == "inform" and any(i.suggested_hours is None for i in by["FI-D0017"].items)
    for m in sorted(all_msgs, key=lambda m: -m.priority):
        if m.status == "draft":
            c.post(f"/ui/messages/{m.id}/send", headers=hx)
    by = {m.entity_id: m for m in st.messages.values()}
    assert by["FI-D0001"].status == "sent" and by["FI-D0001"].channel == "sms"
    assert c.get("/phone").status_code == 200 and c.get("/outbox").status_code == 200

    # simulate an owner (SMS business) – applied, needs_review or no answer, but never an error
    c.post(f"/dev/messages/{by['FI-D0001'].id}/simulate?llm=0", headers=hx)
    assert all(rep.status != "error" for rep in st.replies.values())

    # free-text reply on an email business → review queue → reject
    email_m = next(m for m in by.values() if m.status == "sent" and m.channel == "email" and m.mode == "ask")
    c.post(f"/dev/messages/{email_m.id}/reply", data={"text": "mikä tapahtuma?"}, headers=hx)
    rep = next(x for x in st.replies.values() if x.message_id == email_m.id)
    assert rep.status == "needs_review" and "mikä tapahtuma?" in c.get(f"/businesses/{email_m.entity_id}").text
    assert c.post(f"/ui/replies/{rep.id}/reject", headers=hx).status_code == 204

    # WhatsApp business: tap Approve → applied, hours changed in the real mock, follow-up in the fake WhatsApp log
    wa = next(m for m in by.values() if m.status == "sent" and m.channel == "whatsapp" and m.mode == "ask")
    c.post(f"/dev/messages/{wa.id}/wa-tap?code=A", headers=hx)
    wrep = next(x for x in st.replies.values() if x.message_id == wa.id)
    assert wrep.status == "applied" and wrep.change_id, wrep.problems
    assert real_deps.yext.get_entity(wa.entity_id)["hours"].get("holidayHours")
    assert real_deps.whatsapp.texts() if hasattr(real_deps.whatsapp, "texts") else True

    # revert the change over HTTP
    assert c.post(f"/ui/changes/{wrep.change_id}/revert", headers=hx).status_code == 204

    # no answer on the other messages: advancing the demo clock produces reminder emails, then permission requests
    n_mail = len(real_deps.mail.outbox)
    c.post("/dev/clock/advance", data={"hours": "30"}, headers=hx)
    assert len(real_deps.mail.outbox) > n_mail
    c.post("/dev/clock/advance", data={"hours": "48"}, headers=hx)
    assert any(m.template_id == "permission" for m in st.messages.values())
    assert "Clock: +78 h (demo)" in c.get("/").text


def test_lazy_module_app_serves_ui():
    """`uvicorn app.server.main:app` builds its adapters on the first request."""
    from fastapi.testclient import TestClient

    from app.server import main

    with TestClient(main.app) as c:
        assert c.get("/healthz").text == "ok"
        page = c.get("/")
        assert page.status_code == 200 and "FI-D0017" in page.text and "FAKE MAIL" in page.text
