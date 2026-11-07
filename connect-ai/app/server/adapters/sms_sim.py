"""Simulated SMS gateway: stores the message in the SMS log; nothing is sent anywhere."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.core.timeutil import iso


class SimSms:
    def __init__(self, store, clock=None) -> None:
        self.store, self.clock = store, clock

    def send(self, to: str, text: str, message_id: str | None) -> str:
        sid = f"sms-out-{uuid.uuid4().hex[:12]}"
        now = self.clock.now() if self.clock else datetime.now(UTC)
        self.store.append_sms(
            {"id": sid, "direction": "out", "phone": to, "text": text, "at": iso(now), "message_id": message_id}
        )
        return sid
