"""Recipient allowlist."""

from app.core.email_checks import same_mailbox


def is_allowed(email: str, entries: list[str]) -> bool:
    """`*` allows everything; `@domain` matches the domain; otherwise an exact (plus-tag-insensitive) match."""
    addr = email.strip().lower()
    for raw in entries:
        e = raw.strip().lower()
        if not e:
            continue
        if e == "*":
            return True
        if e.startswith("@"):
            if addr.endswith(e):
                return True
        elif same_mailbox(addr, e):
            return True
    return False
