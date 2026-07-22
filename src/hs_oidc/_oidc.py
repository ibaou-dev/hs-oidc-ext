"""Shared OIDC discovery + JWT verification for the tenancy + RBAC extensions.

Provider-agnostic: give it an **issuer** and it discovers everything else from
``{issuer}/.well-known/openid-configuration`` (the endpoint every compliant OIDC
provider serves), including ``jwks_uri``. The only always-required admin input is
the issuer URL; a profile supplies the claim mapping (see :mod:`.claims`).

Config (shared by both extensions), read from the environment:

    HINDSIGHT_API_OIDC_ISSUER      required — e.g. https://id.example.com/realms/acme
    HINDSIGHT_API_OIDC_AUDIENCE    optional — expected ``aud`` (skip check if unset)
    HINDSIGHT_API_OIDC_JWKS_URL    optional — override discovery (needed when the
                                   issuer host is unreachable from inside the
                                   container; validate iss=issuer, fetch keys here)
    HINDSIGHT_API_OIDC_PROFILE     optional — vendor preset (default "generic")
    HINDSIGHT_API_OIDC_ALGORITHMS  optional — default "RS256"

Legacy ``HINDSIGHT_API_TENANT_{ISSUER,AUDIENCE,JWKS_URL}`` names are still honored
so existing deployments keep working.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import urllib.request

import jwt as pyjwt
from hindsight_api.extensions.tenant import AuthenticationError
from jwt import PyJWKClient

from ._metadata import www_authenticate
from .claims import ClaimMap, build_claim_map

logger = logging.getLogger(__name__)

_SCHEMA_TOKEN_RE = re.compile(r"[^a-z0-9_]")
_CLAIMS_CACHE_MIN_TTL = 5
_CLAIMS_CACHE_MAX = 1024
_DISCOVERY_TIMEOUT = 5


def _env(*names: str, default: str | None = None) -> str | None:
    """First set value among ``names`` (supports OIDC_* → legacy TENANT_* fallback)."""
    for n in names:
        v = os.getenv(n)
        if v:
            return v
    return default


def discover(issuer: str, timeout: int = _DISCOVERY_TIMEOUT) -> dict:
    """Fetch and return the provider's OIDC discovery document.

    The well-known URL tolerates a trailing slash on the issuer, but the ``issuer``
    value *inside* the document is authoritative for ``iss`` validation (some
    providers — Authentik — advertise a trailing slash that must match exactly).
    """
    url = issuer.rstrip("/") + "/.well-known/openid-configuration"
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 (trusted issuer)
        doc = json.loads(resp.read())
    if not doc.get("jwks_uri"):
        raise ValueError(f"Discovery document at {url} has no 'jwks_uri'")
    return doc


class OidcVerifier:
    """Validates OIDC JWTs (any compliant provider) and caches results per token."""

    def __init__(
        self,
        issuer: str,
        jwks_url: str,
        audience: str | None,
        claim_map: ClaimMap,
        algorithms: tuple[str, ...] = ("RS256",),
        leeway: int = 30,
    ) -> None:
        if not issuer:
            raise ValueError("HINDSIGHT_API_OIDC_ISSUER is required (e.g. https://id.example.com/realms/acme)")
        # Exact string — NOT rstrip'd: some providers (Authentik) advertise an
        # issuer with a trailing slash that must match the token's `iss` exactly.
        self.issuer = issuer
        self.jwks_url = jwks_url
        self.audience = audience or None
        self.claims = claim_map
        self.algorithms = list(algorithms)
        self.leeway = leeway
        self._jwk_client = PyJWKClient(jwks_url, cache_keys=True, lifespan=600)
        self._claims_cache: dict[str, tuple[float, dict]] = {}

    async def verify(self, token: str | None) -> dict:
        """Return the token's claims, or raise :class:`AuthenticationError`."""
        if not token:
            raise AuthenticationError(
                "Missing bearer token",
                headers={"WWW-Authenticate": www_authenticate()},
            )

        now = time.time()
        hit = self._claims_cache.get(token)
        if hit and hit[0] > now:
            return hit[1]

        try:
            signing_key = await asyncio.to_thread(self._jwk_client.get_signing_key_from_jwt, token)
            claims = pyjwt.decode(
                token,
                signing_key.key,
                algorithms=self.algorithms,
                issuer=self.issuer,
                audience=self.audience,
                leeway=self.leeway,
                options={
                    "require": ["exp", "iss", "sub"],
                    "verify_aud": self.audience is not None,
                },
            )
        except pyjwt.ExpiredSignatureError as e:
            raise AuthenticationError(
                "Token has expired",
                headers={"WWW-Authenticate": www_authenticate(error="invalid_token")},
            ) from e
        except pyjwt.InvalidAudienceError as e:
            raise AuthenticationError("Invalid token audience") from e
        except pyjwt.InvalidIssuerError as e:
            raise AuthenticationError("Invalid token issuer") from e
        except pyjwt.PyJWTError as e:
            raise AuthenticationError(f"Invalid token: {e}") from e
        except Exception as e:  # JWKS fetch / signing-key resolution failures
            raise AuthenticationError(f"Token verification failed: {e}") from e

        exp = float(claims.get("exp", now + 60))
        self._claims_cache[token] = (max(exp, now + _CLAIMS_CACHE_MIN_TTL), claims)
        if len(self._claims_cache) > _CLAIMS_CACHE_MAX:
            self._claims_cache = {k: v for k, v in self._claims_cache.items() if v[0] > now}
        return claims


_verifier: OidcVerifier | None = None


def get_verifier() -> OidcVerifier:
    """Lazily build the process-wide verifier from ``HINDSIGHT_API_OIDC_*`` env.

    If no JWKS URL is configured, it is discovered from the issuer's well-known
    document — so the minimal config is just issuer (+ profile + audience).
    """
    global _verifier
    if _verifier is None:
        issuer = _env("HINDSIGHT_API_OIDC_ISSUER", "HINDSIGHT_API_TENANT_ISSUER") or ""
        audience = _env("HINDSIGHT_API_OIDC_AUDIENCE", "HINDSIGHT_API_TENANT_AUDIENCE")
        jwks_url = _env("HINDSIGHT_API_OIDC_JWKS_URL", "HINDSIGHT_API_TENANT_JWKS_URL")
        algs = tuple(
            a.strip() for a in (_env("HINDSIGHT_API_OIDC_ALGORITHMS", default="RS256") or "").split(",") if a.strip()
        )
        claim_map = build_claim_map()

        if not jwks_url:
            if not issuer:
                raise ValueError("HINDSIGHT_API_OIDC_ISSUER is required (e.g. https://id.example.com/realms/acme)")
            doc = discover(issuer)
            jwks_url = doc["jwks_uri"]
            # Trust the issuer the provider advertises (authoritative for `iss`).
            issuer = doc.get("issuer") or issuer
            logger.info("Discovered jwks_uri=%s issuer=%s", jwks_url, issuer)

        _verifier = OidcVerifier(
            issuer=issuer,
            jwks_url=jwks_url,
            audience=audience,
            claim_map=claim_map,
            algorithms=algs or ("RS256",),
        )
        logger.info(
            "OIDC verifier ready (issuer=%s jwks=%s aud=%s profile=%s roles_claim=%s)",
            issuer,
            jwks_url,
            audience,
            claim_map.profile,
            claim_map.roles_claim,
        )
    return _verifier


def schema_for_tenant(tenant: str, prefix: str = "tenant") -> str:
    """Map a tenant claim (e.g. ``acme``) to a Postgres schema (``tenant_acme``)."""
    slug = _SCHEMA_TOKEN_RE.sub("_", tenant.strip().lower()).strip("_")
    if not slug:
        raise AuthenticationError("Token 'tenant' claim is empty or invalid")
    return f"{prefix}_{slug}"
