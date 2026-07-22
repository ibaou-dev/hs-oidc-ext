"""A background agent (machine-to-machine) → OIDC-protected Hindsight.

Central-server mode: an unattended agent authenticates with the client-credentials
grant (no user, no browser) and refreshes on expiry. Tokens without a `tenant`
claim fall back to the server's DEFAULT_TENANT.

    pip install hindsight-client requests
    python agent_client_credentials.py
"""

from __future__ import annotations

import os
import time

import requests
from hindsight_client import Hindsight

ISSUER = os.environ.get("ISS", "http://localhost:8280/realms/hindsight")
API = os.environ.get("API", "http://localhost:8893")
CLIENT_ID = os.environ.get("CLIENT_ID", "hindsight")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET", "hindsight-dev-secret")


class TokenSource:
    """Mints + caches a client-credentials token, refreshing shortly before expiry."""

    def __init__(self) -> None:
        self._token = ""
        self._expires_at = 0.0

    def get(self) -> str:
        # Refresh 30s before the token actually expires.
        if time.monotonic() >= self._expires_at:
            resp = requests.post(
                f"{ISSUER}/protocol/openid-connect/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                },
                timeout=15,
            )
            resp.raise_for_status()
            body = resp.json()
            self._token = body["access_token"]
            self._expires_at = time.monotonic() + float(body.get("expires_in", 60)) - 30
        return self._token


def main() -> None:
    tokens = TokenSource()
    # Re-create the client with a fresh token each cycle (or wrap the transport).
    for i in range(3):
        client = Hindsight(base_url=API, api_key=tokens.get())
        client.retain(bank_id="agent-log", content=f"cycle {i} observation")
        print(f"cycle {i}: retained")
        time.sleep(1)


if __name__ == "__main__":
    main()
