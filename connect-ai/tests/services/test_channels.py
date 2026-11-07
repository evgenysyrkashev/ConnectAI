import pytest

from app.core.token import sign_token
from app.server.services import send, sms_inbound
from app.server.services.common import token_for
from tests.services import wa_helpers as wh
from tests.services.conftest import draft, make_world, sent_message
from tests.world import World

WA = {"channel": "WHATSAPP"}


def wa_world(env=None, eids=("FI-T1",), **kw):
    w = make_world(env, eids=())
    for e in eids:
        w.add_entity(e, channel="WHATSAPP", **kw)
    return w


def test_23_whatsapp_draft_and_send():
    w = wa_world()
    _, msgs = draft(w)
    m = msgs[0]
    assert m.channel == "whatsapp" and m.wa_template == "connect_hours_suggestion" and len(m.wa_params) == 5
    assert all("\n" not in p and "  " not in p for p in m.wa_params)
    assert m.wa_payload_codes == ["A", "E", "D"] and "24.12." in m.body  # email body is always computed too
    assert send.send_message(w.deps, m.id)["status"] == "sent"
    call = w.wa.templates()[0]
    tok = token_for(w.cfg, m.id)
    assert call["payloads"] == [f"A:{tok}", f"E:{tok}", f"D:{tok}"] and call["to"] == wh.PHONE and call["lang"] == "fi"
    sent = w.store.get_message(m.id)
    assert sent.to_phone_digits == wh.PHONE and sent.escalate_at is not None


def test_24_approve_tap_applies():
    w = wa_world()
    m = sent_message(w)
    r = wh.post(w, wh.payload([wh.button(w, m, "A")]))
    assert r.status_code == 200
    rep = w.store.get_reply("wa-wamid.IN1")
    assert rep.status == "applied" and rep.checks.matched_by == "button" and rep.cleaned_text == "[button] Approve"
    assert w.yext.holiday("FI-T1", "2026-12-24")["isClosed"] is True
    assert w.llm.parse_calls == []
    assert len(w.wa.texts()) == 1 and "päivittäneet" in w.wa.texts()[0]["text"]


def test_25_same_webhook_twice():
    w = wa_world()
    m = sent_message(w)
    body = wh.payload([wh.button(w, m, "A")])
    wh.post(w, body)
    wh.post(w, body)
    assert len(w.store.replies) == 1 and len(w.yext.puts) == 1


def test_26_wrong_signature():
    w = wa_world()
    m = sent_message(w)
    body = wh.payload([wh.button(w, m, "A")])
    assert wh.post(w, body, secret="wrong").status_code == 401
    assert wh.post(w, body, signed=False).status_code == 401
    assert w.store.replies == {} and not w.yext.puts


def test_verify_handshake():
    w = wa_world()
    c = wh.client(w)
    ok = c.get(
        "/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "123"}
    )
    assert ok.status_code == 200 and ok.text == "123"
    assert (
        c.get(
            "/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "x", "hub.challenge": "1"}
        ).status_code
        == 403
    )


def test_27_edit_tap_then_text():
    w = wa_world()
    m = sent_message(w)
    wh.post(w, wh.payload([wh.button(w, m, "E", label="Edit")]))
    assert w.store.get_state(f"wa-await-{wh.PHONE}")["message_id"] == m.id
    assert "Kirjoittakaa aukioloajat" in w.wa.texts()[0]["text"]
    assert w.store.get_reply("wa-wamid.IN1").status == "ignored"
    wh.post(w, wh.payload([wh.text("24.12. 10-14", wamid="wamid.IN3")]))
    rep = w.store.get_reply("wa-wamid.IN3")
    assert rep.status == "applied" and rep.checks.matched_by == "phone"
    assert w.yext.holiday("FI-T1", "2026-12-24")["openIntervals"] == [{"start": "10:00", "end": "14:00"}]


def test_28_context_match():
    w = wa_world()
    m = sent_message(w)
    wh.post(w, wh.payload([wh.text("ok", context=m.provider_message_id)]))
    rep = w.store.get_reply("wa-wamid.IN2")
    assert rep.checks.matched_by == "context" and rep.status == "applied"


def test_29_two_open_messages_same_phone():
    w = wa_world(eids=("FI-T1", "FI-T2"))
    c, _msgs = draft(w, eids=("FI-T1", "FI-T2"))
    send.send_campaign(w.deps, c.id, "op")
    wh.post(w, wh.payload([wh.text("ok")]))
    rep = w.store.get_reply("wa-wamid.IN2")
    assert rep.status == "needs_review" and "Several open messages" in rep.problems[0]


def test_30_statuses():
    w = wa_world()
    m = sent_message(w)
    wid = m.provider_message_id
    wh.post(w, wh.payload(statuses=[{"id": wid, "status": "delivered"}]))
    assert w.store.get_message(m.id).delivery_status == "delivered"
    wh.post(w, wh.payload(statuses=[{"id": wid, "status": "failed", "errors": [{"title": "Undeliverable"}]}]))
    got = w.store.get_message(m.id)
    assert got.delivery_status == "failed" and got.error == "Undeliverable" and got.escalate_at == w.deps.now_iso()


def test_31_outside_window_uses_template():
    w = wa_world()
    m = sent_message(w)
    w.wa.window_open = False
    wh.post(w, wh.payload([wh.button(w, m, "A")]))
    assert w.store.get_reply("wa-wamid.IN1").status == "applied"
    assert w.wa.texts() == []
    t = w.wa.templates()[-1]
    assert t["name"] == "connect_hours_updated" and t["payloads"] == [f"W:{token_for(w.cfg, m.id)}"]


def test_32_phone_not_allowlisted():
    w = wa_world({"PHONE_ALLOWLIST": "+358409999999"})
    _, msgs = draft(w)
    res = send.send_message(w.deps, msgs[0].id)
    assert res["status"] == "failed" and w.wa.calls == []


def sms_world(**kw):
    w = make_world(eids=())
    w.add_entity("FI-T1", channel="SMS", **kw)
    return w


def test_33_sms():
    w = sms_world()
    m = sent_message(w)
    assert m.channel == "sms" and m.to_phone == "+358401111111"
    log = w.store.list_sms(None)
    assert len(log) == 1 and log[0]["direction"] == "out" and len(log[0]["text"]) <= 480 and "STOP" in log[0]["text"]
    rep = sms_inbound.process_sms(w.deps, "+358401111111", "ok")
    assert rep.status == "applied" and w.llm.parse_calls == [] and rep.source == "sms"
    assert w.yext.holiday("FI-T1", "2026-12-31")
    assert any(e["direction"] == "out" and "Kahvila Testi" in e["text"] for e in w.store.list_sms(None)[2:])

    w2 = sms_world()
    w2.sugg.stale["FI-T1"] = [{"type": "review", "date": "2026-10-01", "text": "x"}]
    m2 = sent_message(w2, "stale_hours")
    r2 = sms_inbound.process_sms(w2.deps, "+358401111111", "ma-pe 9-17")
    assert r2.status == "applied"
    h = w2.yext.get_entity("FI-T1")["hours"]
    assert h["monday"]["openIntervals"][0]["start"] == "09:00" and h["sunday"]["openIntervals"][0]["start"] == "08:00"
    _ = m2


def test_34_sms_unknown_number():
    w = sms_world()
    sent_message(w)
    rep = sms_inbound.process_sms(w.deps, "+358409999999", "ok")
    assert rep.status == "unmatched"


def test_35_image_ignored_once():
    w = wa_world()
    m = sent_message(w)
    img = {"from": wh.PHONE, "id": "wamid.IMG1", "type": "image", "image": {"id": "x"}}
    wh.post(w, wh.payload([img]))
    wh.post(w, wh.payload([{**img, "id": "wamid.IMG2"}]))
    assert w.store.get_reply("wa-wamid.IMG1").status == "ignored"
    assert len(w.wa.texts()) == 1 and "Valitettavasti luen vain tekstiä" in w.wa.texts()[0]["text"]
    _ = m


def test_decline_and_regular_buttons():
    w = wa_world()
    m = sent_message(w)
    wh.post(w, wh.payload([wh.button(w, m, "D", label="No thanks")]))
    rep = w.store.get_reply("wa-wamid.IN1")
    assert rep.status == "applied" and not w.yext.puts and "ennalleen" in w.wa.texts()[0]["text"]


def test_invalid_button_token():
    w = wa_world()
    sent_message(w)
    bad = {
        "from": wh.PHONE,
        "id": "wamid.B",
        "type": "button",
        "button": {"payload": "A:" + sign_token("0" * 16, "other-key"), "text": "x"},
    }
    wh.post(w, wh.payload([bad]))
    assert w.store.get_reply("wa-wamid.B").status == "unmatched"


_ = (World, pytest)
