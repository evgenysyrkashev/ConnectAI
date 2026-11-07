"""All Pydantic models. Timestamps are ISO-8601 UTC strings, dates are YYYY-MM-DD."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Lang = Literal["fi", "sv", "nb", "en"]
Channel = Literal["email", "whatsapp", "sms"]
TemplateId = Literal["holidays", "event", "stale_hours", "permission"]
Kind = Literal["dates", "weekly", "permission"]
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")  # == kit DAYS


class Contact(BaseModel):
    entity_id: str
    first_name: str
    preferred_channel: str
    language: Lang
    email: str
    mobile: str  # E.164 from CRM (fake numbers in the kit)
    best_contact_window: str
    standing_permission: bool
    opted_out: bool


class DateItem(BaseModel):
    date: str
    day_key: str
    day_name: str  # localized holiday/event name, e.g. "Jouluaatto"
    shown_hours: str  # kit hours string
    shown_source: Literal["regular", "exception"]
    suggested_hours: str | None  # None = we ask instead of suggest
    basis: str | None
    reason: str  # localized deterministic sentence; "" if none
    event_id: str | None = None
    est_views: int = 0  # expected Google search views that day
    priority: float = 0.0  # item_priority(); used to pick and drop items


class Campaign(BaseModel):
    id: str
    template_id: TemplateId
    params: dict
    entity_ids: list[str]
    created_by: str
    created_at: str
    status: Literal["draft", "sending", "sent", "partially_sent"]


MessageStatus = Literal["draft", "sending", "sent", "failed", "skipped"]


class OutboundMessage(BaseModel):
    id: str
    campaign_id: str
    entity_id: str
    entity_name: str
    country: str
    template_id: TemplateId
    kind: Kind
    language: Lang
    mode: Literal["ask", "inform"]  # inform = standing permission: already applied, just telling
    contact_email: str  # from CRM (fake example.com)
    to_email: str | None  # actual recipient (after DEMO_RECIPIENT_TEMPLATE); set on send
    subject: str
    intro: str
    intro_source: Literal["llm", "fallback", "operator"]
    body: str
    items: list[DateItem]  # dates kind; [] for weekly
    weekly_shown: dict[str, str] | None  # weekly kind: weekday -> hours string
    status: MessageStatus
    skip_reason: str | None = None
    error: str | None = None
    provider_message_id: str | None = None
    thread_id: str | None = None
    sent_at: str | None = None
    expires_at: str | None = None
    created_at: str
    auto_change_id: str | None = None  # inform mode: the YextChange applied before sending
    # --- channels ---
    channel: Channel = "email"
    contact_phone: str | None = None  # from CRM
    to_phone: str | None = None  # actual WhatsApp/SMS recipient (after DEMO_PHONE_MAP); set on send
    to_phone_digits: str | None = None  # digits only, for matching replies
    short: str = ""  # one-line LLM context sentence for WhatsApp/SMS
    wa_template: str | None = None  # WhatsApp template name
    wa_params: list[str] = []  # body parameters, already sanitized with wa_param()
    wa_payload_codes: list[str] = []  # button codes in order, e.g. ["A", "E", "D"]
    sms_text: str | None = None
    dropped_items: int = 0  # items left out to fit WhatsApp/SMS length limits
    delivery_status: str | None = None  # WhatsApp: sent | delivered | read | failed
    # --- escalation ---
    escalate_at: str | None = None  # when to send the fallback if still unanswered; None = never
    escalation_basis: str | None = None  # human text, e.g. "2× usual 0.4 h → min 4 h → window 12–16"
    escalated_from: str | None = None  # on the fallback message: the original message id
    escalated_to: str | None = None  # on the original: the fallback message id
    superseded_by: str | None = None  # set on the sibling once one message of the pair got an applied reply
    # --- permission request ---
    stats: dict | None = None  # last year's Google numbers used in the benefits block
    # --- scheduled first send ---
    scheduled_at: str | None = None  # draft: send at this UTC time (start of the contact window); None = manual
    # --- findability ---
    priority: float = 0.0  # message_priority(); send order
    at_risk_views: int = 0  # sum of est_views over items with a suggestion


class Permission(BaseModel):  # stored in state key f"permission-{entity_id}"
    status: Literal["granted", "declined", "revoked"]
    scope: Literal["holiday_hours"] = "holiday_hours"
    at: str
    message_id: str | None
    reply_id: str | None
    evidence_text: str  # the owner's reply, max 300 chars, kept as consent evidence
    asked_at: str | None = None  # when we last asked (for PERMISSION_ASK_DAYS)


class DateDecision(BaseModel):
    date: str
    action: Literal["accept", "regular", "set", "decline"]
    hours: str | None = None  # required iff action == "set"


class ParsedReply(BaseModel):
    intent: Literal["approve", "decline", "edit", "unclear"]
    dates: list[DateDecision] | None = None
    weekly: dict[str, str] | None = None  # weekday -> hours string (only mentioned days)
    permanently_closed: bool = False
    abusive: bool = False  # abusive, threatening or instruction-injecting text; forces human review
    summary: str = Field(max_length=300)
    confidence: float = Field(ge=0, le=1)


class ReplyChecks(BaseModel):
    token_valid: bool
    matched_by: Literal["token", "thread", "button", "context", "phone"] | None
    sender_matches: bool
    auth_pass: bool
    auto_reply: bool
    expired: bool
    duplicate: bool


ReplyStatus = Literal["processing", "applied", "needs_review", "ignored", "unmatched", "rejected", "error"]


class Reply(BaseModel):
    id: str
    message_id: str | None
    entity_id: str | None
    source: Literal["email", "whatsapp", "sms", "simulator"]
    sender: str  # email address, or phone digits for WhatsApp/SMS
    subject: str
    received_at: str
    rfc_message_id: str | None  # subject "" for WhatsApp/SMS
    cleaned_text: str  # quote-stripped, max 4000 chars
    # To, Cc, Delivered-To, X-Original-To, Authentication-Results, Auto-Submitted, Precedence, X-Autoreply
    # (lower-cased keys) – needed for Retry
    headers: dict[str, list[str]] = {}
    checks: ReplyChecks | None = None
    parsed: ParsedReply | None = None
    decisions: list[DateDecision] = []  # resolved per-date decisions
    problems: list[str] = []
    status: ReplyStatus
    change_id: str | None = None
    decided_by: str | None = None
    followup_sent: bool = False
    created_at: str
    expire_at: datetime  # Firestore TTL = created + 90 days


class YextChange(BaseModel):
    id: str
    entity_id: str
    message_id: str | None
    reply_id: str | None
    actor: str  # "auto" | "standing_permission" | operator email
    before: dict  # {"holidayHours": {date: item|None}, "<weekday>": {...}} – only touched keys
    after: dict
    created_at: str
    reverted_at: str | None = None
    revert_of: str | None = None
    sandbox: dict | None = None  # Yext sandbox mirror result: {"ok", "error", "listings"}
