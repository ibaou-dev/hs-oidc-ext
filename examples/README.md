# Example: OIDC-protected Hindsight with Keycloak

A complete, runnable stack: a Keycloak realm + a Hindsight server whose API
requires an OIDC token. Ports are non-standard (Keycloak `8280`, API `8893`, UI
`9998`) so it won't collide with anything.

## 1. Bring it up

```bash
docker compose -f examples/compose.yaml up -d
# wait ~30s for Keycloak to import the realm and Hindsight to migrate
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
