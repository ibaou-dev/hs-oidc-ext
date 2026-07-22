"""OIDCTenantExtension — tenant claim -> dedicated Postgres schema (Option A).

An OIDC access token carries a ``tenant`` claim (e.g. ``acme``). This extension
validates the token (any compliant provider — see :mod:`._oidc`) and returns a
:class:`TenantContext` whose ``schema_name`` is ``{prefix}_{tenant}`` (e.g.
``tenant_acme``), giving each tenant hard schema-level isolation. Role-based
authorization is enforced separately by ``OIDCOperationValidator``.

*Where* the tenant claim lives is set by the OIDC profile (:mod:`.claims`), not
here, so the same extension works with Keycloak/Auth0/Cognito/Zitadel/etc.

An optional internal service key lets a trusted co-located service (e.g. the
control-plane UI, which authenticates to the dataplane with a single shared key)
reach a fixed schema without presenting a user JWT.

Enable via environment (shared OIDC config lives under ``HINDSIGHT_API_OIDC_*``):

    HINDSIGHT_API_TENANT_EXTENSION=hs_oidc.tenant:OIDCTenantExtension
    HINDSIGHT_API_OIDC_ISSUER=https://id.example.com/realms/acme
    HINDSIGHT_API_OIDC_PROFILE=keycloak
    HINDSIGHT_API_OIDC_AUDIENCE=hindsight
    HINDSIGHT_API_TENANT_SCHEMA_PREFIX=tenant             # optional (default "tenant")
    HINDSIGHT_API_TENANT_KNOWN_TENANTS=acme,globex        # optional: pre-provision on boot
    HINDSIGHT_API_TENANT_DEFAULT_TENANT=main              # optional: single-tenant mode —
                                                          #   used when a token has no tenant
                                                          #   claim (no IdP mapper needed)
    HINDSIGHT_API_TENANT_INTERNAL_API_KEY=<shared-key>    # optional: service->schema bypass
    HINDSIGHT_API_TENANT_INTERNAL_SCHEMA=tenant_acme      # schema the internal key maps to

Two modes:
  * **Single-tenant** (simplest — "protect the server, one memory space"): set
    ``DEFAULT_TENANT`` and skip the IdP ``tenant`` mapper. Every authenticated
    user lands in one schema.
  * **Multi-tenant**: emit a ``tenant`` claim from the IdP; each tenant gets its
    own schema. ``DEFAULT_TENANT`` (if set) is the fallback for tokens without one.
"""

from __future__ import annotations

import logging

from hindsight_api.extensions.tenant import (
    AuthenticationError,
    Tenant,
    TenantContext,
    TenantExtension,
)
from hindsight_api.models import RequestContext

from ._oidc import get_verifier, schema_for_tenant

logger = logging.getLogger(__name__)

__all__ = ["OIDCTenantExtension"]


class OIDCTenantExtension(TenantExtension):
    """Authenticate OIDC JWTs and isolate each tenant in its own schema."""

    def __init__(self, config: dict[str, str]) -> None:
        super().__init__(config)
        self._verifier = get_verifier()
        self.schema_prefix = config.get("schema_prefix", "tenant")
        # Single-tenant fallback: when set, tokens without a `tenant` claim map here,
        # so an admin can protect a server without configuring an IdP tenant mapper.
        self._default_tenant = config.get("default_tenant") or None
        self._known_tenants = [t.strip() for t in config.get("known_tenants", "").split(",") if t.strip()]
        # Optional service-to-service bypass: a trusted co-located client (e.g. the
        # control-plane) presents this static key and is mapped to a fixed schema
        # without a user JWT. Leave unset to require a JWT for every request.
        self._internal_api_key = config.get("internal_api_key") or None
        self._internal_schema = config.get("internal_schema", "public")
        self._initialized_schemas: set[str] = set()

    async def on_startup(self) -> None:
        """Prepare the base schema, then pre-provision declared tenant schemas.

        The base ``public`` schema is migrated first so shared extensions
        (``pg_trgm``, ``vector``) are seated in ``public`` — which is always on the
        query-time ``search_path`` (``"$user", public``). Without this, the first
        *tenant* migration installs ``pg_trgm`` into the tenant schema instead, and
        queries fail with ``operator does not exist: text % text``.
        """
        try:
            await self.context.run_migration("public")
            logger.info("Base 'public' schema ready (shared extensions seated)")
        except Exception as e:  # non-fatal
            logger.warning("Base 'public' schema migration failed: %s", e)

        for tenant in self._known_tenants:
            schema = schema_for_tenant(tenant, self.schema_prefix)
            try:
                await self.context.run_migration(schema)
                self._initialized_schemas.add(schema)
                logger.info("Pre-provisioned tenant schema: %s", schema)
            except Exception as e:  # non-fatal: a request can still provision it later
                logger.warning("Could not pre-provision schema %s: %s", schema, e)

    async def authenticate(self, context: RequestContext) -> TenantContext:
        token = context.api_key

        # Trusted service identity — fixed schema, no JWT required.
        if self._internal_api_key and token == self._internal_api_key:
            if self._internal_schema not in self._initialized_schemas:
                await self._ensure_schema(self._internal_schema)
            return TenantContext(schema_name=self._internal_schema)

        claims = await self._verifier.verify(token)
        tenant = self._verifier.claims.tenant(claims) or self._default_tenant
        if not tenant:
            raise AuthenticationError(
                f"Token missing required tenant claim "
                f"('{self._verifier.claims.tenant_claim}') and no DEFAULT_TENANT is set"
            )

        schema = schema_for_tenant(str(tenant), self.schema_prefix)
        if schema not in self._initialized_schemas:
            await self._ensure_schema(schema)
        return TenantContext(schema_name=schema)

    async def _ensure_schema(self, schema: str) -> None:
        try:
            await self.context.run_migration(schema)
            self._initialized_schemas.add(schema)
            logger.info("Tenant schema ready: %s", schema)
        except Exception as e:
            logger.error("Schema initialization failed for %s: %s", schema, e)
            raise AuthenticationError(f"Failed to initialize tenant schema: {e}") from e

    async def list_tenants(self) -> list[Tenant]:
        """All provisioned tenant schemas (used by the worker to poll async tasks)."""
        return [Tenant(schema=s, tenant_id=s) for s in sorted(self._initialized_schemas)]
