"""Mail placeholder for the public webhooks service, which has no Gmail credentials by design."""

from __future__ import annotations

from app.server.ports import OutgoingMail


class UnavailableMail:
    def send(self, m: OutgoingMail) -> tuple[str, str]:
        raise RuntimeError("This service has no mail access (webhooks role)")

    def list_unprocessed(self, max_n: int) -> list[str]:
        return []

    def get_raw(self, provider_id: str) -> bytes:
        raise RuntimeError("This service has no mail access (webhooks role)")

    def get_thread_id(self, provider_id: str) -> str | None:
        return None

    def mark_processed(self, provider_id: str) -> None:
        return None

    def renew_watch(self) -> str | None:
        return None
