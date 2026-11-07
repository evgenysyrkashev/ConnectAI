"""Real adapters exercised with fakes: Gmail service, Meta Graph API (httpx mock transport), Vertex client."""

import base64
import email
import email.policy
import email.utils
import json
from unittest.mock import MagicMock

import httpx
import pytest

from app.core.prompts import IntroInput, ParseInput, SimReplyInput
from app.server.adapters.llm_vertex import VertexLlm
from app.server.adapters.mail_gmail import GmailMail
from app.server.adapters.wa_meta import MetaWhatsApp
from app.server.ports import OutgoingMail, OutsideWindow, WhatsAppError


# ---------------------------------------------------------------- Gmail
def test_gmail_send_threading():
    svc = MagicMock()
    svc.users().messages().send().execute.return_value = {"id": "g1", "threadId": "t1"}
    mail = GmailMail(svc, "bot@gmail.com", "Connect (demo)")
    pid, tid = mail.send(
        OutgoingMail(
            to="o@x.com",
            reply_to="bot+abc@gmail.com",
            subject="Re: hi",
            text="body ä",
            thread_id="t1",
            in_reply_to="<m1@x>",
        )
    )
    assert (pid, tid) == ("g1", "t1")
    body = svc.users().messages().send.call_args.kwargs["body"]
    assert body["threadId"] == "t1"
    msg = email.message_from_bytes(base64.urlsafe_b64decode(body["raw"]), policy=email.policy.default)
    assert msg["Reply-To"] == "bot+abc@gmail.com" and msg["In-Reply-To"] == "<m1@x>" and msg["References"] == "<m1@x>"
    assert (
        email.utils.parseaddr(msg["From"]) == ("Connect (demo)", "bot@gmail.com")
        and msg.get_content().strip() == "body ä"
    )


def test_gmail_inbox_cycle():
    svc = MagicMock()
    mail = GmailMail(svc, "bot@gmail.com", "x", "projects/p/topics/gmail-inbox")
    svc.users().messages().list().execute.return_value = {"messages": [{"id": "a"}, {"id": "b"}]}
    assert mail.list_unprocessed(50) == ["a", "b"]
    assert "-label:connect-processed" in svc.users().messages().list.call_args.kwargs["q"]
    svc.users().messages().list().execute.return_value = {}
    assert mail.list_unprocessed(5) == []
    raw = base64.urlsafe_b64encode(b"Subject: x\r\n\r\nhi").decode().rstrip("=")
    svc.users().messages().get().execute.return_value = {"raw": raw, "threadId": "T9"}
    assert mail.get_raw("a") == b"Subject: x\r\n\r\nhi" and mail.get_thread_id("a") == "T9"
    # label created once, then reused
    svc.users().labels().list().execute.return_value = {"labels": [{"id": "L1", "name": "INBOX"}]}
    svc.users().labels().create().execute.return_value = {"id": "L2"}
    mail.mark_processed("a")
    mail.mark_processed("b")
    assert svc.users().messages().modify.call_args.kwargs["body"] == {"addLabelIds": ["L2"]}
    assert mail._label_id == "L2" and svc.users().messages().modify.call_count == 2
    svc.users().watch().execute.return_value = {"expiration": 1730000000000}
    assert mail.renew_watch() == "1730000000000"
    assert GmailMail(svc, "b@g.com", "x").renew_watch() is None


# ---------------------------------------------------------------- WhatsApp
def wa(handler):
    return MetaWhatsApp("PNID", "TOKEN", "v21.0", httpx.Client(transport=httpx.MockTransport(handler)))


def test_wa_template_payload():
    seen = {}

    def handler(req: httpx.Request):
        seen["url"], seen["auth"], seen["json"] = str(req.url), req.headers["authorization"], json.loads(req.content)
        return httpx.Response(200, json={"messages": [{"id": "wamid.X"}]})

    wid = wa(handler).send_template(
        "358401", "connect_hours_suggestion", "fi", ["Maria", "x"], ["A:tok", "E:tok", "D:tok"]
    )
    assert (
        wid == "wamid.X"
        and seen["url"] == "https://graph.facebook.com/v21.0/PNID/messages"
        and seen["auth"] == "Bearer TOKEN"
    )
    t = seen["json"]["template"]
    assert (
        seen["json"]["to"] == "358401" and t["language"] == {"code": "fi"} and t["name"] == "connect_hours_suggestion"
    )
    assert t["components"][0] == {
        "type": "body",
        "parameters": [{"type": "text", "text": "Maria"}, {"type": "text", "text": "x"}],
    }
    assert t["components"][2] == {
        "type": "button",
        "sub_type": "quick_reply",
        "index": "1",
        "parameters": [{"type": "payload", "payload": "E:tok"}],
    }


def test_wa_text_and_errors():
    ok = wa(lambda r: httpx.Response(200, json={"messages": [{"id": "w1"}]}))
    assert ok.send_text("358", "hi") == "w1"
    window = wa(lambda r: httpx.Response(400, json={"error": {"code": 131047, "message": "Re-engagement"}}))
    with pytest.raises(OutsideWindow):
        window.send_text("358", "hi")
    bad = wa(
        lambda r: httpx.Response(400, json={"error": {"code": 131030, "message": "Recipient not in allowed list"}})
    )
    with pytest.raises(WhatsAppError) as e:
        bad.send_template("358", "n", "fi", [], [])
    assert e.value.code == 131030 and "allowed list" in e.value.message
    with pytest.raises(WhatsAppError):
        wa(lambda r: httpx.Response(502, text="gateway")).send_text("358", "x")


# ---------------------------------------------------------------- Vertex
class FakeGenai:
    def __init__(self, text):
        self.text, self.calls = text, []
        self.models = self

    def generate_content(self, model, contents, config):
        self.calls.append((model, contents, config))
        return type("R", (), {"text": self.text})()


def test_vertex_calls():
    client = FakeGenai('```json\n{"subject": "s", "intro": "i", "short": "x"}\n```')
    llm = VertexLlm("p", "europe-west1", "gemini-test", client)
    inp = IntroInput(
        template_id="holidays",
        language="fi",
        business_name="Kahvila",
        first_name="Maria",
        facts=["a"],
        tone="warm",
        goal="g",
        sender_name="Connect",
    )
    assert llm.write_intro(inp) == {"subject": "s", "intro": "i", "short": "x"}
    model, contents, cfg = client.calls[0]
    assert (
        model == "gemini-test" and contents == "Facts:\n- a" and cfg.temperature == 0.7 and cfg.max_output_tokens == 400
    )
    assert cfg.response_mime_type == "application/json" and cfg.thinking_config.thinking_budget == 0
    assert "Finnish" in cfg.system_instruction
    client2 = FakeGenai('{"intent": "approve", "summary": "s", "confidence": 0.9}')
    out = VertexLlm("p", "l", "m", client2).parse_reply(
        ParseInput(kind="dates", mode="ask", language="fi", items_text="x", weekly_text="", cleaned_text="ok")
    )
    assert (
        out["intent"] == "approve"
        and client2.calls[0][1] == "<email>\nok\n</email>"
        and client2.calls[0][2].temperature == 0
    )
    client3 = FakeGenai("  Käy hyvin.  ")
    assert (
        VertexLlm("p", "l", "m", client3).write_sim_reply(
            SimReplyInput(language="fi", first_name="M", intent_description="approve")
        )
        == "Käy hyvin."
    )
    with pytest.raises(ValueError):
        VertexLlm("p", "l", "m", FakeGenai("not json")).parse_reply(
            ParseInput(kind="dates", mode="ask", language="fi", items_text="", weekly_text="", cleaned_text="x")
        )
