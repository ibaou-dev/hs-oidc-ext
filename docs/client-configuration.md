---
type: Guide
title: Client & central-server-mode setup — protecting the backend
description: How clients (SDKs, CLI, agents, MCP) authenticate to an OIDC-protected central Hindsight server, and how tokens are obtained and refreshed.
tags: [oidc, client, central, backend, sdk, agents, tokens]
timestamp: 2026-07-19T00:00:00Z
---

# Goal

When you enable this extension, **the Hindsight HTTP API itself becomes
protected** — not just the web UI. Every call to `/v1/...` must carry a valid OIDC
token, or it is rejected with `401`. This guide shows how each kind of client
obtains a token and presents it, in **central-server mode** (one shared Hindsight
serving many users/agents).

```
  ┌── interactive user ──┐   auth-code flow      ┌─────────────┐
  │  Python SDK / CLI    │ ───────────────────▶  │  OIDC / IdP │
  ├── service / agent ───┤   client_credentials  └─────┬───────┘
  │  M2M                 │ ◀───── access token ────────┘
  └──────────┬───────────┘
             │ Authorization: Bearer <access token>
             ▼
   ┌───────────────────────────────────────┐
   │  central Hindsight  +  hs-oidc-ext      │  → tenant schema
   └───────────────────────────────────────┘
```

# Server side (recap)

Enable the extension on the central server (see [configuration](configuration.md)):

```bash
HINDSIGHT_API_TENANT_EXTENSION=hs_oidc.tenant:OIDCTenantExtension
HINDSIGHT_API_OIDC_ISSUER=https://id.example.com/realms/acme
HINDSIGHT_API_OIDC_PROFILE=keycloak
HINDSIGHT_API_OIDC_AUDIENCE=hindsight
HINDSIGHT_API_TENANT_DEFAULT_TENANT=main     # or multi-tenant via the tenant claim
```

From now on the backend answers `401` without a token and routes an authenticated
caller to its tenant's schema.

# Getting a token

## Interactive users (authorization-code flow)

A person logs in at the IdP and receives an access token. Any standard OIDC client
library does this; for quick tests, mint one with the password grant (dev only):

```bash
ISS=https://id.example.com/realms/acme
TOKEN=$(curl -s -X POST "$ISS/protocol/openid-connect/token" \
  -d grant_type=password -d client_id=hindsight -d client_secret=$SECRET \
  -d username=alice -d password=… | jq -r .access_token)
```

## Services & agents (client-credentials, the common central case)

Background agents that write memory authenticate machine-to-machine. Create a
confidential client (or service account) at the IdP and use the client-credentials
grant:

```bash
TOKEN=$(curl -s -X POST "$ISS/protocol/openid-connect/token" \
  -d grant_type=client_credentials \
  -d client_id=memory-agent -d client_secret=$AGENT_SECRET | jq -r .access_token)
```

Give the client the right `aud` (matching `HINDSIGHT_API_OIDC_AUDIENCE`) and, for
multi-tenant, a `tenant` claim (via a mapper / scope). Verify what a token actually
carries with:

```bash
hs-oidc doctor "$ISS" --profile keycloak --audience hindsight --token "$TOKEN"
```

# Presenting the token

The token is the client's **bearer credential** — Hindsight reads it as the
`api_key`.

## Python SDK

```python
from hindsight_client import Hindsight

client = Hindsight(
    base_url="https://memory.example.com",
    api_key=access_token,          # ← the OIDC access token (sent as Bearer)
)
client.retain(bank_id="notes", content="…")
```

## Raw HTTP / CLI

```bash
curl -H "Authorization: Bearer $TOKEN" https://memory.example.com/v1/default/banks
```

## MCP clients

If you expose Hindsight's MCP endpoint, pass the same bearer token in the MCP
client's HTTP `Authorization` header. Tools then run under the caller's tenant.

# Token lifetime & refresh

Access tokens are short-lived (Keycloak default: 5 minutes). Long-running clients
must refresh:

- **Interactive**: keep the refresh token and exchange it before expiry
  (`grant_type=refresh_token`).
- **Agents**: simplest is to re-run the client-credentials request when a call
  returns `401` (or a few seconds before `expires_in`). Wrap the SDK client so it
  re-mints and updates `api_key` on expiry.

The extension caches verified claims per token until the token's own `exp`, so
refresh cost falls on the client, not the server.

# The internal service key (control-plane only)

The bundled control-plane authenticates to the dataplane with **one** static key,
not a user token. Give the extension that key so the CP can browse a fixed schema:

```bash
HINDSIGHT_API_TENANT_INTERNAL_API_KEY=<shared-secret>   # == CP's HINDSIGHT_CP_DATAPLANE_API_KEY
HINDSIGHT_API_TENANT_INTERNAL_SCHEMA=tenant_main
```

Regular clients never use this key — it exists only so the co-located CP works.
Putting **per-user SSO** in front of the CP web UI is the optional
[proxy trick](proxy-trick.md).

# Checklist

1. Server has `HINDSIGHT_API_OIDC_ISSUER` + `PROFILE` (+ `AUDIENCE`) and the
   extension loaded.
2. `curl` without a token → `401`; with a valid token → `200`.
3. Each client sets `api_key` / `Authorization: Bearer` to a **fresh** access token.
4. Agents refresh on expiry.
5. `hs-oidc doctor` shows the token's `username`/`tenant`/`aud` resolving correctly.
