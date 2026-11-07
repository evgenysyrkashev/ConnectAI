"""Mirror holiday-hours writes to the Yext sandbox. A sandbox failure never fails the real flow."""

from __future__ import annotations

import copy
import logging

from app.core.models import YextChange
from app.server.services.common import Deps

log = logging.getLogger("connect.sandbox")


def entity_map(spec: str | None) -> dict[str, str]:
    """'FI-D0001=<sandbox id>;FI-D0003=<id>' -> dict."""
    out = {}
    for part in (spec or "").split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            if k.strip() and v.strip():
                out[k.strip()] = v.strip()
    return out


_DEFAULT_HOURS = {
    d: {"openIntervals": [{"start": "10:00", "end": "18:00"}]}
    for d in ("monday", "tuesday", "wednesday", "thursday", "friday")
}
_DEFAULT_HOURS |= {"saturday": {"openIntervals": [{"start": "10:00", "end": "15:00"}]}, "sunday": {"isClosed": True}}


def import_entities(client, spec: str | None) -> list[dict]:
    """Fetch the mapped sandbox entities so they can be used locally (embedded mock).

    DECISION: the entity is fetched live, not stored in the repo. The local id is the map key. A sandbox entity
    without `hours` gets assumed ones (Mon-Fri 10-18, Sat 10-15, Sun closed), because the apply flow needs them.
    A failure is logged and skipped; it never stops startup.
    """
    out = []
    mapping = entity_map(spec)
    for local_id, sandbox_id in mapping.items():
        try:
            e = client.get_entity(sandbox_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("sandbox import of %s failed: %s", local_id, exc)
            continue
        e["meta"] = {**e.get("meta", {}), "id": local_id}
        e.setdefault("hours", _DEFAULT_HOURS)
        e.setdefault("closed", False)
        out.append(e)
    return out


def mirror(deps: Deps, change: YextChange) -> dict | None:
    """Apply the change's holidayHours (after-state; None = remove) to the mapped sandbox entity.

    Read-modify-write of the sandbox entity's own full hours object. Stores {"ok", "error", "listings"} on the change.
    """
    client = deps.extras.get("sandbox")
    if not deps.cfg.yext_sandbox_mirror or client is None:
        return None
    sid = entity_map(deps.cfg.yext_sandbox_entity_map).get(change.entity_id)
    holiday = (change.after or {}).get("holidayHours")
    if sid is None or not holiday:
        return None
    try:
        hours = copy.deepcopy(client.get_entity(sid).get("hours") or {})
        items = [h for h in hours.get("holidayHours", []) if h.get("date") not in holiday]
        items += [copy.deepcopy(v) for v in holiday.values() if v is not None]
        hours["holidayHours"] = sorted(items, key=lambda h: h["date"])
        client.put_hours(sid, hours)
        try:
            listings = [
                {k: x.get(k) for k in ("publisherId", "status", "expectedLiveBy")} for x in client.listings(sid)
            ]
        except Exception:  # noqa: BLE001 - listings are a bonus
            listings = []
        result = {"ok": True, "error": None, "listings": listings}
    except Exception as e:  # noqa: BLE001
        log.warning("sandbox mirror failed for %s: %s", change.entity_id, type(e).__name__)
        result = {"ok": False, "error": f"{type(e).__name__}: {e}"[:300], "listings": []}
    deps.store.update_change(change.id, sandbox=result)
    return result
