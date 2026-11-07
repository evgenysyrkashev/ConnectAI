"""Scheduled first send: hold each draft until its business's contact window.

There is no Cloud Tasks here. A message gets `scheduled_at` (UTC); `run_scheduled` sends what is due.
It runs from `POST /cron/send-scheduled` and whenever the demo clock moves, and it reads `deps.now()`,
so advancing the demo clock makes the scheduled sends fire.
"""

from __future__ import annotations

import logging
from datetime import datetime

from app.core.escalation import next_window_start
from app.core.models import Campaign
from app.core.templates import TEMPLATES
from app.core.timeutil import iso
from app.server.services import campaigns, send, simulate
from app.server.services.common import Deps, effective_contact

log = logging.getLogger("connect.scheduler")
DEFAULT_TZ = "Europe/Helsinki"
FAR_FUTURE = "9999-12-31T23:59:59Z"


def _tz(deps: Deps, eid: str) -> str:
    try:
        return deps.yext.get_entity(eid).get("timezone") or DEFAULT_TZ
    except Exception:  # noqa: BLE001
        return DEFAULT_TZ


def planned_time(deps: Deps, eid: str) -> datetime | None:
    """Now if the business is inside its contact window (or has none), else the next window start. None = no contact."""
    contact = effective_contact(deps, eid)
    if contact is None:
        return None
    now = deps.now()
    if not deps.cfg.respect_contact_window:
        return now
    return next_window_start(now, contact.best_contact_window, _tz(deps, eid))


def suggested_ids(deps: Deps, split: str = "demo") -> list[str]:
    """Businesses with at least one SUGGEST row in the default holiday window (the "With suggestions" table)."""
    p = TEMPLATES["holidays"].params_model()
    lo, hi = p.date_from.isoformat(), p.date_to.isoformat()  # type: ignore[attr-defined]
    return [
        eid
        for eid in deps.suggestions.entity_ids(split)
        if any(
            lo <= r.date <= hi and deps.suggestions.detect(r).action == "SUGGEST"
            for r in deps.suggestions.rows_for(eid)
        )
    ]


def auto_schedule(deps: Deps, operator: str = "scheduler") -> Campaign | None:
    """Schedule every business with suggestions that has not been scheduled yet."""
    return schedule_for(deps, suggested_ids(deps), operator)


def schedule_for(deps: Deps, entity_ids: list[str], operator: str) -> Campaign | None:
    """Draft a holiday message for each business never scheduled before, and schedule it for its window."""
    todo = [e for e in entity_ids if schedule_state(deps, e) is None]
    if not todo:
        return None
    todo = todo[: deps.cfg.max_messages_per_campaign]
    campaign = campaigns.create_campaign(deps, "holidays", {}, todo, operator)
    for m in deps.store.list_messages(campaign.id):
        # skipped messages get a mark too, so the next tick does not draft them again
        at = planned_time(deps, m.entity_id) if m.status == "draft" else None
        deps.store.update_message(m.id, scheduled_at=iso(at or deps.now()))
    return campaign


def schedule_state(deps: Deps, eid: str) -> dict | None:
    """The latest scheduled message of a business: {"at", "status", "sent_at", "skip_reason"}, or None."""
    for m in deps.store.list_messages_for_entity(eid, 5):
        if m.scheduled_at:
            return {"at": m.scheduled_at, "status": m.status, "sent_at": m.sent_at, "skip_reason": m.skip_reason}
    return None


def run_scheduled(deps: Deps) -> dict:
    """Send every scheduled draft that is due and still inside its contact window; re-plan the others."""
    sent = deferred = 0
    auto_schedule(deps)
    due = sorted(deps.store.list_due_scheduled(deps.now_iso()), key=lambda m: -m.priority)
    for m in due:
        try:
            at = planned_time(deps, m.entity_id)
            if at is not None and at > deps.now():  # the window closed before we got here
                deps.store.update_message(m.id, scheduled_at=iso(at))
                deferred += 1
                continue
            res = send.send_one(deps, m.id)
        except Exception as e:  # noqa: BLE001
            log.warning("scheduled send of %s failed: %s", m.id, type(e).__name__)
            continue
        if res["status"] == "limit":
            break
        if res["status"] == "sent":
            sent += 1
            _simulate_owner(deps, m.id)
    return {"sent": sent, "deferred": deferred}


def _simulate_owner(deps: Deps, mid: str) -> None:
    """Demo: once a message is out, the simulated owner answers it with an LLM-written reply."""
    if not (deps.cfg.enable_simulator and deps.owner_sim):
        return
    try:
        reply = simulate.simulate_owner(deps, mid, use_llm=True)
        if reply is None:
            deps.store.set_state(f"sim-noanswer-{mid}", {"at": deps.now_iso()})
    except ValueError:  # not a dev/demo business, or not a dates message
        pass
    except Exception as e:  # noqa: BLE001
        log.warning("owner simulation for %s failed: %s", mid, type(e).__name__)
