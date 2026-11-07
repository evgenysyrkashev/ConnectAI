import json

import httpx

from app.core import wa_templates as wt
from scripts import wa_templates as script
from scripts.authorize_gmail import write_env_value


def test_graph_definitions():
    defs = wt.all_definitions()
    assert len(defs) == 16 and {d["category"] for d in defs} == {"UTILITY"}
    d = wt.graph_definition("connect_hours_suggestion", "fi")
    body, footer, buttons = d["components"]
    assert body["type"] == "BODY" and len(body["example"]["body_text"][0]) == 5 and "{{5}}" in body["text"]
    assert footer["text"] == "Vastaa STOP, jos et halua näitä viestejä."
    assert [b["text"] for b in buttons["buttons"]] == ["Hyväksy", "Muokkaa", "Ei kiitos"]
    assert len(wt.graph_definition("connect_hours_updated", "en")["components"][0]["example"]["body_text"][0]) == 4


def test_create_skips_existing_and_reports_failures():
    posted = []

    def handler(req: httpx.Request):
        if req.method == "GET":
            return httpx.Response(
                200, json={"data": [{"name": "connect_hours_check", "language": "fi", "status": "APPROVED"}]}
            )
        body = json.loads(req.content)
        posted.append((body["name"], body["language"]))
        if body["name"] == "connect_hours_updated" and body["language"] == "nb":
            return httpx.Response(
                400, json={"error": {"message": "bad", "error_user_msg": "Body ends with a parameter"}}
            )
        return httpx.Response(200, json={"id": "1", "status": "PENDING"})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    rows = script.create_missing(http, "https://graph.facebook.com/v21.0/WABA", "TOKEN")
    assert len(rows) == 16 and len(posted) == 15 and ("connect_hours_check", "fi") not in posted
    assert ("connect_hours_check", "fi", "exists") in rows
    assert any("FAILED: Body ends with a parameter" in r[2] for r in rows)


def test_write_env_value(tmp_path):
    p = tmp_path / ".env"
    p.write_text("A=1\nGMAIL_REFRESH_TOKEN=old\n")
    write_env_value(p, "GMAIL_REFRESH_TOKEN", "new")
    write_env_value(p, "B", "2")
    assert p.read_text() == "A=1\nGMAIL_REFRESH_TOKEN=new\nB=2\n" and oct(p.stat().st_mode)[-3:] == "600"
