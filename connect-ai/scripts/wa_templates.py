"""Create / list WhatsApp message templates through the Graph API.

    python -m scripts.wa_templates create
    python -m scripts.wa_templates status

Needs WA_WABA_ID, WA_ACCESS_TOKEN, WA_GRAPH_VERSION (from the environment or .env). Never prints the token.
"""

from __future__ import annotations

import os
import sys

import httpx

from app.core.wa_templates import all_definitions
from app.server.config import read_dotenv


def _env(name: str, env: dict[str, str]) -> str:
    if not env.get(name):
        sys.exit(f"{name} is not set (put it in .env or the environment)")
    return env[name]


def list_templates(http: httpx.Client, base: str, token: str) -> list[dict]:
    out, url, params = [], f"{base}/message_templates", {"fields": "name,language,status", "limit": 100}
    while url:
        r = http.get(url, params=params, headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status()
        j = r.json()
        out += j.get("data", [])
        url, params = j.get("paging", {}).get("next"), None
    return out


def create_missing(http: httpx.Client, base: str, token: str) -> list[tuple[str, str, str]]:
    existing = {(t["name"], t["language"]) for t in list_templates(http, base, token)}
    results = []
    for d in all_definitions():
        key = (d["name"], d["language"])
        if key in existing:
            results.append((*key, "exists"))
            continue
        r = http.post(f"{base}/message_templates", json=d, headers={"Authorization": f"Bearer {token}"})
        if r.status_code >= 300:
            msg = r.json().get("error", {}).get("error_user_msg") or r.json().get("error", {}).get(
                "message", r.text[:200]
            )
            results.append((*key, f"FAILED: {msg}"))
        else:
            results.append((*key, f"created ({r.json().get('status', '?')})"))
    return results


def main(argv: list[str]) -> None:
    if len(argv) != 1 or argv[0] not in ("create", "status"):
        sys.exit(__doc__)
    env = {**read_dotenv(), **os.environ}
    base = f"https://graph.facebook.com/{_env('WA_GRAPH_VERSION', env)}/{_env('WA_WABA_ID', env)}"
    token = _env("WA_ACCESS_TOKEN", env)
    with httpx.Client(timeout=30) as http:
        if argv[0] == "create":
            rows = create_missing(http, base, token)
        else:
            rows = sorted((t["name"], t["language"], t["status"]) for t in list_templates(http, base, token))
    for name, lang, status in rows:
        print(f"{name:28} {lang:3} {status}")


if __name__ == "__main__":
    main(sys.argv[1:])
