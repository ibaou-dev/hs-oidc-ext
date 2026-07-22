---
type: Runbook
title: Fresh setup — protect a new Hindsight server with Keycloak + OIDC
description: Stand up Keycloak and an OIDC-protected Hindsight server from a clean clone, and verify the backend rejects unauthenticated calls and accepts tokens.
tags: [oidc, keycloak, setup, runbook, hindsight]
timestamp: 2026-07-19T00:00:00Z
---

# Trigger

You cloned `hs-oidc-ext` and want a fresh Hindsight server where the API is
protected by Keycloak/OIDC — from zero to a working, authenticated call.

# Preconditions

- Docker + Docker Compose v2, `curl`, `jq`.
- Python 3.11+ (only to run `hs-oidc doctor`, optional).
- Ports free: `8280` (Keycloak), `8893` (API), `9998` (UI). They are non-standard
  on purpose; change them in `examples/compose.yaml` if needed.

# Steps

1. **Bring up the stack** (Keycloak with an auto-imported realm + an
   OIDC-protected Hindsight):

   ```bash
   docker compose -f examples/compose.yaml up -d
   ```

2. **Wait for readiness** (Keycloak imports the realm; Hindsight migrates schemas):

   ```bash
   # Keycloak discovery returns 200 when ready
   until curl -sf http://localhost:8280/realms/hindsight/.well-known/openid-configuration >/dev/null; do sleep 3; done
   ```

3. **(Optional) install the doctor** for a readable check:

   ```bash
   pip install -e .        # from the repo root
   ```

# Verification

```bash
API=http://localhost:8893
ISS=http://localhost:8280/realms/hindsight

# 1. Unauthenticated → 401
test "$(curl -s -o /dev/null -w '%{http_code}' $API/v1/default/banks)" = 401 && echo "OK: 401 without token"

# 2. Get a token and call again → 200
TOKEN=$(curl -s -X POST "$ISS/protocol/openid-connect/token" \
  -d grant_type=password -d client_id=hindsight -d client_secret=hindsight-dev-secret \
  -d username=alice -d password=alice | jq -r .access_token)
test "$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $TOKEN" $API/v1/default/banks)" = 200 \
  && echo "OK: 200 with token"

# 3. Inspect the token (optional)
hs-oidc doctor "$ISS" --profile keycloak --audience hindsight --token "$TOKEN"

# 4. Retain + recall through the protected API
curl -s -X POST "$API/v1/default/banks/notes/memories" -H "Authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -d '{"items":[{"content":"hello from a fresh setup","context":"smoke"}]}'
```

Expected: `401` without a token, `200` with one; doctor shows `username=alice`,
`tenant=acme`, signature verified.

# Optional: SSO for the web UI

See [`examples/proxy/`](../../examples/proxy/README.md).

# Teardown

```bash
docker compose -f examples/compose.yaml down -v
```

# See also

- [Configuration reference](../configuration.md)
- [Client & central-server-mode setup](../client-configuration.md)
- [Keycloak provider guide](../providers/keycloak.md)
