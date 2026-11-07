"""Authentication, auto-reply and mailbox checks. Pure."""

import re
from email.utils import parseaddr


def parse_auth_results(values: list[str]) -> dict[str, str]:
    """Use the first Authentication-Results value starting with mx.google.com."""
    for v in values:
        if v.strip().lower().startswith("mx.google.com"):
            out: dict[str, str] = {}
            for key in ("spf", "dkim", "dmarc"):
                m = re.search(rf"\b{key}=(\w+)", v)
                if m:
                    out[key] = m.group(1).lower()
            return out
    return {}


def auth_pass(r: dict[str, str]) -> bool:
    # DECISION: only dmarc=pass counts. It implies SPF/DKIM aligned with the From domain; a bare dkim=pass
    # can come from any domain the sender controls, so it does not prove the From address.
    return r.get("dmarc") == "pass"


_AUTO_HEADERS = ("x-autoreply", "x-autorespond", "x-auto-response-suppress")


def is_auto_reply(headers: dict[str, str], from_email: str) -> bool:
    h = {k.lower(): v for k, v in headers.items()}
    sub = h.get("auto-submitted")
    if sub is not None and sub.strip().lower() != "no":
        return True
    if any(k in h for k in _AUTO_HEADERS):
        return True
    if h.get("precedence", "").strip().lower() in {"bulk", "junk", "list", "auto_reply"}:
        return True
    return bool(re.match(r"^(mailer-daemon|postmaster|no-?reply)@", from_email.strip().lower()))


def same_mailbox(a: str, b: str) -> bool:
    """Lowercase, strip the +tag from the local part, compare."""

    def norm(x: str) -> str:
        addr = parseaddr(x)[1] or x
        local, _, domain = addr.strip().lower().partition("@")
        return local.split("+", 1)[0] + "@" + domain

    return bool(a) and bool(b) and norm(a) == norm(b)
