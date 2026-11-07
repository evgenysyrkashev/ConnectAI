"""One-time OAuth for the bot Gmail account.

    python -m scripts.authorize_gmail                 # client id/secret from Secret Manager, token → Secret Manager
    python -m scripts.authorize_gmail --target env    # client id/secret from .env, token → GMAIL_REFRESH_TOKEN in .env

Sign in as the bot account. The refresh token is never printed.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from app.server.adapters.mail_gmail import SCOPES
from app.server.config import ENV_FILE, read_dotenv


def _secret(project: str, name: str) -> str:  # pragma: no cover - needs GCP
    from google.cloud import secretmanager

    c = secretmanager.SecretManagerServiceClient()
    return (
        c.access_secret_version(name=f"projects/{project}/secrets/{name}/versions/latest").payload.data.decode().strip()
    )


def write_env_value(path: Path, key: str, value: str) -> None:
    """Set KEY=value in a .env file, keeping other lines."""
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    line = f"{key}={value}"
    if re.search(rf"^{re.escape(key)}=.*$", text, flags=re.MULTILINE):
        text = re.sub(rf"^{re.escape(key)}=.*$", lambda _: line, text, flags=re.MULTILINE)
    else:
        text = text + ("" if text.endswith("\n") or not text else "\n") + line + "\n"
    path.write_text(text, encoding="utf-8")
    path.chmod(0o600)


def main() -> None:  # pragma: no cover - interactive
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=["secret-manager", "env"], default="secret-manager")
    ap.add_argument("--project", default=os.environ.get("GCP_PROJECT_ID") or read_dotenv().get("GCP_PROJECT_ID"))
    a = ap.parse_args()
    env = {**read_dotenv(), **os.environ}
    if a.target == "env":
        cid, secret = env.get("GMAIL_CLIENT_ID"), env.get("GMAIL_CLIENT_SECRET")
    else:
        if not a.project:
            sys.exit("Set GCP_PROJECT_ID or pass --project")
        cid, secret = _secret(a.project, "gmail-client-id"), _secret(a.project, "gmail-client-secret")
    if not cid or not secret:
        sys.exit("GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET are missing")
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_config(
        {
            "installed": {
                "client_id": cid,
                "client_secret": secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        },
        SCOPES,
    )
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    if not creds.refresh_token:
        sys.exit("Google returned no refresh token; revoke the app's access and try again")
    if a.target == "env":
        write_env_value(ENV_FILE, "GMAIL_REFRESH_TOKEN", creds.refresh_token)
        print("Saved refresh token to .env")
    else:
        from google.cloud import secretmanager

        secretmanager.SecretManagerServiceClient().add_secret_version(
            parent=f"projects/{a.project}/secrets/gmail-refresh-token", payload={"data": creds.refresh_token.encode()}
        )
        print("Saved refresh token to Secret Manager")


if __name__ == "__main__":
    main()
