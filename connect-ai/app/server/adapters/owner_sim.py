"""Owner simulator client: POST /sim/v1/owner-response on the kit mock."""

from __future__ import annotations

import httpx

from app.server.ports import SimUnavailable


class HttpOwnerSim:
    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/")
        self.http = httpx.Client(timeout=15)

    def respond(self, eid: str, date: str, proposed_hours: str) -> dict:
        r = self.http.post(
            f"{self.base}/sim/v1/owner-response",
            json={"entityId": eid, "date": date, "proposedHours": proposed_hours, "channel": "EMAIL"},
        )
        if r.status_code == 403:
            raise SimUnavailable(r.text[:200])
        r.raise_for_status()
        return r.json()["response"] if "response" in r.json() else r.json()
