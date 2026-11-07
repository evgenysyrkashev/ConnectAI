"""Inbound routes: Pub/Sub push and Scheduler crons. Protected by Cloud Run IAM."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Response

from app.server.services import escalation, scheduler, sync
from app.server.services.common import Deps

log = logging.getLogger("connect.inbound")


def make_router(deps: Deps) -> APIRouter:
    r = APIRouter()

    @r.post("/pubsub/gmail")
    def pubsub() -> Response:
        try:
            sync.sync_inbox(deps)
        except Exception as e:  # noqa: BLE001
            log.warning("pubsub sync failed: %s", type(e).__name__)
            raise HTTPException(status_code=500) from None  # Pub/Sub retries
        return Response(status_code=204)

    @r.post("/cron/sync")
    def cron_sync() -> dict:
        return sync.sync_inbox(deps)

    @r.post("/cron/renew-watch")
    def renew() -> dict:
        exp = deps.mail.renew_watch()
        deps.store.set_state("gmail", {"watch_expiration": exp, "at": deps.now_iso()})
        return {"expiration": exp}

    @r.post("/cron/escalate")
    def escalate() -> dict:
        return escalation.run_escalations(deps)

    @r.post("/cron/send-scheduled")
    def send_scheduled() -> dict:
        return scheduler.run_scheduled(deps)

    return r
