---
type: Config
title: hs-oidc-ext configuration reference
description: Every environment variable, the vendor profiles, and the discovery / override rules for the OIDC authentication + tenancy extension.
tags: [oidc, configuration, env, profiles, hindsight]
timestamp: 2026-07-19T00:00:00Z
---

# Overview

The extension is configured entirely through `HINDSIGHT_API_*` environment
variables on the Hindsight server process. There are three groups:

1. **Shared OIDC** (`HINDSIGHT_API_OIDC_*`) — how to verify tokens; read by the
   verifier that both this extension and any downstream RBAC extension share.
2. **Tenancy** (`HINDSIGHT_API_TENANT_*`) — how the authenticated identity maps to
   a Postgres schema.
3. **Loader** — the one line that tells Hindsight to load the extension.

The only strictly required value is the **issuer**.

# Keys

## Loader

| Variable | Required | Description |
|---|---|---|
| `HINDSIGHT_API_TENANT_EXTENSION` | ✅ | `hs_oidc.tenant:OIDCTenantExtension` |

## Shared OIDC (`HINDSIGHT_API_OIDC_*`)

| Variable | Default | Description |
|---|---|---|
| `HINDSIGHT_API_OIDC_ISSUER` | — (required) | OIDC issuer URL, e.g. `https://id.example.com/realms/acme`. Everything else is discovered from `{issuer}/.well-known/openid-configuration`. |
| `HINDSIGHT_API_OIDC_PROFILE` | `generic` | Vendor preset for claim locations (see below). |
| `HINDSIGHT_API_OIDC_AUDIENCE` | unset | Expected `aud`. If set, it is validated; if unset, the `aud` check is skipped. |
| `HINDSIGHT_API_OIDC_JWKS_URL` | discovered | Override the JWKS URL. Needed when the issuer host is unreachable from inside the container (validate `iss` against the issuer, but fetch keys here). |
| `HINDSIGHT_API_OIDC_ALGORITHMS` | `RS256` | Comma-separated allowed signing algorithms. |
| `HINDSIGHT_API_OIDC_ROLES_CLAIM` | per profile | Override the roles claim path. |
| `HINDSIGHT_API_OIDC_TENANT_CLAIM` | `tenant` | Override the tenant claim path. |
| `HINDSIGHT_API_OIDC_USERNAME_CLAIM` | `preferred_username` | Override the username claim path. |
| `HINDSIGHT_API_OIDC_ROLES_TRANSFORM` | per profile | `array` / `space_delimited` / `csv` / `map_keys`. |
| `HINDSIGHT_API_OIDC_CLIENT_ID` | unset | Substituted for `<client>` in a roles path (Keycloak client roles). |

Legacy `HINDSIGHT_API_TENANT_{ISSUER,JWKS_URL,AUDIENCE,TENANT_CLAIM}` names are
still honored as fallbacks.

## Tenancy (`HINDSIGHT_API_TENANT_*`)

| Variable | Default | Description |
|---|---|---|
| `HINDSIGHT_API_TENANT_SCHEMA_PREFIX` | `tenant` | Schema name = `{prefix}_{tenant}`. |
| `HINDSIGHT_API_TENANT_DEFAULT_TENANT` | unset | **Single-tenant mode.** Tokens without a `tenant` claim map here — no IdP tenant mapper needed. |
| `HINDSIGHT_API_TENANT_KNOWN_TENANTS` | unset | Comma-separated tenants to pre-provision (migrate schemas) on boot. |
| `HINDSIGHT_API_TENANT_INTERNAL_API_KEY` | unset | A static service key that bypasses OIDC and maps to a fixed schema (for the control-plane UI). Set it equal to the CP's `HINDSIGHT_CP_DATAPLANE_API_KEY`. |
| `HINDSIGHT_API_TENANT_INTERNAL_SCHEMA` | `public` | The schema the internal key maps to. |

# Profiles

A profile is a preset of *where the claims live*. Override any single path if your
setup differs.

| Profile | roles claim | tenant claim | username claim | transform |
|---|---|---|---|---|
| `keycloak` | `realm_access.roles` | `tenant` | `preferred_username` | array |
| `auth0` | `https://<ns>/roles` (override) | `tenant` | `preferred_username` | array |
| `cognito` | `cognito:groups` | `custom:tenant` | `cognito:username` | array |
| `okta` | `groups` | `tenant` | `preferred_username` | array |
| `entra` | `roles` | `tenant` | `preferred_username` | array |
| `zitadel` | `urn:zitadel:iam:org:project:*:roles` | `tenant` | `preferred_username` | map_keys |
| `authentik` | `groups` | `tenant` | `preferred_username` | array |
| `dex` | — | `tenant` | `email` | array |
| `generic` | `roles` | `tenant` | `preferred_username` | array |

Claim **paths** resolve in this order: (1) an exact literal top-level key — so
URL / `urn:` / `cognito:` claim names work verbatim; (2) a `*` glob over top-level
keys, merging matches (Zitadel per-project claims); (3) a dotted nested walk
(`realm_access.roles`). A `<client>` token is replaced by `..._CLIENT_ID`.

# Example

Single-tenant Keycloak, discovery-driven:

```bash
HINDSIGHT_API_TENANT_EXTENSION=hs_oidc.tenant:OIDCTenantExtension
HINDSIGHT_API_OIDC_ISSUER=http://localhost:8080/realms/hindsight
HINDSIGHT_API_OIDC_PROFILE=keycloak
HINDSIGHT_API_OIDC_AUDIENCE=hindsight
HINDSIGHT_API_TENANT_DEFAULT_TENANT=main
```

Multi-tenant, JWKS fetched in-network while validating the public issuer:

```bash
HINDSIGHT_API_OIDC_ISSUER=https://id.example.com/realms/acme
HINDSIGHT_API_OIDC_JWKS_URL=http://keycloak:8080/realms/acme/protocol/openid-connect/certs
HINDSIGHT_API_OIDC_PROFILE=keycloak
HINDSIGHT_API_TENANT_KNOWN_TENANTS=acme,globex
```

Verify any config against a live issuer + token with `hs-oidc doctor` — see the
[client-configuration guide](client-configuration.md). Design rationale for these
choices is in [design-decisions.md](design-decisions.md).
