import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from app.server.main import create_app
from app.server.services.common import token_for

PHONE = "358401111111"


def payload(messages=None, statuses=None) -> dict:
    value: dict = {}
    if messages:
        value["messages"] = messages
    if statuses:
        value["statuses"] = statuses
    return {"object": "whatsapp_business_account", "entry": [{"changes": [{"field": "messages", "value": value}]}]}


def button(world, msg, code, wamid="wamid.IN1", phone=PHONE, label="Approve"):
    return {
        "from": phone,
        "id": wamid,
        "type": "button",
        "button": {"payload": f"{code}:{token_for(world.cfg, msg.id)}", "text": label},
    }


def text(body, wamid="wamid.IN2", phone=PHONE, context=None):
    m = {"from": phone, "id": wamid, "type": "text", "text": {"body": body}}
    if context:
        m["context"] = {"id": context}
    return m


def sign(raw: bytes, secret="wa-secret") -> str:
    return "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


def client(world) -> TestClient:
    return TestClient(create_app(world.cfg, world.deps))


def post(world, body: dict, *, secret="wa-secret", signed=True):
    raw = json.dumps(body).encode()
    headers = {"X-Hub-Signature-256": sign(raw, secret)} if signed else {}
    return client(world).post("/webhooks/whatsapp", content=raw, headers=headers)
