"""Tests for OIDCTenantExtension — tenant claim -> Postgres schema (Option A)."""

from __future__ import annotations

import pytest

from hs_oidc.tenant import AuthenticationError, OIDCTenantExtension
from tests.helpers import FakeExtensionContext, FakeRequestContext


def _make_ext(config=None) -> OIDCTenantExtension:
    ext = OIDCTenantExtension(config or {})
    ext.set_context(FakeExtensionContext())
    return ext


async def test_authenticate_maps_tenant_to_schema(verifier, make_token):
    ext = _make_ext()
    ctx = FakeRequestContext(api_key=make_token(tenant="acme"))
    result = await ext.authenticate(ctx)
    assert result.schema_name == "tenant_acme"
    ext.context.run_migration.assert_awaited_with("tenant_acme")


async def test_authenticate_custom_prefix(verifier, make_token):
    ext = _make_ext({"schema_prefix": "dept"})
    ctx = FakeRequestContext(api_key=make_token(tenant="acme"))
    result = await ext.authenticate(ctx)
    assert result.schema_name == "dept_acme"


async def test_missing_tenant_claim_rejected(verifier, make_token):
    ext = _make_ext()
    ctx = FakeRequestContext(api_key=make_token(tenant=None))
    with pytest.raises(AuthenticationError, match="tenant"):
        await ext.authenticate(ctx)


async def test_default_tenant_used_when_claim_absent(verifier, make_token):
    """Single-tenant mode: no tenant claim needed when DEFAULT_TENANT is set."""
    ext = _make_ext({"default_tenant": "main"})
    ctx = FakeRequestContext(api_key=make_token(tenant=None))
    result = await ext.authenticate(ctx)
    assert result.schema_name == "tenant_main"


async def test_explicit_tenant_claim_overrides_default(verifier, make_token):
    ext = _make_ext({"default_tenant": "main"})
    ctx = FakeRequestContext(api_key=make_token(tenant="acme"))
    result = await ext.authenticate(ctx)
    assert result.schema_name == "tenant_acme"


async def test_no_token_rejected(verifier):
    ext = _make_ext()
    with pytest.raises(AuthenticationError):
        await ext.authenticate(FakeRequestContext(api_key=None))


async def test_internal_key_bypass_maps_to_fixed_schema(verifier):
    ext = _make_ext({"internal_api_key": "svc-secret", "internal_schema": "tenant_acme"})
    result = await ext.authenticate(FakeRequestContext(api_key="svc-secret"))
    assert result.schema_name == "tenant_acme"  # no JWT required for the service key


async def test_schema_provisioned_only_once(verifier, make_token):
    ext = _make_ext()
    ctx = FakeRequestContext(api_key=make_token(tenant="acme"))
    await ext.authenticate(ctx)
    await ext.authenticate(ctx)
    calls = [c.args[0] for c in ext.context.run_migration.await_args_list]
    assert calls.count("tenant_acme") == 1


async def test_on_startup_seats_public_then_known_tenants(verifier):
    ext = _make_ext({"known_tenants": "acme, globex"})
    await ext.on_startup()
    migrated = [c.args[0] for c in ext.context.run_migration.await_args_list]
    assert migrated[0] == "public"  # base schema first (seats pg_trgm/vector)
    assert "tenant_acme" in migrated
    assert "tenant_globex" in migrated


async def test_list_tenants_returns_provisioned(verifier, make_token):
    ext = _make_ext()
    await ext.authenticate(FakeRequestContext(api_key=make_token(tenant="acme")))
    tenants = await ext.list_tenants()
    assert [t.schema for t in tenants] == ["tenant_acme"]
