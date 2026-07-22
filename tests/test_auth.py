"""Tests for hs_oidc._oidc — JWT verification + schema mapping."""

from __future__ import annotations

import pytest

from hs_oidc._oidc import schema_for_tenant
from hs_oidc.tenant import AuthenticationError  # re-exported base error

# --------------------------------------------------------------------------- #
# OidcVerifier.verify
# --------------------------------------------------------------------------- #


async def test_valid_token_returns_claims(verifier, make_token):
    claims = await verifier.verify(make_token(tenant="acme", roles=["admin"]))
    assert claims["tenant"] == "acme"
    assert claims["preferred_username"] == "alice"
    assert claims["realm_access"]["roles"] == ["admin"]


async def test_missing_token_rejected(verifier):
    with pytest.raises(AuthenticationError, match="Missing bearer token"):
        await verifier.verify(None)


async def test_expired_token_rejected(verifier, make_token):
    # beyond the verifier's 30s clock-skew leeway
    with pytest.raises(AuthenticationError, match="expired"):
        await verifier.verify(make_token(exp_delta=-120))


async def test_wrong_issuer_rejected(verifier, make_token):
    with pytest.raises(AuthenticationError, match="issuer"):
        await verifier.verify(make_token(iss="https://evil.example.com/realms/x"))


async def test_wrong_audience_rejected(verifier, make_token):
    with pytest.raises(AuthenticationError, match="audience"):
        await verifier.verify(make_token(aud="some-other-client"))


async def test_garbage_token_rejected(verifier):
    with pytest.raises(AuthenticationError):
        await verifier.verify("not.a.jwt")


async def test_claims_are_cached(verifier, make_token):
    token = make_token()
    first = await verifier.verify(token)
    second = await verifier.verify(token)
    assert first is second  # served from the per-token cache


async def test_issuer_trailing_slash_preserved(rsa_key, make_token):
    """Authentik advertises an issuer WITH a trailing slash; it must not be
    stripped, or the token's `iss` (which keeps the slash) fails validation."""
    from types import SimpleNamespace

    from hs_oidc._oidc import OidcVerifier
    from hs_oidc.claims import build_claim_map

    iss = "https://id.example.com/application/o/hindsight/"
    v = OidcVerifier(
        issuer=iss,
        jwks_url="http://unused/certs",
        audience=None,
        claim_map=build_claim_map({"HINDSIGHT_API_OIDC_PROFILE": "keycloak"}),
    )
    v._jwk_client.get_signing_key_from_jwt = lambda t: SimpleNamespace(key=rsa_key.public_key())
    claims = await v.verify(make_token(iss=iss, aud=None))
    assert claims["iss"] == iss  # exact match, slash preserved


# --------------------------------------------------------------------------- #
# schema_for_tenant
# --------------------------------------------------------------------------- #


def test_schema_mapping_basic():
    assert schema_for_tenant("acme") == "tenant_acme"


def test_schema_mapping_custom_prefix():
    assert schema_for_tenant("team-1.5", prefix="t") == "t_team_1_5"


def test_schema_mapping_sanitizes_unsafe_chars():
    assert schema_for_tenant("  Acme Corp!! ") == "tenant_acme_corp"


def test_schema_mapping_empty_rejected():
    with pytest.raises(AuthenticationError):
        schema_for_tenant("  ")
