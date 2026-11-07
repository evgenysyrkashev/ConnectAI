"""Operator identity, CSRF guard, security headers, body limit."""

from __future__ import annotations

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse

from app.server.config import Config

MAX_BODY = 100 * 1024
CSP = "default-src 'self'; style-src 'self'; script-src 'self'"


def operator_identity(request: Request) -> str:
    cfg: Config = request.app.state.config
    if cfg.app_env == "local":
        who = "local-dev@example.com"
    else:
        hdr = request.headers.get("X-Goog-Authenticated-User-Email")
        if hdr:
            who = hdr.removeprefix("accounts.google.com:")
        elif cfg.trust_proxy_mode:
            who = "proxy-user"
        else:
            raise HTTPException(status_code=401, detail="Not authenticated")
    if cfg.operator_allowlist and who not in cfg.operator_allowlist:
        raise HTTPException(status_code=403, detail="Operator not allowed")
    return who


def csrf_guard(request: Request) -> None:
    """POST routes under /ui and /dev need the HX-Request header (HTMX sends it, cross-site forms cannot)."""
    if request.headers.get("HX-Request") != "true":
        raise HTTPException(status_code=403, detail="Missing HX-Request header")
    origin = request.headers.get("Origin")
    if origin and origin != f"{request.url.scheme}://{request.url.netloc}":
        raise HTTPException(status_code=403, detail="Cross-origin request")


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if not request.url.path.startswith("/webhooks"):
            cl = request.headers.get("content-length")
            if cl and cl.isdigit() and int(cl) > MAX_BODY:
                return PlainTextResponse("Request too large", status_code=413)
            if not cl and "chunked" in request.headers.get("transfer-encoding", "").lower():
                # a chunked body has no declared size, so the limit above cannot apply
                return PlainTextResponse("Content-Length required", status_code=411)
        resp = await call_next(request)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "same-origin"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Content-Security-Policy"] = CSP
        return resp
