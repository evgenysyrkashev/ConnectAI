"""Yext REST client (kit mock or Yext sandbox)."""

from __future__ import annotations

import contextlib
import json
import logging
import threading
import time

import httpx

from app.server.ports import YextError

log = logging.getLogger("connect.yext")


class HttpYext:
    def __init__(self, base_url: str, api_key: str = "demo", use_id_token: bool = False, v: str = "20261101"):
        self.base = base_url.rstrip("/")
        self.key, self.v, self.use_id_token = api_key, v, use_id_token
        self.http = httpx.Client(timeout=30)
        self._cache: dict[str, tuple[float, dict]] = {}
        self._lock = threading.Lock()
        self._token: tuple[float, str] | None = None

    # --- plumbing
    def _id_token(self) -> str:  # pragma: no cover - needs GCP
        if self._token and time.time() < self._token[0]:
            return self._token[1]
        import google.auth.transport.requests
        from google.oauth2 import id_token

        tok = id_token.fetch_id_token(google.auth.transport.requests.Request(), self.base)
        self._token = (time.time() + 50 * 60, tok)
        return tok

    def _req(self, method: str, path: str, params: dict | None = None, body: dict | None = None) -> dict:
        headers = {"api-key": self.key}
        if self.use_id_token:
            headers["Authorization"] = f"Bearer {self._id_token()}"
        url = f"{self.base}/v2/accounts/me/{path}"
        t0 = time.time()
        try:
            r = self.http.request(method, url, params={"v": self.v, **(params or {})}, json=body, headers=headers)
        except httpx.HTTPError as exc:
            log.warning("yext %s %s failed: %s", method, url, type(exc).__name__)  # never the key or bodies
            raise
        # DECISION: log only method, URL, status and timing; never the api-key header, the body or the response.
        log.debug("yext %s %s -> %s in %d ms", method, url, r.status_code, (time.time() - t0) * 1000)
        if r.status_code >= 300:
            msg = r.text[:400]
            with contextlib.suppress(Exception):
                msg = "; ".join(e.get("message", "") for e in r.json().get("meta", {}).get("errors", [])) or msg
            err = YextError(f"{method} {path} -> {r.status_code}: {msg}")
            err.status = r.status_code  # type: ignore[attr-defined]
            raise err
        return r.json()

    # --- Yext port
    def get_entity(self, eid: str) -> dict:
        with self._lock:
            hit = self._cache.get(eid)
            if hit and time.time() - hit[0] < 60:
                return json.loads(json.dumps(hit[1]))
        ent = self._req("GET", f"entities/{eid}")["response"]
        with self._lock:
            self._cache[eid] = (time.time(), ent)
        return json.loads(json.dumps(ent))

    def list_entities(self, ids: list[str]) -> list[dict]:
        out: dict[str, dict] = {}
        for i in range(0, len(ids), 50):
            chunk = ids[i : i + 50]
            try:
                r = self._req("GET", "entities", {"limit": 50, "filter": json.dumps({"meta.id": {"$in": chunk}})})[
                    "response"
                ]
                for e in r.get("entities", []):
                    out[e["meta"]["id"]] = e
            except YextError as e:
                if getattr(e, "status", None) != 400:
                    raise
                for eid in chunk:  # sandbox may not support $in
                    out[eid] = self.get_entity(eid)
        return [out[i] for i in ids if i in out]

    def put_hours(self, eid: str, hours: dict) -> dict:
        res = self._req("PUT", f"entities/{eid}", body={"hours": hours})
        with self._lock:
            self._cache.pop(eid, None)
        return res

    def listings(self, eid: str) -> list[dict]:
        return self._req("GET", "listings/listings", {"locationIds": eid})["response"].get("listings", [])

    def analytics(self, eid: str, start: str, end: str, metrics: list[str]) -> dict[str, int]:
        try:
            body = {
                "metrics": metrics,
                "dimensions": ["ENTITY_IDS"],
                "filters": {"startDate": start, "endDate": end, "entityIds": [eid]},
            }
            data = self._req("POST", "analytics/reports", body=body)["response"].get("data", [])
            return {m: int(sum(row.get(m, 0) or 0 for row in data)) for m in metrics}
        except Exception:  # noqa: BLE001 - analytics are optional
            return {}
