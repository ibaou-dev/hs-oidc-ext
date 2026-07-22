# Example: OIDC-protected Hindsight with Keycloak

A complete, runnable stack: a Keycloak realm + a Hindsight server whose API
requires an OIDC token. Ports are non-standard (Keycloak `8280`, API `8893`, UI
`9998`) to avoid common defaults.

> **Port already in use?** Every host port is overridable — the whole Hindsight
> service (API *and* UI share one container) fails to start if either is taken:
> ```bash
> HS_KC_PORT=18280 HS_API_PORT=18893 HS_UI_PORT=19998 docker compose -f examples/compose.yaml up -d
> ```
> `HS_KC_PORT` also feeds the issuer, so it stays consistent. If you remap ports,
> set the same values in the commands below (and pass `UPSTREAM` to the proxy).

## 1. Bring it up

```bash
docker compose -f examples/compose.yaml up -d
```

Wait for both services — Keycloak imports the realm, then Hindsight migrates
schemas (the API refuses connections for a few extra seconds after Keycloak is up):

```bash
until curl -sf http://localhost:8280/realms/hindsight/.well-known/openid-configuration >/dev/null; do sleep 3; done
until [ "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8893/v1/default/banks)" != 000 ]; do sleep 2; done
echo "ready"
```

The realm `hindsight` is imported with a confidential client `hindsight`
(secret `hindsight-dev-secret`) and two users — `alice`/`alice`, `bob`/`bob`.

## 2. Prove the API is protected

```bash
# No token → 401
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8893/v1/default/banks   # 401
```

## 3. Get a token and call the API

```bash
ISS=http://localhost:8280/realms/hindsight
TOKEN=$(curl -s -X POST "$ISS/protocol/openid-connect/token" \
  -d grant_type=password -d client_id=hindsight -d client_secret=hindsight-dev-secret \
  -d username=alice -d password=alice | jq -r .access_token)

# With a token → 200, routed to the caller's tenant schema (tenant_acme)
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8893/v1/default/banks | jq

# Retain a memory...
curl -s -X POST http://localhost:8893/v1/default/banks/notes/memories \
  -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"items":[{"content":"Alice prefers dark roast","context":"pref"}]}' | jq

# ...then recall it (POST .../memories/recall — results are under `.results`)
curl -s -X POST http://localhost:8893/v1/default/banks/notes/memories/recall \
  -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"query":"what does Alice drink?"}' | jq '.results'
```

## 4. Inspect what the token carries

```bash
hs-oidc doctor "$ISS" --profile keycloak --audience hindsight --token "$TOKEN"
```

You should see `username=alice`, `tenant=acme`, roles resolved, and the signature
verified against Keycloak's JWKS.

## 5. (Optional) SSO for the web UI

The control-plane UI at http://localhost:9998 has no login of its own. To put SSO
in front of it, see [`proxy/`](proxy/).

## Modes

- **Single-tenant** (protect one shared memory space): drop the `tenant` mapper
  from the realm and rely on `HINDSIGHT_API_TENANT_DEFAULT_TENANT`.
- **Multi-tenant** (as configured here): each user carries a `tenant` claim and
  lands in its own Postgres schema.

## Tear down

```bash
docker compose -f examples/compose.yaml down -v
```

## Client code

See [`client/`](client/) for Python SDK, agent (client-credentials), and curl
snippets that present the token.
