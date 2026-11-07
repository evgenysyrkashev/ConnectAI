"""Shared service helpers: Deps container, effective contact, permission state, recipients."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from app.core.channel import digits
from app.core.models import Contact, OutboundMessage, Permission
from app.core.timeutil import iso
from app.core.token import reply_address, sign_token
from app.server.config import Config

SUPPORTED = ("fi", "sv", "nb", "en")


@dataclass
class Deps:
    cfg: Config
    store: Any
    mail: Any
    llm: Any
    yext: Any
    contacts: Any
    suggestions: Any
    findability: Any
    clock: Any
    stats: Any  # .usual_hours(eid, channel) -> (hours, source)
    whatsapp: Any = None
    sms: Any = None
    owner_sim: Any = None
    extras: dict = field(default_factory=dict)

    def now(self) -> datetime:
        return self.clock.now()

    def now_iso(self) -> str:
        return iso(self.now())

    def today(self) -> str:
        return self.now().date().isoformat()


def error_problem(e: Exception) -> str:
    """Operator-facing text for an internal error. Validation errors echo their input (reply text), so only their type shows."""
    if isinstance(e, ValueError):  # pydantic's ValidationError is a ValueError
        return f"Internal error: {type(e).__name__}"
    return f"Internal error: {type(e).__name__}: {str(e)[:200]}"


def new_id() -> str:
    return secrets.token_hex(8)


def effective_contact(deps: Deps, eid: str) -> Contact | None:
    """CRM contact with language resolution, opt-out state and permission state applied."""
    c = deps.contacts.get(eid)
    if c is None:
        return None
    raw = deps.contacts.raw_language(eid) if hasattr(deps.contacts, "raw_language") else c.language
    lang = raw if raw in SUPPORTED else None
    if lang is None:
        try:
            ent_lang = deps.yext.get_entity(eid).get("meta", {}).get("language")
        except Exception:  # noqa: BLE001
            ent_lang = None
        lang = ent_lang if ent_lang in SUPPORTED else "en"
    update: dict = {"language": lang}
    if deps.store.get_state(f"optout-{eid}"):
        update["opted_out"] = True
    perm = get_permission(deps, eid)
    if perm is not None:
        update["standing_permission"] = perm.status == "granted"
    return c.model_copy(update=update)


def get_permission(deps: Deps, eid: str) -> Permission | None:
    raw = deps.store.get_state(f"permission-{eid}")
    return Permission.model_validate(raw) if raw else None


def set_permission(deps: Deps, eid: str, perm: Permission) -> None:
    deps.store.set_state(f"permission-{eid}", perm.model_dump(mode="json"))


def demo_phone(cfg: Config, eid: str) -> str | None:
    """DEMO_PHONE_MAP: 'FI-D0003=+358...;*=+358...'."""
    mapping: dict[str, str] = {}
    for part in (cfg.demo_phone_map or "").split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            mapping[k.strip()] = v.strip()
    return mapping.get(eid) or mapping.get("*")


def recipient_email(cfg: Config, eid: str, contact: Contact) -> str:
    if cfg.demo_recipient_template:
        return cfg.demo_recipient_template.format(entity=eid.lower())
    return contact.email


def token_for(cfg: Config, message_id: str) -> str:
    assert cfg.token_hmac_key
    return sign_token(message_id, cfg.token_hmac_key)


def tokenized_reply_to(cfg: Config, message_id: str) -> str:
    return reply_address(cfg.gmail_address, token_for(cfg, message_id))


def recently_asked(deps: Deps, eid: str, now: datetime, days: int) -> set[str]:
    """Dates that appeared in a message to this entity that was *sent* within `days`."""
    since = iso(now - timedelta(days=days))
    out: set[str] = set()
    for m in deps.store.list_messages_for_entity(eid, 200):
        if m.status == "sent" and m.sent_at and m.sent_at >= since:
            out.update(i.date for i in m.items)
    return out


def live_holiday_dates(entity: dict) -> set[str]:
    return {h["date"] for h in (entity.get("hours") or {}).get("holidayHours", []) if "date" in h}


def phone_digits_of(msg: OutboundMessage) -> str | None:
    return msg.to_phone_digits or (digits(msg.to_phone) if msg.to_phone else None)


def dropped_key(mid: str) -> str:
    return f"dropped-{mid}"


def save_message(deps: Deps, m: OutboundMessage) -> None:
    """Persist every field of a message (keeps nested models as models, unlike model_dump)."""
    deps.store.update_message(m.id, **{k: getattr(m, k) for k in OutboundMessage.model_fields})
