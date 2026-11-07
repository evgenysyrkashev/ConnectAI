"""WhatsApp webhook: GET handshake, signed POST."""

from __future__ import annotations

import hmac
import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import PlainTextResponse, Response

from app.core.webhook_sig import verify_meta_signature
from app.server.services import whatsapp_inbound
from app.server.services.common import Deps

log = logging.getLogger("connect.webhooks")
MAX_BODY = 1_000_000


def make_router(deps: Deps) -> APIRouter:
    router = APIRouter()
    cfg = deps.cfg

    @router.get("/webhooks/whatsapp", response_class=PlainTextResponse)
    def verify(request: Request) -> str:
        q = request.query_params
        token = q.get("hub.verify_token", "")
        if (
            q.get("hub.mode") == "subscribe"
            and cfg.wa_verify_token
            and hmac.compare_digest(token.encode(), cfg.wa_verify_token.encode())
        ):
            return q.get("hub.challenge", "")
        raise HTTPException(status_code=403)

    @router.post("/webhooks/whatsapp")
    async def receive(request: Request) -> Response:
        raw = await request.body()
        if len(raw) > MAX_BODY:
            raise HTTPException(status_code=413)
        if not verify_meta_signature(cfg.wa_app_secret or "", raw, request.headers.get("X-Hub-Signature-256")):
            log.warning("bad signature")
            raise HTTPException(status_code=401)
        try:
            payload = json.loads(raw)
        except ValueError:
            return Response(status_code=200)
        try:
            await run_in_threadpool(whatsapp_inbound.process_payload, deps, payload)
        except Exception as e:  # noqa: BLE001 - always 200 for a valid signature, or Meta retries forever
            log.warning("webhook processing failed: %s", type(e).__name__)
        return Response(status_code=200)

    return router
