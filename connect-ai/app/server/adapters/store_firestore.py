"""Firestore Store. Same semantics as MemoryStore."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from app.core.models import Campaign, OutboundMessage, Reply, YextChange
from app.core.timeutil import iso

try:  # pragma: no cover - imported lazily in tests with a fake
    from google.api_core.exceptions import AlreadyExists
    from google.cloud import firestore
    from google.cloud.firestore_v1.base_query import FieldFilter
except ImportError:  # pragma: no cover
    firestore = None  # type: ignore[assignment]


def _plain(v: Any) -> Any:
    """Models -> JSON-able dicts (datetimes kept as datetimes for Firestore TTL)."""
    if isinstance(v, BaseModel):
        return _dump(v)
    if isinstance(v, list):
        return [_plain(x) for x in v]
    if isinstance(v, dict):
        return {k: _plain(x) for k, x in v.items()}
    return v


def _dump(m: BaseModel) -> dict:
    d = m.model_dump(mode="json")
    if isinstance(m, Reply):
        d["expire_at"] = m.expire_at  # a real datetime, for the TTL policy
    return d


class FirestoreStore:
    def __init__(self, client=None, project: str | None = None, transactional=None) -> None:
        self.db = client or firestore.Client(project=project)
        self._transactional = transactional or firestore.transactional

    # --- helpers
    def _col(self, name: str):
        return self.db.collection(name)

    def _where(self, col: str, **eq):
        q = self._col(col)
        for k, v in eq.items():
            q = q.where(filter=FieldFilter(k, "==", v))
        return q

    def _all(self, q) -> list[dict]:
        return [d.to_dict() for d in q.stream()]

    def _get(self, col: str, doc_id: str, model):
        snap = self._col(col).document(doc_id).get()
        return model.model_validate(snap.to_dict()) if snap.exists else None

    def _update(self, col: str, doc_id: str, fields: dict) -> None:
        self._col(col).document(doc_id).update({k: _plain(v) for k, v in fields.items()})

    # --- campaigns
    def create_campaign(self, c: Campaign) -> None:
        self._col("campaigns").document(c.id).set(_dump(c))

    def get_campaign(self, cid: str) -> Campaign | None:
        return self._get("campaigns", cid, Campaign)

    def list_campaigns(self, limit: int) -> list[Campaign]:
        q = self._col("campaigns").order_by("created_at", direction="DESCENDING").limit(limit)
        return [Campaign.model_validate(d) for d in self._all(q)]

    def update_campaign(self, cid: str, **fields) -> None:
        self._update("campaigns", cid, fields)

    # --- messages
    def create_message(self, m: OutboundMessage) -> None:
        self._col("messages").document(m.id).set(_dump(m))

    def get_message(self, mid: str) -> OutboundMessage | None:
        return self._get("messages", mid, OutboundMessage)

    def _messages(self, q) -> list[OutboundMessage]:
        return [OutboundMessage.model_validate(d) for d in self._all(q)]

    def list_messages(self, campaign_id: str) -> list[OutboundMessage]:
        return sorted(
            self._messages(self._where("messages", campaign_id=campaign_id)), key=lambda m: (m.created_at, m.id)
        )

    def list_messages_for_entity(self, eid: str, limit: int) -> list[OutboundMessage]:
        ms = self._messages(self._where("messages", entity_id=eid))
        return sorted(ms, key=lambda m: m.created_at, reverse=True)[:limit]

    def find_message_by_thread(self, thread_id: str) -> OutboundMessage | None:
        ms = self._messages(self._where("messages", thread_id=thread_id).limit(1))
        return ms[0] if ms else None

    def find_message_by_provider_id(self, provider_id: str) -> OutboundMessage | None:
        ms = self._messages(self._where("messages", provider_message_id=provider_id).limit(1))
        return ms[0] if ms else None

    def list_due_escalations(self, now_iso: str) -> list[OutboundMessage]:
        q = self._col("messages").where(filter=FieldFilter("escalate_at", "<=", now_iso))
        return [
            m
            for m in self._messages(q)
            if m.status == "sent" and m.escalated_to is None and m.superseded_by is None and m.escalate_at is not None
        ]

    def list_due_scheduled(self, now_iso: str) -> list[OutboundMessage]:
        q = self._col("messages").where(filter=FieldFilter("scheduled_at", "<=", now_iso))
        return [m for m in self._messages(q) if m.status == "draft" and m.scheduled_at is not None]

    def update_message(self, mid: str, **fields) -> None:
        self._update("messages", mid, fields)

    def claim_message_for_sending(self, mid: str) -> bool:
        ref = self._col("messages").document(mid)

        def txn(tx) -> bool:
            snap = ref.get(transaction=tx)
            if not snap.exists or snap.to_dict().get("status") not in ("draft", "failed"):
                return False
            tx.update(ref, {"status": "sending"})
            return True

        return self._transactional(txn)(self.db.transaction())

    def find_open_messages_by_phone(self, phone_digits: str, channel: str) -> list[OutboundMessage]:
        now = iso(datetime.now(UTC))
        ms = self._messages(self._where("messages", to_phone_digits=phone_digits, channel=channel, status="sent"))
        ms = [m for m in ms if (m.expires_at is None or m.expires_at > now) and not self.has_applied_reply(m.id)]
        return sorted(ms, key=lambda m: m.sent_at or "", reverse=True)

    # --- sms log
    def append_sms(self, entry: dict) -> None:
        self._col("sms").document(entry["id"]).set(entry)

    def list_sms(self, phone: str | None) -> list[dict]:
        q = self._where("sms", phone=phone) if phone is not None else self._col("sms")
        return sorted(self._all(q), key=lambda e: e["at"])

    # --- replies
    def create_reply_if_absent(self, r: Reply) -> bool:
        try:
            self._col("replies").document(r.id).create(_dump(r))
            return True
        except AlreadyExists:
            return False

    def get_reply(self, rid: str) -> Reply | None:
        return self._get("replies", rid, Reply)

    def update_reply(self, rid: str, **fields) -> None:
        self._update("replies", rid, fields)

    def list_replies(self, status: str | None, limit: int) -> list[Reply]:
        q = self._where("replies", status=status) if status else self._col("replies")
        q = q.order_by("created_at", direction="DESCENDING").limit(limit)
        return [Reply.model_validate(d) for d in self._all(q)]

    def list_replies_for_message(self, message_id: str) -> list[Reply]:
        rs = [Reply.model_validate(d) for d in self._all(self._where("replies", message_id=message_id))]
        return sorted(rs, key=lambda r: (r.created_at, r.id))

    def has_applied_reply(self, message_id: str) -> bool:
        return bool(self._all(self._where("replies", message_id=message_id, status="applied").limit(1)))

    # --- changes
    def create_change(self, ch: YextChange) -> None:
        self._col("changes").document(ch.id).set(_dump(ch))

    def get_change(self, change_id: str) -> YextChange | None:
        return self._get("changes", change_id, YextChange)

    def update_change(self, change_id: str, **fields) -> None:
        self._update("changes", change_id, fields)

    def list_changes_for_entity(self, eid: str) -> list[YextChange]:
        cs = [YextChange.model_validate(d) for d in self._all(self._where("changes", entity_id=eid))]
        return sorted(cs, key=lambda c: c.created_at, reverse=True)

    # --- counters / state
    def try_increment_daily_sends(self, day: str, limit: int) -> bool:
        ref = self._col("state").document(f"sends-{day}")

        def txn(tx) -> bool:
            snap = ref.get(transaction=tx)
            n = (snap.to_dict() or {}).get("n", 0) if snap.exists else 0
            if n >= limit:
                return False
            tx.set(ref, {"n": n + 1})
            return True

        return self._transactional(txn)(self.db.transaction())

    def get_state(self, key: str) -> dict | None:
        snap = self._col("state").document(key).get()
        return snap.to_dict() if snap.exists else None

    def set_state(self, key: str, value: dict) -> None:
        self._col("state").document(key).set(value)
