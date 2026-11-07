"""Fake WhatsApp: records every call. `window_open=False` makes send_text raise OutsideWindow."""

from __future__ import annotations

import itertools

from app.server.ports import OutsideWindow


class FakeWhatsApp:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.window_open = True
        self._ids = itertools.count(1)
        self.fail_next: Exception | None = None

    def _maybe_fail(self) -> None:
        if self.fail_next is not None:
            e, self.fail_next = self.fail_next, None
            raise e

    def send_template(self, to_digits: str, name: str, lang: str, params: list[str], payloads: list[str]) -> str:
        self._maybe_fail()
        wamid = f"wamid.FAKE{next(self._ids)}"
        self.calls.append(
            {
                "kind": "template",
                "to": to_digits,
                "name": name,
                "lang": lang,
                "params": params,
                "payloads": payloads,
                "id": wamid,
            }
        )
        return wamid

    def send_text(self, to_digits: str, text: str) -> str:
        self._maybe_fail()
        if not self.window_open:
            raise OutsideWindow()
        wamid = f"wamid.FAKE{next(self._ids)}"
        self.calls.append({"kind": "text", "to": to_digits, "text": text, "id": wamid})
        return wamid

    def texts(self) -> list[dict]:
        return [c for c in self.calls if c["kind"] == "text"]

    def templates(self) -> list[dict]:
        return [c for c in self.calls if c["kind"] == "template"]
