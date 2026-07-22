#!/usr/bin/env bash
# Minimal end-to-end: get a token from Keycloak, call the protected Hindsight API.
set -euo pipefail

ISS="${ISS:-http://localhost:8280/realms/hindsight}"
API="${API:-http://localhost:8893}"
USER="${USER_NAME:-alice}"

echo "1) no token → expect 401"
curl -s -o /dev/null -w '   %{http_code}\n' "$API/v1/default/banks"

echo "2) get an access token for $USER"
TOKEN=$(curl -s -X POST "$ISS/protocol/openid-connect/token" \
  -d grant_type=password -d client_id=hindsight -d client_secret=hindsight-dev-secret \
  -d "username=$USER" -d "password=$USER" | jq -r .access_token)

echo "3) with token → expect 200"
curl -s -o /dev/null -w '   %{http_code}\n' -H "Authorization: Bearer $TOKEN" "$API/v1/default/banks"

echo "4) retain + recall"
curl -s -X POST "$API/v1/default/banks/notes/memories" \
  -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"items":[{"content":"Alice prefers dark roast","context":"pref"}]}' | jq -r '.success // .'
