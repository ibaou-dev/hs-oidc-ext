#!/usr/bin/env bash
# Configure Keycloak so an MCP host (Claude Code) can complete OAuth against it.
#
# Two things Keycloak needs that a realm import can't reliably set (Keycloak
# re-creates the default client-registration policies on every import):
#   1. Anonymous Dynamic Client Registration (DCR) — so the host can self-register.
#   2. A token audience the resource server validates — DCR clients get no audience
#      mapper and Keycloak ignores the RFC 8707 `resource`, so tokens arrive with
#      `aud: null` and are rejected. We stamp `aud` via the built-in `basic` scope,
#      which every client (including DCR ones) receives.
#
# Idempotent — safe to re-run. Requires curl + python3.
#
#   ./setup-mcp-oauth.sh
#
# ⚠ SECURITY: this OPENS anonymous DCR (any client may self-register) for a local
# demo. In production, scope the DCR policies instead, or pre-register a client and
# use `claude mcp add --client-id ...`. See docs/mcp-oauth.md.
set -euo pipefail

KC="${KC:-http://localhost:8280}"
REALM="${REALM:-hindsight}"
ADMIN_USER="${ADMIN_USER:-admin}"
ADMIN_PASS="${ADMIN_PASS:-admin}"
AUDIENCE="${AUDIENCE:-hindsight}"   # must match HINDSIGHT_API_OIDC_AUDIENCE

say() { printf '  %s\n' "$*"; }
jqpy() { python3 -c "import sys,json; $1"; }

echo "Configuring $KC realm '$REALM' for MCP OAuth…"

AT="$(curl -s -X POST "$KC/realms/master/protocol/openid-connect/token" \
  -d grant_type=password -d client_id=admin-cli \
  -d "username=$ADMIN_USER" -d "password=$ADMIN_PASS" \
  | jqpy 'print(json.load(sys.stdin)["access_token"])')"
[ -n "$AT" ] || { echo "ERROR: could not get admin token"; exit 1; }
auth=(-H "Authorization: Bearer $AT")

# 1) Enable anonymous DCR: remove the restrictive anonymous policies.
say "enabling anonymous DCR (removing restrictive policies)…"
policies="$(curl -s "${auth[@]}" \
  "$KC/admin/realms/$REALM/components?type=org.keycloak.services.clientregistration.policy.ClientRegistrationPolicy")"
echo "$policies" | jqpy '
import sys,json
for c in json.load(sys.stdin):
    if c.get("subType")=="anonymous":
        print(c["id"], c["providerId"])' | while read -r id name; do
    code="$(curl -s -o /dev/null -w '%{http_code}' -X DELETE "${auth[@]}" \
      "$KC/admin/realms/$REALM/components/$id")"
    say "  removed anonymous policy '$name' ($code)"
done

# 2) Stamp aud=$AUDIENCE via the built-in 'basic' scope (reaches DCR clients too).
basic_id="$(curl -s "${auth[@]}" "$KC/admin/realms/$REALM/client-scopes" \
  | jqpy "print(next((s['id'] for s in json.load(sys.stdin) if s['name']=='basic'),''))")"
[ -n "$basic_id" ] || { echo "ERROR: no 'basic' client scope found"; exit 1; }
exists="$(curl -s "${auth[@]}" \
  "$KC/admin/realms/$REALM/client-scopes/$basic_id/protocol-mappers/models" \
  | jqpy "print(any(m.get('name')=='hindsight-audience' for m in json.load(sys.stdin)))")"
if [ "$exists" = "True" ]; then
    say "audience mapper already present on 'basic'"
else
    body="$(python3 -c "import json;print(json.dumps({
      'name':'hindsight-audience','protocol':'openid-connect',
      'protocolMapper':'oidc-audience-mapper',
      'config':{'included.custom.audience':'$AUDIENCE','id.token.claim':'false','access.token.claim':'true'}}))")"
    code="$(curl -s -o /dev/null -w '%{http_code}' -X POST "${auth[@]}" \
      -H 'content-type: application/json' -d "$body" \
      "$KC/admin/realms/$REALM/client-scopes/$basic_id/protocol-mappers/models")"
    say "added audience mapper aud=$AUDIENCE to 'basic' ($code)"
fi

echo "Done. MCP hosts can now register + obtain tokens accepted by the server."
