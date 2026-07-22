"""Interactive user → OIDC-protected Hindsight via the Python SDK.

    pip install hindsight-client requests
    python python_client.py

The OIDC access token is passed as `api_key`; the SDK sends it as a bearer token.
"""

from __future__ import annotations

import os

import requests
from hindsight_client import Hindsight

ISSUER = os.environ.get("ISS", "http://localhost:8280/realms/hindsight")
API = os.environ.get("API", "http://localhost:8893")
USERNAME = os.environ.get("USER_NAME", "alice")


def get_token() -> str:
    resp = requests.post(
        f"{ISSUER}/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": "hindsight",
            "client_secret": "hindsight-dev-secret",
            "username": USERNAME,
            "password": USERNAME,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def main() -> None:
    client = Hindsight(base_url=API, api_key=get_token())  # ← token as bearer
    client.retain(bank_id="notes", content="Alice works on the memory platform")
    results = client.recall(bank_id="notes", query="What does Alice work on?")
    for r in results.results:
        print(r.text)


if __name__ == "__main__":
    main()
