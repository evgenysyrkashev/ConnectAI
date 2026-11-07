"""Delete all app state in Firestore and reset the Yext mock. Asks you to type the project id.

python -m scripts.wipe_staging            # uses GCP_PROJECT_ID (and YEXT_BASE_URL for the mock reset) from .env / env
"""

from __future__ import annotations

import os
import sys

from app.server.config import read_dotenv

COLLECTIONS = ("campaigns", "messages", "replies", "changes", "sms", "state")


def delete_collection(db, name: str, batch: int = 200) -> int:
    n = 0
    while True:
        docs = list(db.collection(name).limit(batch).stream())
        if not docs:
            return n
        for d in docs:
            d.reference.delete()
            n += 1


def wipe(db, project: str, typed: str) -> dict[str, int]:
    if typed.strip() != project:
        raise SystemExit("Project id did not match; nothing was deleted.")
    return {c: delete_collection(db, c) for c in COLLECTIONS}


def reset_mock(base_url: str) -> bool:  # pragma: no cover - needs a deployed, private mock
    import google.auth.transport.requests
    import httpx
    from google.oauth2 import id_token

    tok = id_token.fetch_id_token(google.auth.transport.requests.Request(), base_url)
    return (
        httpx.post(
            f"{base_url.rstrip('/')}/mock/reset", headers={"Authorization": f"Bearer {tok}"}, timeout=30
        ).status_code
        == 200
    )


def main() -> None:  # pragma: no cover
    env = {**read_dotenv(), **os.environ}
    project = env.get("GCP_PROJECT_ID")
    if not project:
        sys.exit("Set GCP_PROJECT_ID")
    from google.cloud import firestore

    typed = input(f"This deletes ALL Firestore data of project {project!r}. Type the project id to confirm: ")
    counts = wipe(firestore.Client(project=project), project, typed)
    print("deleted:", ", ".join(f"{k}={v}" for k, v in counts.items()))
    if env.get("YEXT_BASE_URL") and env.get("YEXT_USE_ID_TOKEN") == "true":
        print("mock reset:", "ok" if reset_mock(env["YEXT_BASE_URL"]) else "failed")
    print("Remember to reset the demo clock (the clock state lived in Firestore and is gone now).")


if __name__ == "__main__":
    main()
