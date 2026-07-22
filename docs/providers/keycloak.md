---
type: Guide
title: Keycloak provider guide
description: Configure Keycloak as the OIDC provider for hs-oidc-ext — realm, client, tenant claim, audience, and the exact server config.
tags: [oidc, keycloak, provider, realm, guide]
timestamp: 2026-07-19T00:00:00Z
---

# Goal

Use Keycloak to authenticate Hindsight callers. The runnable version is the
[example stack](../../examples/README.md); this guide explains the pieces so you
can adapt it to an existing Keycloak.

# Realm & client

Create (or import) a realm — the example ships
[`examples/keycloak-realm.json`](../../examples/keycloak-realm.json) with:

- A confidential client `hindsight` (secret `hindsight-dev-secret`) with
  **Standard flow** (for the UI proxy), **Direct access grants** (password grant,
  dev convenience), and **Service accounts** (client-credentials for agents).
- An **audience mapper** so the access token's `aud` includes `hindsight`.
- A **tenant mapper** (user attribute `tenant` → claim `tenant`) for multi-tenancy.
- Users `alice` / `bob` with `tenant=acme`.

# Claims the extension reads

| Claim | Source in Keycloak | Used for |
|---|---|---|
| `iss`, `exp`, `sub` | standard | verification (required) |
| `aud` | audience mapper | optional `aud` check |
| `tenant` | user-attribute mapper | which Postgres schema |
| `preferred_username` | standard | identity / `user-*` conventions |
| `realm_access.roles` | default | surfaced for a future RBAC extension |

For **client roles** instead of realm roles, set
`HINDSIGHT_API_OIDC_ROLES_CLAIM=resource_access.<client>.roles` and
`HINDSIGHT_API_OIDC_CLIENT_ID=hindsight`.

# Server config

```bash
HINDSIGHT_API_TENANT_EXTENSION=hs_oidc.tenant:OIDCTenantExtension
HINDSIGHT_API_OIDC_ISSUER=http://localhost:8280/realms/hindsight
HINDSIGHT_API_OIDC_PROFILE=keycloak
HINDSIGHT_API_OIDC_AUDIENCE=hindsight
# Containerized: validate the public issuer but fetch keys in-network
HINDSIGHT_API_OIDC_JWKS_URL=http://keycloak:8080/realms/hindsight/protocol/openid-connect/certs
# Multi-tenant via the tenant claim; DEFAULT_TENANT catches tokens without one
HINDSIGHT_API_TENANT_KNOWN_TENANTS=acme
HINDSIGHT_API_TENANT_DEFAULT_TENANT=main
```

# Verify

```bash
ISS=http://localhost:8280/realms/hindsight
TOKEN=$(curl -s -X POST "$ISS/protocol/openid-connect/token" \
  -d grant_type=password -d client_id=hindsight -d client_secret=hindsight-dev-secret \
  -d username=alice -d password=alice | jq -r .access_token)
hs-oidc doctor "$ISS" --profile keycloak --audience hindsight --token "$TOKEN"
```

Expect `username=alice`, `tenant=acme`, roles resolved, signature verified.

# Single-tenant variant

Drop the tenant mapper and set only `HINDSIGHT_API_TENANT_DEFAULT_TENANT=main` —
every authenticated user shares one schema. Simplest way to "just protect the
server".

# Notes

- **JWKS/issuer decoupling** (`JWKS_URL`) is essential when Hindsight runs in a
  container that can't resolve the browser-facing issuer host.
- Access-token lifetime is Keycloak's `accessTokenLifespan`; clients refresh
  (see [client-configuration](../client-configuration.md)).
