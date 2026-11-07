"""WhatsApp Business Cloud API over plain httpx."""

from __future__ import annotations

import httpx

from app.server.ports import OutsideWindow, WhatsAppError

OUTSIDE_WINDOW_CODE = 131047


class MetaWhatsApp:
    def __init__(
        self, phone_number_id: str, access_token: str, graph_version: str, http: httpx.Client | None = None
    ) -> None:
        self.url = f"https://graph.facebook.com/{graph_version}/{phone_number_id}/messages"
        self.token = access_token
        self.http = http or httpx.Client(timeout=30)

    def _post(self, payload: dict) -> str:
        r = self.http.post(self.url, json=payload, headers={"Authorization": f"Bearer {self.token}"})
        if r.status_code >= 300:
            try:
                err = r.json().get("error", {})
            except ValueError:
                err = {}
            code = err.get("code", r.status_code)
            if code == OUTSIDE_WINDOW_CODE:
                raise OutsideWindow()
            raise WhatsAppError(code, str(err.get("message") or r.text[:200]))
        return r.json()["messages"][0]["id"]

    def send_template(self, to_digits: str, name: str, lang: str, params: list[str], payloads: list[str]) -> str:
        components: list[dict] = [{"type": "body", "parameters": [{"type": "text", "text": p} for p in params]}]
        components += [
            {
                "type": "button",
                "sub_type": "quick_reply",
                "index": str(i),
                "parameters": [{"type": "payload", "payload": pl}],
            }
            for i, pl in enumerate(payloads)
        ]
        return self._post(
            {
                "messaging_product": "whatsapp",
                "to": to_digits,
                "type": "template",
                "template": {"name": name, "language": {"code": lang}, "components": components},
            }
        )

    def send_text(self, to_digits: str, text: str) -> str:
        return self._post({"messaging_product": "whatsapp", "to": to_digits, "type": "text", "text": {"body": text}})
