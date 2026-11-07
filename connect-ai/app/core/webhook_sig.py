"""Meta X-Hub-Signature-256 verification."""

import hashlib
import hmac


def verify_meta_signature(secret: str, raw: bytes, header: str | None) -> bool:
    if not header or not secret:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(header.encode(), expected.encode())  # bytes: str with non-ASCII would raise
