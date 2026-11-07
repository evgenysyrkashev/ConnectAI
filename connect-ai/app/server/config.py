"""Environment -> Config. Parsed once; fails fast with readable errors."""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

LOCAL_HMAC_KEY = "local-dev-key-not-secret"


def _split(value: str | None) -> list[str]:
    return [p.strip() for p in (value or "").split(";") if p.strip()]


class ConfigError(RuntimeError):
    pass


class Config(BaseModel):
    model_config = ConfigDict(frozen=True)

    app_env: Literal["local", "staging"] = "local"
    service_role: Literal["web", "inbound", "webhooks", "all"] = "all"
    store_mode: Literal["memory", "firestore"] = "memory"
    mail_mode: Literal["fake", "gmail"] = "fake"
    llm_mode: Literal["fake", "vertex"] = "fake"
    log_level: str = "INFO"  # DEBUG also logs every Yext request (URL and status only)
    yext_mode: Literal["embedded", "http"] = "embedded"
    yext_base_url: str | None = None
    yext_api_key: str = "demo"
    yext_use_id_token: bool = False
    simulator_base_url: str | None = None
    enable_simulator: bool = True
    suggestions_mode: Literal["baseline", "v2", "fake"] = (
        "v2"  # DECISION: v2 is the default since it beats the baseline in both evaluations
    )
    snapshot_date: date = date(2026, 11, 6)
    gcp_project_id: str | None = None
    vertex_location: str = "europe-west1"
    llm_model: str = "gemini-2.5-flash"  # DECISION: placeholder until set explicitly
    gmail_address: str = "connect.local@example.com"
    gmail_client_id: str | None = None
    gmail_client_secret: str | None = None
    gmail_refresh_token: str | None = None
    gmail_pubsub_topic: str | None = None
    token_hmac_key: str | None = None
    sender_name: str = "ConnectAI (demo)"
    demo_recipient_template: str | None = None
    recipient_allowlist: list[str] = ["@example.com"]
    operator_allowlist: list[str] = []
    trust_proxy_mode: bool = False
    auto_apply: bool = True
    min_confidence: float = 0.8
    max_messages_per_campaign: int = 25
    daily_send_limit: int = 100
    send_followups: bool = True
    channels_enabled: list[str] = ["email", "whatsapp", "sms"]
    ask_min_change_share: float = 0.3
    ask_min_peer_n: int = 10
    stale_evidence_days: int = 180
    already_asked_days: int = 60
    learn_from_pilot: bool = True  # seed owner-decision memory from the 2025 pilot log (brief 04)
    priority_recent_days: int = 28
    closed_door_weight: float = 1.5
    views_line_min: int = 20
    findability_mode: Literal["parquet", "fake"] = "parquet"
    yext_sandbox_mirror: bool = False
    yext_sandbox_direct: bool = False  # read/write the mapped entities directly in the sandbox (no mirror)
    yext_sandbox_base_url: str = "https://sbx-api.yextapis.com"
    yext_sandbox_api_key: str | None = None
    yext_sandbox_entity_map: str | None = None
    escalation_chain: list[str] = ["whatsapp>email", "sms>email", "email>permission"]
    permission_ask_days: int = 180
    offer_permission_in_followup: bool = True
    escalation_factor: float = 2.0
    min_escalation_hours: int = 4
    respect_contact_window: bool = True
    scheduler_interval_s: int = 0  # >0: a background tick runs the scheduler (local demo; on GCP use Cloud Scheduler)
    wa_mode: Literal["fake", "meta"] = "fake"
    wa_graph_version: str = "v21.0"  # DECISION: placeholder until set explicitly
    wa_phone_number_id: str | None = None
    wa_waba_id: str | None = None
    wa_access_token: str | None = None
    wa_app_secret: str | None = None
    wa_verify_token: str | None = None
    demo_phone_map: str | None = None
    phone_allowlist: list[str] = []

    @model_validator(mode="after")
    def _check(self) -> Config:
        errors: list[str] = []
        if self.app_env == "local":
            if self.token_hmac_key is None:
                object.__setattr__(self, "token_hmac_key", LOCAL_HMAC_KEY)
        elif not self.token_hmac_key or len(self.token_hmac_key) < 32:
            errors.append("TOKEN_HMAC_KEY is required (at least 32 characters) unless APP_ENV=local")
        if self.service_role == "all" and self.app_env == "staging":
            errors.append("SERVICE_ROLE=all is not allowed with APP_ENV=staging")
        if self.yext_mode == "http" and not self.yext_base_url:
            errors.append("YEXT_BASE_URL is required when YEXT_MODE=http")
        if self.simulator_base_url is None and self.yext_base_url:
            object.__setattr__(self, "simulator_base_url", self.yext_base_url)
        real = self.store_mode != "memory" or self.mail_mode != "fake" or self.llm_mode != "fake"
        if real and not self.gcp_project_id:
            errors.append("GCP_PROJECT_ID is required when any mode is real")
        if self.mail_mode == "gmail":
            # DECISION: the public webhooks service never touches Gmail and holds no Gmail secrets.
            for name in ("gmail_client_id", "gmail_client_secret", "gmail_refresh_token"):
                if not getattr(self, name) and self.service_role != "webhooks":
                    errors.append(f"{name.upper()} is required when MAIL_MODE=gmail")
            if self.service_role != "web" and not self.gmail_pubsub_topic:
                errors.append("GMAIL_PUBSUB_TOPIC is required when MAIL_MODE=gmail and SERVICE_ROLE is not web")
            if not self.recipient_allowlist:
                errors.append("RECIPIENT_ALLOWLIST must be non-empty when MAIL_MODE=gmail")
        if self.wa_mode == "meta":
            for name in ("wa_phone_number_id", "wa_waba_id", "wa_access_token"):
                if not getattr(self, name):
                    errors.append(f"{name.upper()} is required when WA_MODE=meta")
            if self.service_role == "webhooks":
                for name in ("wa_app_secret", "wa_verify_token"):
                    if not getattr(self, name):
                        errors.append(f"{name.upper()} is required for SERVICE_ROLE=webhooks with WA_MODE=meta")
        if (self.yext_sandbox_mirror or self.yext_sandbox_direct) and not self.yext_sandbox_api_key:
            errors.append("YEXT_SANDBOX_API_KEY is required when YEXT_SANDBOX_MIRROR or YEXT_SANDBOX_DIRECT is true")
        if errors:
            raise ValueError("; ".join(errors))
        return self

    def startup_line(self) -> str:
        """One log line with the modes. Never includes secrets."""
        return (
            f"modes: env={self.app_env} role={self.service_role} store={self.store_mode} mail={self.mail_mode} "
            f"llm={self.llm_mode} yext={self.yext_mode} wa={self.wa_mode} suggestions={self.suggestions_mode} "
            f"auto_apply={self.auto_apply}"
        )


_LIST_FIELDS = {"recipient_allowlist", "operator_allowlist", "channels_enabled", "escalation_chain", "phone_allowlist"}


ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


def read_dotenv(path: Path = ENV_FILE) -> dict[str, str]:
    """Tiny .env reader (KEY=value lines; # comments; optional quotes). The file is gitignored; secrets live in GCP in staging."""
    out: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return out
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        out[k.strip().removeprefix("export ").strip()] = v
    return out


def load_config(env: Mapping[str, str] | None = None) -> Config:
    """Build a Config from environment variables (semicolon-separated lists). Empty values count as unset.

    With no argument it reads `.env` (if present) and lets real environment variables win.
    """
    env = {**read_dotenv(), **os.environ} if env is None else env
    raw: dict[str, object] = {}
    for name in Config.model_fields:
        value = env.get(name.upper())
        if value is None or (value == "" and name not in _LIST_FIELDS):
            continue
        raw[name] = _split(value) if name in _LIST_FIELDS else value
    try:
        return Config.model_validate(raw)
    except ValidationError as e:
        lines = []
        for err in e.errors():
            loc = ".".join(str(p) for p in err["loc"]).upper() or "CONFIG"
            msg = err["msg"].removeprefix("Value error, ")
            lines.append(f"{loc}: {msg}" if loc != "CONFIG" else msg)
        raise ConfigError("Invalid configuration:\n  " + "\n  ".join(lines)) from None
