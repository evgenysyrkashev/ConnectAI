"""In-memory Store with the same semantics as the Firestore one (deep copies, atomic claims)."""

from __future__ import annotations

import copy
import threading
from datetime import UTC, datetime

from app.core.models import Campaign, OutboundMessage, Reply, YextChange
from app.core.timeutil import iso


class MemoryStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.campaigns: dict[str, Campaign] = {}
        self.messages: dict[str, OutboundMessage] = {}
        self.replies: dict[str, Reply] = {}
        self.changes: dict[str, YextChange] = {}
        self.sms: list[dict] = []
        self.state: dict[str, dict] = {}
        self.sends: dict[str, int] = {}

    # --- campaigns
    def create_campaign(self, c: Campaign) -> None:
        with self._lock:
            self.campaigns[c.id] = c.model_copy(deep=True)

    def get_campaign(self, cid: str) -> Campaign | None:
        with self._lock:
            c = self.campaigns.get(cid)
            return c.model_copy(deep=True) if c else None

    def list_campaigns(self, limit: int) -> list[Campaign]:
        with self._lock:
            cs = sorted(self.campaigns.values(), key=lambda c: c.created_at, reverse=True)
            return [c.model_copy(deep=True) for c in cs[:limit]]

    def update_campaign(self, cid: str, **fields) -> None:
        with self._lock:
            self.campaigns[cid] = self.campaigns[cid].model_copy(update=copy.deepcopy(fields))

    # --- messages
    def create_message(self, m: OutboundMessage) -> None:
        with self._lock:
            self.messages[m.id] = m.model_copy(deep=True)

    def get_message(self, mid: str) -> OutboundMessage | None:
        with self._lock:
            m = self.messages.get(mid)
            return m.model_copy(deep=True) if m else None

    def _msgs(self, pred) -> list[OutboundMessage]:
        with self._lock:
            return [m.model_copy(deep=True) for m in self.messages.values() if pred(m)]

    def list_messages(self, campaign_id: str) -> list[OutboundMessage]:
        return sorted(self._msgs(lambda m: m.campaign_id == campaign_id), key=lambda m: (m.created_at, m.id))

    def list_messages_for_entity(self, eid: str, limit: int) -> list[OutboundMessage]:
        ms = sorted(self._msgs(lambda m: m.entity_id == eid), key=lambda m: m.created_at, reverse=True)
        return ms[:limit]

    def find_message_by_thread(self, thread_id: str) -> OutboundMessage | None:
        ms = self._msgs(lambda m: m.thread_id == thread_id)
        return ms[0] if ms else None

    def find_message_by_provider_id(self, provider_id: str) -> OutboundMessage | None:
        ms = self._msgs(lambda m: m.provider_message_id == provider_id)
        return ms[0] if ms else None

    def list_due_escalations(self, now_iso: str) -> list[OutboundMessage]:
        return self._msgs(
            lambda m: (
                m.status == "sent"
                and m.escalate_at is not None
                and m.escalate_at <= now_iso
                and m.escalated_to is None
                and m.superseded_by is None
            )
        )

    def list_due_scheduled(self, now_iso: str) -> list[OutboundMessage]:
        return self._msgs(lambda m: m.status == "draft" and m.scheduled_at is not None and m.scheduled_at <= now_iso)

    def update_message(self, mid: str, **fields) -> None:
        with self._lock:
            self.messages[mid] = self.messages[mid].model_copy(update=copy.deepcopy(fields))

    def claim_message_for_sending(self, mid: str) -> bool:
        with self._lock:
            m = self.messages.get(mid)
            if m is None or m.status not in ("draft", "failed"):
                return False
            self.messages[mid] = m.model_copy(update={"status": "sending"})
            return True

    def find_open_messages_by_phone(self, phone_digits: str, channel: str) -> list[OutboundMessage]:
        now = iso(datetime.now(UTC))

        def open_(m: OutboundMessage) -> bool:
            return (
                m.to_phone_digits == phone_digits
                and m.channel == channel
                and m.status == "sent"
                and (m.expires_at is None or m.expires_at > now)
                and not self.has_applied_reply(m.id)
            )

        return sorted(self._msgs(open_), key=lambda m: m.sent_at or "", reverse=True)

    # --- sms log
    def append_sms(self, entry: dict) -> None:
        with self._lock:
            self.sms.append(copy.deepcopy(entry))

    def list_sms(self, phone: str | None) -> list[dict]:
        with self._lock:
            return sorted(
                (copy.deepcopy(e) for e in self.sms if phone is None or e["phone"] == phone), key=lambda e: e["at"]
            )

    # --- replies
    def create_reply_if_absent(self, r: Reply) -> bool:
        with self._lock:
            if r.id in self.replies:
                return False
            self.replies[r.id] = r.model_copy(deep=True)
            return True

    def get_reply(self, rid: str) -> Reply | None:
        with self._lock:
            r = self.replies.get(rid)
            return r.model_copy(deep=True) if r else None

    def update_reply(self, rid: str, **fields) -> None:
        with self._lock:
            self.replies[rid] = self.replies[rid].model_copy(update=copy.deepcopy(fields))

    def list_replies(self, status: str | None, limit: int) -> list[Reply]:
        with self._lock:
            rs = [r for r in self.replies.values() if status is None or r.status == status]
            rs.sort(key=lambda r: (r.created_at, r.id), reverse=True)
            return [r.model_copy(deep=True) for r in rs[:limit]]

    def list_replies_for_message(self, message_id: str) -> list[Reply]:
        with self._lock:
            rs = [r.model_copy(deep=True) for r in self.replies.values() if r.message_id == message_id]
            return sorted(rs, key=lambda r: (r.created_at, r.id))

    def has_applied_reply(self, message_id: str) -> bool:
        with self._lock:
            return any(r.message_id == message_id and r.status == "applied" for r in self.replies.values())

    # --- changes
    def create_change(self, ch: YextChange) -> None:
        with self._lock:
            self.changes[ch.id] = ch.model_copy(deep=True)

    def get_change(self, change_id: str) -> YextChange | None:
        with self._lock:
            c = self.changes.get(change_id)
            return c.model_copy(deep=True) if c else None

    def update_change(self, change_id: str, **fields) -> None:
        with self._lock:
            self.changes[change_id] = self.changes[change_id].model_copy(update=copy.deepcopy(fields))

    def list_changes_for_entity(self, eid: str) -> list[YextChange]:
        with self._lock:
            cs = [c.model_copy(deep=True) for c in self.changes.values() if c.entity_id == eid]
            return sorted(cs, key=lambda c: c.created_at, reverse=True)

    # --- counters / state
    def try_increment_daily_sends(self, day: str, limit: int) -> bool:
        with self._lock:
            n = self.sends.get(day, 0)
            if n >= limit:
                return False
            self.sends[day] = n + 1
            return True

    def get_state(self, key: str) -> dict | None:
        with self._lock:
            v = self.state.get(key)
            return copy.deepcopy(v) if v is not None else None

    def set_state(self, key: str, value: dict) -> None:
        with self._lock:
            self.state[key] = copy.deepcopy(value)
