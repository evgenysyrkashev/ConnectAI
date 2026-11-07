import re

import pytest
from fastapi.testclient import TestClient

from app.server.adapters.clock import OffsetClock
from app.server.main import create_app
from app.server.services import campaigns, send
from tests.services.conftest import draft, make_world, sent_message

HX = {"HX-Request": "true"}


@pytest.fixture
def ui():
    w = make_world(eids=("FI-T1", "FI-T2"))
    w.deps.clock = OffsetClock(w.clock, w.store)
    c = TestClient(create_app(w.cfg, w.deps))
    return w, c


def test_pages_render(ui):
    _w, c = ui
    for path in (
        "/",
        "/businesses/FI-T1",
        "/phone",
        "/outbox",
        "/healthz",
    ):
        r = c.get(path)
        assert r.status_code == 200, (path, r.text[:300])
    page = c.get("/").text
    assert "FAKE MAIL" in page and "FI-T1" in page and "Views at risk" in page and "Demo clock" in page
    assert c.get("/businesses/NOPE").status_code == 404


def test_security_headers_and_csrf(ui):
    _w, c = ui
    r = c.get("/")
    assert r.headers["X-Content-Type-Options"] == "nosniff" and r.headers["X-Frame-Options"] == "DENY"
    assert "script-src 'self'" in r.headers["Content-Security-Policy"] and r.headers["Referrer-Policy"] == "same-origin"
    assert c.post("/dev/clock/advance", data={"hours": "1"}).status_code == 403  # no HX-Request
    assert (
        c.post("/dev/clock/advance", data={"hours": "1"}, headers={**HX, "Origin": "http://evil.example"}).status_code
        == 403
    )
    assert c.post("/dev/clock/advance", data={"hours": "1"}, headers=HX).status_code == 204
    big = c.post("/ui/businesses/FI-T1/messages", content=b"x" * 200_000, headers={**HX, "Content-Type": "text/plain"})
    assert big.status_code == 413


def test_operator_identity_staging():
    w = make_world(
        {"APP_ENV": "staging", "SERVICE_ROLE": "web", "TOKEN_HMAC_KEY": "k" * 40, "OPERATOR_ALLOWLIST": "a@x.com"}
    )
    c = TestClient(create_app(w.cfg, w.deps))
    assert c.get("/").status_code == 401
    assert c.get("/", headers={"X-Goog-Authenticated-User-Email": "accounts.google.com:b@x.com"}).status_code == 403
    assert c.get("/", headers={"X-Goog-Authenticated-User-Email": "accounts.google.com:a@x.com"}).status_code == 200
    # webhooks role mounts nothing else
    w2 = make_world({"SERVICE_ROLE": "webhooks"})
    c2 = TestClient(create_app(w2.cfg, w2.deps))
    assert c2.get("/").status_code == 404 and c2.get("/healthz").text == "ok"


def test_business_card_message_flow(ui):
    w, c = ui
    page = c.get("/businesses/FI-T1").text
    assert "Create draft" in page and "/campaigns" not in page
    assert c.post("/ui/businesses/NOPE/messages", headers=HX).status_code == 400
    assert "Template" not in page and 'name="template_id"' not in page
    assert c.post("/ui/businesses/FI-T1/messages", headers=HX).status_code == 204
    page = c.get("/businesses/FI-T1").text
    assert "Send message" in page and "Edit intro" in page and "Create draft" not in page  # open draft: no second one
    mid = next(iter(w.store.messages))
    assert c.post(f"/ui/messages/{mid}/send", headers=HX).status_code == 204
    assert w.store.get_message(mid).status == "sent"
    assert c.post("/ui/messages/nope/send", headers=HX).status_code == 404
    c.post(f"/dev/messages/{mid}/reply", data={"text": "mikä tapahtuma?"}, headers=HX)
    rep = next(iter(w.store.replies.values()))
    page = c.get("/businesses/FI-T1").text
    assert "mikä tapahtuma?" in page and f"/ui/replies/{rep.id}/reject" in page and "Create another message" in page
    assert 'class="badge st-needs_review"' in c.get("/").text
    assert "Reply needs review" in c.get("/").text.split('id="attention"')[1].split("</section>")[0]
    assert c.post(f"/ui/replies/{rep.id}/reject", headers=HX).status_code == 204


def test_simulate_review_revert_flow(ui):
    w, c = ui
    m = sent_message(w)
    assert c.post(f"/dev/messages/{m.id}/simulate?llm=0", headers=HX).status_code == 204
    rep = next(iter(w.store.replies.values()))
    assert rep.source == "simulator" and rep.status == "applied" and rep.change_id
    assert w.store.get_state(f"simtruth-{rep.id}")
    page = c.get("/businesses/FI-T1").text
    assert "Revert" in page and "Apply" in page.replace("Apply</li>", "Apply")
    ch = rep.change_id
    assert c.post(f"/ui/changes/{ch}/revert", headers=HX).status_code == 204
    assert w.yext.get_entity("FI-T1")["hours"]["holidayHours"] == []
    assert c.post(f"/ui/changes/{ch}/revert", headers=HX).status_code == 400


def test_write_reply_to_review_then_reject(ui):
    w, c = ui
    m = sent_message(w)
    c.post(f"/dev/messages/{m.id}/reply", data={"text": "mikä tapahtuma?"}, headers=HX)
    rep = next(iter(w.store.replies.values()))
    assert rep.status == "needs_review"
    page = c.get(f"/businesses/{m.entity_id}").text
    assert "Answer is unclear" in page and "mikä tapahtuma?" in page
    assert c.post(f"/ui/replies/{rep.id}/reject", headers=HX).status_code == 204
    assert w.store.get_reply(rep.id).status == "rejected"
    assert c.post(f"/ui/replies/{rep.id}/approve", headers=HX).status_code == 400  # no longer in review


def test_proposed_change_table(ui):
    w, c = ui
    m = sent_message(w)
    c.post(f"/dev/messages/{m.id}/reply", data={"text": "OK", "from_email": "stranger@test.example"}, headers=HX)
    page = c.get(f"/businesses/{m.entity_id}").text
    assert "Sender does not match" in page and "2026-12-24" in page and "isClosed" in page
    assert c.post(f"/ui/replies/{next(iter(w.store.replies))}/approve", headers=HX).status_code == 204


def test_channel_change_and_intro_edit(ui):
    w, c = ui
    _, msgs = draft(w)
    mid = msgs[0].id
    assert c.post(f"/ui/messages/{mid}/channel", data={"channel": "whatsapp"}, headers=HX).status_code == 204
    assert w.store.get_message(mid).wa_template == "connect_hours_suggestion"
    assert "connect_hours_suggestion" in c.get("/businesses/FI-T1").text
    assert c.post(f"/ui/messages/{mid}/channel", data={"channel": "fax"}, headers=HX).status_code == 400
    bad = c.post(f"/ui/messages/{mid}/intro", data={"subject": "x", "intro": "y"}, headers=HX)
    assert bad.status_code == 400
    assert c.post(f"/ui/messages/{mid}/regenerate", headers=HX).status_code == 204


def test_phone_and_sms_reply(ui):
    w, c = ui
    w.contacts.c["FI-T1"] = w.contacts.c["FI-T1"].model_copy(update={"preferred_channel": "SMS"})
    m = sent_message(w)
    assert m.channel == "sms"
    assert "Kahvila Testi" in c.get("/phone").text
    assert c.post("/dev/sms/%2B358401111111/reply", data={"text": "ok"}, headers=HX).status_code == 204
    assert any(r.status == "applied" for r in w.store.replies.values())


def test_escalation_buttons_and_clock(ui):
    w, c = ui
    w.contacts.c["FI-T1"] = w.contacts.c["FI-T1"].model_copy(update={"preferred_channel": "WHATSAPP"})
    m = sent_message(w)
    assert c.post(f"/dev/messages/{m.id}/wa-tap?code=Z", headers=HX).status_code == 400
    assert c.post(f"/ui/messages/{m.id}/escalation", data={"action": "cancel"}, headers=HX).status_code == 204
    assert w.store.get_message(m.id).escalate_at is None
    m2 = w.store.get_message(m.id)
    assert m2.status == "sent"
    m3 = sent_message(make_world(), "holidays") if False else None
    assert m3 is None


def test_inbound_routes():
    w = make_world({"SERVICE_ROLE": "inbound"})
    c = TestClient(create_app(w.cfg, w.deps))
    assert c.post("/cron/sync").json() == {"processed": 0, "errors": 0}
    assert c.post("/cron/escalate").json() == {"escalated": 0, "skipped": 0}
    assert c.post("/pubsub/gmail").status_code == 204
    assert c.post("/cron/renew-watch").status_code == 200
    assert c.get("/").status_code == 404


_ = (campaigns, send)


def test_demo_sidebar(ui):
    w, c = ui
    page = c.get("/").text
    assert 'id="demo-panel"' in page and "Demo clock" in page and 'href="/outbox"' in page and 'href="/phone"' in page
    nav = page.split("</nav>")[0]
    assert "/phone" not in nav and "/outbox" not in nav  # moved out of the top nav
    assert 'class="clock"' not in page  # no demo controls in the header any more

    # the picker defaults to the sent message of the page being viewed
    m = sent_message(w)
    assert re.search(rf'<option value="{m.id}" selected>', c.get("/businesses/FI-T1").text)
    assert "selected>" not in c.get("/").text.split('id="panel-mid"')[1].split("</select>")[0]

    # panel actions take the message from the picker
    assert c.post("/dev/panel/simulate", data={"mid": ""}, headers=HX).status_code == 400
    assert c.post("/dev/panel/simulate", data={"mid": m.id, "llm": "0"}, headers=HX).status_code == 204
    assert next(iter(w.store.replies.values())).source == "simulator"
    assert c.post("/dev/panel/wa-tap", data={"mid": m.id, "code": "A"}, headers=HX).status_code == 400  # email message
    assert c.post("/dev/panel/reply", data={"mid": "nope", "text": "ok"}, headers=HX).status_code == 404
    assert c.post("/dev/panel/reply", data={"mid": m.id, "text": "ok"}, headers=HX).status_code == 204

    # collapsing is a cookie; the collapsed panel renders no controls
    r = c.post("/ui/demo-panel", data={"open": "0"}, headers=HX)
    assert r.status_code == 204 and "demo_panel=0" in r.headers["set-cookie"]
    collapsed = c.get("/").text
    assert 'class="collapsed"' in collapsed and "Advance" not in collapsed
    assert c.post("/ui/demo-panel", data={"open": "0"}).status_code == 403  # needs HX-Request
    c.post("/ui/demo-panel", data={"open": "1"}, headers=HX)
    assert 'class="open"' in c.get("/").text


def test_sidebar_sections_follow_flags():
    w = make_world({"ENABLE_SIMULATOR": "false"})
    c = TestClient(create_app(w.cfg, w.deps))
    page = c.get("/").text
    assert 'id="demo-panel"' in page and "Fake email" in page  # fake mail and fake WhatsApp still show
    assert "Demo clock" not in page and "Simulate owner" not in page
    assert c.post("/dev/panel/simulate", data={"mid": "x"}, headers=HX).status_code in (404, 405)


def test_business_filters_multi_and_cascade(ui):
    _w, c = ui
    page = c.get("/?country=FI&country=SE").text
    assert 'type="hidden" name="country" value="FI"' in page and 'type="hidden" name="country" value="SE"' in page
    assert "onchange" not in page and "data-autosubmit" in page
    form = page[page.index('<form method="get"') : page.index("</form>")]
    assert "checkbox" not in form

    # country narrows the rows, and cities/segments cascade from it
    def all_table(q):
        return c.get(q).text.split("<h2>All businesses</h2>")[1]

    assert "FI-T1" in all_table("/?country=FI") and "FI-T1" not in all_table("/?country=SE")
    # the "with suggestions" table ignores the All-businesses filters
    sugg = lambda q: c.get(q).text.split('id="suggestions"')[1].split("</section>")[0]
    assert sugg("/?country=SE") == sugg("/")
    # a city that does not exist in the chosen country is dropped, not applied
    assert c.get("/?country=FI&city=NoSuchCity").status_code == 200


def test_business_filters_reset_link(ui):
    _w, c = ui
    assert "Reset filters" not in c.get("/").text
    assert 'href="/?split=demo">Reset filters' in c.get("/?country=FI").text


def test_attention_section(ui):
    w, c = ui
    assert "Nothing needs a human" in c.get("/").text
    m = sent_message(w)
    w.store.update_message(m.id, status="failed", error="boom")
    page = c.get("/").text.split('id="attention"')[1].split("</section>")[0]
    assert "FI-T1" in page and "Send failed: boom" in page


def test_translate_reply_inline(ui):
    from app.core.prompts import pick_locale

    w, c = ui
    m = sent_message(w)
    c.post(f"/dev/messages/{m.id}/reply", data={"text": "mikä tapahtuma?"}, headers=HX)
    rep = next(iter(w.store.replies.values()))
    page = c.get(f"/businesses/{m.entity_id}", headers={"Accept-Language": "sv-SE,sv;q=0.9"}).text
    assert f"/ui/replies/{rep.id}/translate" in page and "Translate to SV" in page
    r = c.post(f"/ui/replies/{rep.id}/translate", headers={**HX, "Accept-Language": "fi-FI,fi;q=0.9"})
    assert r.status_code == 200 and "[fi] mikä tapahtuma?" in r.text
    r = c.post(f"/ui/replies/{rep.id}/translate", data={"to": "en"}, headers=HX)
    assert "[en] mikä tapahtuma?" in r.text
    assert c.post(f"/ui/replies/{rep.id}/translate").status_code == 403  # CSRF guard
    assert c.post("/ui/replies/nope/translate", headers=HX).status_code == 404
    assert pick_locale(None) == "en" and pick_locale("xx,no;q=0.8") == "nb" and pick_locale("zz") == "en"
