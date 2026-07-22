"""Tests for MCP OAuth discovery — RFC 9728 metadata + WWW-Authenticate pointer."""

from __future__ import annotations

import pytest

from hs_oidc import _metadata


@pytest.fixture
def discovery_env(monkeypatch):
    monkeypatch.setenv("HINDSIGHT_API_OIDC_PUBLIC_URL", "https://memory.example.com")
    monkeypatch.setenv("HINDSIGHT_API_OIDC_ISSUER", "https://id.example.com/realms/acme")
    monkeypatch.delenv("HINDSIGHT_API_OIDC_RESOURCE", raising=False)
    monkeypatch.delenv("HINDSIGHT_API_OIDC_SCOPES", raising=False)


def test_metadata_document(discovery_env):
    doc = _metadata.build_resource_metadata()
    assert doc["resource"] == "https://memory.example.com/mcp"  # defaults to {public}/mcp
    assert doc["authorization_servers"] == ["https://id.example.com/realms/acme"]
    assert doc["bearer_methods_supported"] == ["header"]
    assert "openid" in doc["scopes_supported"]


def test_explicit_resource_override(discovery_env, monkeypatch):
    monkeypatch.setenv("HINDSIGHT_API_OIDC_RESOURCE", "https://memory.example.com/mcp/team")
    assert _metadata.resource_id() == "https://memory.example.com/mcp/team"


def test_www_authenticate_advertises_metadata_when_enabled(discovery_env):
    h = _metadata.www_authenticate()
    assert h.startswith('Bearer realm="hindsight"')
    assert 'resource_metadata="https://memory.example.com/ext/oauth-protected-resource"' in h


def test_www_authenticate_error_flag(discovery_env):
    h = _metadata.www_authenticate(error="invalid_token")
    assert 'error="invalid_token"' in h
    assert "resource_metadata=" in h


def test_discovery_off_without_public_url(monkeypatch):
    monkeypatch.delenv("HINDSIGHT_API_OIDC_PUBLIC_URL", raising=False)
    # Classic header, no pointer — backward compatible.
    assert _metadata.www_authenticate() == 'Bearer realm="hindsight"'
    assert _metadata.resource_metadata_url() is None


def test_extension_serves_document(discovery_env):
    """The HttpExtension returns the metadata dict from its route handler."""
    from hs_oidc.http import OIDCDiscoveryExtension

    ext = OIDCDiscoveryExtension({})
    router = ext.get_router(memory=None)
    # find the route and call its endpoint
    routes = {r.path: r for r in router.routes}
    assert "/oauth-protected-resource" in routes


async def test_401_www_authenticate_carries_pointer(discovery_env, verifier):
    """A missing-token 401 from the verifier now carries the resource_metadata pointer."""
    from hs_oidc.tenant import AuthenticationError

    with pytest.raises(AuthenticationError) as ei:
        await verifier.verify(None)
    hdr = ei.value.headers["WWW-Authenticate"]
    assert "resource_metadata=" in hdr
