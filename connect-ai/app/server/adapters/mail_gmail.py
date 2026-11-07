"""Gmail API mailbox. Label-based, idempotent inbox processing."""

from __future__ import annotations

import base64
import logging
from email.message import EmailMessage
from email.utils import formataddr

from app.server.ports import OutgoingMail

log = logging.getLogger("connect.gmail")
SCOPES = ["https://www.googleapis.com/auth/gmail.send", "https://www.googleapis.com/auth/gmail.modify"]
LABEL = "connect-processed"


def build_service(client_id: str, client_secret: str, refresh_token: str):  # pragma: no cover - needs Google
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials(
        None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


class GmailMail:
    def __init__(self, service, address: str, sender_name: str, pubsub_topic: str | None = None) -> None:
        self.svc, self.address, self.sender_name, self.topic = service, address, sender_name, pubsub_topic
        self._label_id: str | None = None
        self._threads: dict[str, str] = {}

    def _msgs(self):
        return self.svc.users().messages()

    def send(self, o: OutgoingMail) -> tuple[str, str]:
        m = EmailMessage()
        m["From"] = formataddr((self.sender_name, self.address))
        m["To"] = o.to
        m["Reply-To"] = o.reply_to
        m["Subject"] = o.subject
        m.set_content(o.text)
        if o.in_reply_to:
            m["In-Reply-To"] = o.in_reply_to
            m["References"] = o.in_reply_to
        body: dict = {"raw": base64.urlsafe_b64encode(m.as_bytes()).decode()}
        if o.thread_id:
            body["threadId"] = o.thread_id
        res = self._msgs().send(userId="me", body=body).execute()
        return res["id"], res["threadId"]

    def list_unprocessed(self, max_n: int) -> list[str]:
        res = self._msgs().list(userId="me", q=f"in:inbox -label:{LABEL}", maxResults=max_n).execute()
        return [m["id"] for m in res.get("messages", [])]

    def get_raw(self, provider_id: str) -> bytes:
        res = self._msgs().get(userId="me", id=provider_id, format="raw").execute()
        if "threadId" in res:
            self._threads[provider_id] = res["threadId"]
        return base64.urlsafe_b64decode(res["raw"] + "=" * (-len(res["raw"]) % 4))

    def get_thread_id(self, provider_id: str) -> str | None:
        if provider_id not in self._threads:
            res = self._msgs().get(userId="me", id=provider_id, format="minimal").execute()
            self._threads[provider_id] = res.get("threadId", "")
        return self._threads[provider_id] or None

    def _ensure_label(self) -> str:
        if self._label_id:
            return self._label_id
        labels = self.svc.users().labels().list(userId="me").execute().get("labels", [])
        found = next((x["id"] for x in labels if x["name"] == LABEL), None)
        if found is None:
            found = self.svc.users().labels().create(userId="me", body={"name": LABEL}).execute()["id"]
        self._label_id = found
        return found

    def mark_processed(self, provider_id: str) -> None:
        self._msgs().modify(userId="me", id=provider_id, body={"addLabelIds": [self._ensure_label()]}).execute()

    def renew_watch(self) -> str | None:
        if not self.topic:
            return None
        res = self.svc.users().watch(userId="me", body={"topicName": self.topic, "labelIds": ["INBOX"]}).execute()
        return str(res.get("expiration")) if res.get("expiration") is not None else None
