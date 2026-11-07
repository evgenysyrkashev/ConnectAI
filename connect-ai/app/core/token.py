"""Reply token."""

import hashlib
import hmac
import re
import secrets


def new_message_id() -> str:
    return secrets.token_hex(8)  # 16 lowercase hex chars


def sign_token(message_id: str, key: str) -> str:
    mac = hmac.new(key.encode(), f"connect-reply:v1:{message_id}".encode(), hashlib.sha256).hexdigest()[:16]
    return message_id + mac  # 32 hex chars


def verify_token(token: str, key: str) -> str | None:
    t = token.lower()
    if not re.fullmatch(r"[0-9a-f]{32}", t):
        return None
    mid = t[:16]
    return mid if hmac.compare_digest(sign_token(mid, key), t) else None


def reply_address(mailbox: str, token: str) -> str:
    local, domain = mailbox.split("@", 1)
    return f"{local}+{token}@{domain}"


def extract_tokens(values: list[str]) -> list[str]:
    seen: list[str] = []
    for v in values:
        for m in re.finditer(r"\+([0-9a-fA-F]{32})@", v):
            t = m.group(1).lower()
            if t not in seen:
                seen.append(t)
    return seen
