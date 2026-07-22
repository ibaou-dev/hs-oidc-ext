"""Shared fixtures: an RSA-signed OIDC token factory + a stubbed verifier.

OIDC providers sign access tokens with RS256 and publish public keys via JWKS.
Tests generate a throwaway RSA keypair, sign tokens with the private key, and stub
the verifier's JWKS lookup to return the matching public key — deterministic,
offline. The default token shape is Keycloak-flavored (`realm_access.roles`); the
profile-matrix tests build other vendor shapes directly.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

import hs_oidc._oidc as authmod
from hs_oidc._oidc import OidcVerifier
from hs_oidc.claims import build_claim_map

ISSUER = "https://keycloak.example.com/realms/hindsight"
AUDIENCE = "hindsight"
KID = "test-key-1"


@pytest.fixture(scope="session")
def rsa_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def make_token(rsa_key):
    """Factory: make_token(tenant=..., roles=[...], exp_delta=..., **claim_overrides)."""

    def _make(
        tenant: str | None = "acme",
        roles: list[str] | None = None,
        exp_delta: int = 300,
        iss: str = ISSUER,
        aud: str | None = AUDIENCE,
        **overrides,
    ) -> str:
        now = int(time.time())
        claims: dict = {
            "iss": iss,
            "sub": "00000000-user",
            "preferred_username": "alice",
            "exp": now + exp_delta,
            "iat": now,
        }
        if aud is not None:
            claims["aud"] = aud
        if tenant is not None:
            claims["tenant"] = tenant
        claims["realm_access"] = {"roles": roles if roles is not None else ["viewer"]}
        claims.update(overrides)
        return pyjwt.encode(claims, rsa_key, algorithm="RS256", headers={"kid": KID})

    return _make


@pytest.fixture
def verifier(rsa_key, monkeypatch) -> OidcVerifier:
    """A verifier whose JWKS lookup is stubbed to the test public key.

    Uses the Keycloak claim profile (default token shape) and is installed as the
    process-wide singleton so OIDCTenantExtension and OIDCOperationValidator (which
    call get_verifier()) use it.
    """
    claim_map = build_claim_map({"HINDSIGHT_API_OIDC_PROFILE": "keycloak"})
    v = OidcVerifier(issuer=ISSUER, jwks_url="http://unused/certs", audience=AUDIENCE, claim_map=claim_map)
    public_key = rsa_key.public_key()
    v._jwk_client.get_signing_key_from_jwt = lambda token: SimpleNamespace(key=public_key)
    monkeypatch.setattr(authmod, "_verifier", v)
    return v
