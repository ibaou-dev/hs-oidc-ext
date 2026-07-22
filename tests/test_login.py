"""Tests for the client token helper — cache, PKCE, refresh, machine-to-machine."""

from __future__ import annotations

import base64
import hashlib
import time

import pytest

from hs_oidc import login


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HS_OIDC_HOME", str(tmp_path / ".hs-oidc"))


def test_pkce_pair_is_valid_s256():
    verifier, challenge = login._pkce_pair()
    assert 43 <= len(verifier) <= 128
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert challenge == expected


def test_cache_roundtrip():
    login._save_cache({"http://x": {"access_token": "t"}})
    assert login._load_cache()["http://x"]["access_token"] == "t"


def test_key_normalizes_trailing_slash():
    assert login._key("http://x/") == login._key("http://x")


def test_token_returns_cached_when_valid():
    login._save_cache({"http://s": {"access_token": "cached", "expires_at": time.time() + 999}})
    assert login.token("http://s") == "cached"


def test_token_refreshes_when_expired(monkeypatch):
    login._save_cache(
        {
            "http://s": {
                "access_token": "old",
                "refresh_token": "r1",
                "client_id": "c",
                "issuer": "iss",
                "resource": "http://s/mcp",
                "token_endpoint": "http://iss/token",
                "expires_at": time.time() - 5,
            }
        }
    )
    calls = {}

    def fake_post(url, data, timeout=15):
        calls["grant"] = data["grant_type"]
        return {"access_token": "new", "refresh_token": "r2", "expires_in": 300}

    monkeypatch.setattr(login, "_post_form", fake_post)
    assert login.token("http://s") == "new"
    assert calls["grant"] == "refresh_token"
    # rotated refresh token is persisted
    assert login._load_cache()["http://s"]["refresh_token"] == "r2"


def test_token_machine_to_machine(monkeypatch):
    monkeypatch.setattr(
        login,
        "discover",
        lambda s, i: {
            "issuer": "iss",
            "resource": "http://s/mcp",
            "authorization_endpoint": "http://iss/auth",
            "token_endpoint": "http://iss/token",
        },
    )

    def fake_post(url, data, timeout=15):
        assert data["grant_type"] == "client_credentials"
        assert data["client_id"] == "agent" and data["client_secret"] == "sec"
        return {"access_token": "m2m", "expires_in": 300}

    monkeypatch.setattr(login, "_post_form", fake_post)
    assert login.token("http://s", client_id="agent", client_secret="sec") == "m2m"


def test_token_not_logged_in_errors():
    with pytest.raises(SystemExit, match="Not logged in"):
        login.token("http://never")


def test_logout_clears(monkeypatch):
    login._save_cache({"http://s": {"access_token": "t"}})
    login.logout("http://s")
    assert "http://s" not in login._load_cache()


def test_discover_reads_protected_resource_metadata(monkeypatch):
    def fake_get(url, timeout=10):
        if url.endswith("/mcp/.well-known/oauth-protected-resource"):
            return {"resource": "http://s/mcp", "authorization_servers": ["http://iss/realms/r"]}
        if url.endswith("/.well-known/openid-configuration"):
            return {
                "issuer": "http://iss/realms/r",
                "authorization_endpoint": "http://iss/realms/r/auth",
                "token_endpoint": "http://iss/realms/r/token",
            }
        raise AssertionError(url)

    monkeypatch.setattr(login, "_get_json", fake_get)
    cfg = login.discover("http://s")
    assert cfg["issuer"] == "http://iss/realms/r"
    assert cfg["token_endpoint"].endswith("/token")
    assert cfg["resource"] == "http://s/mcp"
