"""Fake mailbox: records sent mail, lets tests/UI inject replies as raw RFC 822 messages."""

from __future__ import annotations

import itertools
import threading
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid

from app.server.ports import OutgoingMail

AUTH_PASS = "mx.google.com; dkim=pass header.i=@example.com; spf=pass; dmarc=pass (p=NONE)"
AUTH_FAIL = "mx.google.com; dkim=fail header.i=@example.com; spf=fail; dmarc=fail (p=NONE)"


class FakeMail:
    def __init__(self, gmail_address: str = "connect.local@example.com") -> None:
        self.gmail_address = gmail_address
        self.outbox: list[dict] = []  # sent mail: {id, thread_id, to, reply_to, subject, text, in_reply_to}
        self._inbox: dict[str, bytes] = {}
        self._threads: dict[str, str | None] = {}
        self._processed: set[str] = set()
        self._ids = itertools.count(1)
        self._lock = threading.Lock()
        self.fail_next: Exception | None = None

    def send(self, m: OutgoingMail) -> tuple[str, str]:
        with self._lock:
            if self.fail_next is not None:
                e, self.fail_next = self.fail_next, None
                raise e
            n = next(self._ids)
            pid = f"fake-out-{n}"
            thread = m.thread_id or f"thread-{n}"
            self.outbox.append({"id": pid, "thread_id": thread, **m.model_dump(exclude={"thread_id"})})
            return pid, thread

    def inject_reply(
        self,
        *,
        to: str,
        from_email: str,
        text: str,
        subject: str = "Re: hello",
        thread_id: str | None = None,
        auth_pass: bool = True,
        auto_reply: bool = False,
        delivered_to: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> str:
        """Add an inbound email to the inbox. `to` should carry the reply token to match by token."""
        msg = EmailMessage()
        msg["From"] = from_email
        msg["To"] = to
        msg["Delivered-To"] = delivered_to or to
        msg["Subject"] = subject
        msg["Message-ID"] = make_msgid(domain="mail.test")
        from datetime import UTC, datetime

        msg["Date"] = format_datetime(datetime.now(UTC))
        msg["Authentication-Results"] = AUTH_PASS if auth_pass else AUTH_FAIL
        if auto_reply:
            msg["Auto-Submitted"] = "auto-replied"
        for k, v in (extra_headers or {}).items():
            msg[k] = v
        msg.set_content(text)
        with self._lock:
            pid = f"fake-in-{next(self._ids)}"
            self._inbox[pid] = msg.as_bytes()
            self._threads[pid] = thread_id
            return pid

    def list_unprocessed(self, max_n: int) -> list[str]:
        with self._lock:
            return [p for p in self._inbox if p not in self._processed][:max_n]

    def get_raw(self, provider_id: str) -> bytes:
        return self._inbox[provider_id]

    def get_thread_id(self, provider_id: str) -> str | None:
        return self._threads.get(provider_id)

    def mark_processed(self, provider_id: str) -> None:
        with self._lock:
            self._processed.add(provider_id)

    def renew_watch(self) -> str | None:
        return None
