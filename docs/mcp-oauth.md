---
type: Guide
title: MCP OAuth — browser login from Claude Code (and other MCP hosts)
description: Let an MCP host discover the login and authenticate via the browser (no pasted token) against an OIDC-protected Hindsight, using a metadata shim + the discovery extension + Keycloak. Verified end-to-end with real Claude Code.
tags: [mcp, oauth, oidc, claude-code, discovery, keycloak, shim]
timestamp: 2026-07-19T00:00:00Z
---

# Goal

When Hindsight is OIDC-protected, an MCP host such as **Claude Code** should let a
human log in **through the browser** and connect — no manually-pasted token, and
auto-refresh so the session survives token expiry. This is the MCP Authorization
flow (OAuth 2.1 + RFC 9728/8414/7591/8707). Verified end-to-end with real Claude
Code 2.1.217:

```
claude mcp add --transport http hindsight http://localhost:8899/mcp
/mcp → Authenticate → browser → Keycloak login → ✔ Connected
```

# Why a shim is required

An MCP host discovers where to log in from **Protected Resource Metadata**
(RFC 9728) served at a well-known path. Hindsight embeds FastMCP, which serves an
**empty** metadata document at the canonical paths and provides **no hook** to
configure it — so it *shadows* the correct metadata this extension publishes at
`/ext/oauth-protected-resource`. The host reads the empty canonical doc, fails to
find the authorization server, and can't log in.

The fix is a tiny **reverse-proxy shim** (Caddy) in front of Hindsight that routes
the canonical metadata paths to this extension's endpoint (the single source of
truth) and streams everything else through. See ADR-011 in
[design-decisions.md](design-decisions.md).

```
Claude Code ──▶ shim (:8899) ──▶ Hindsight (:8888) + hs-oidc extension
                 │ overrides /mcp/.well-known/oauth-protected-resource
                 ▼ (→ names Keycloak as the authorization server)
              Keycloak (:8280)  ◀── browser login, DCR, tokens
```

# The pieces

1. **Discovery extension** (`hs_oidc.http:OIDCDiscoveryExtension`) — serves the
   RFC 9728 document and adds `resource_metadata=` to the MCP `401`.
2. **The shim** ([`examples/mcp/`](../examples/mcp/)) — overrides FastMCP's empty
   canonical metadata; run the host against the **shim's** URL.
3. **`PUBLIC_URL` = the shim URL** — so the metadata `resource` and the 401 pointer
   use the address the host actually connects to.
4. **`offline_access` advertised** in `scopes_supported` — the host self-registers
   (DCR) for exactly the scopes we publish, so this is how it gets a **refresh
   token**.
5. **Keycloak setup** (see below) — DCR enablement + a token audience.

# Run it

```bash
# base stack + the MCP shim overlay
docker compose -f examples/compose.yaml -f examples/compose.mcp.yaml up -d
# configure Keycloak for MCP OAuth (idempotent)
examples/mcp/setup-mcp-oauth.sh
# point Claude Code at the SHIM (:8899), not Hindsight directly
claude mcp add --transport http hindsight http://localhost:8899/mcp
# then, inside Claude Code:  /mcp  → Authenticate  (a browser opens)
#   or from the shell:       claude mcp login hindsight
```

Log in as `alice` / `alice`. `claude mcp list` should show **✔ Connected**.

# What the Keycloak setup does (and why)

`setup-mcp-oauth.sh` applies what a realm import can't reliably set:

- **Enables anonymous DCR** — Keycloak blocks self-registration by default
  (Trusted Hosts + Allowed Client Scopes policies). Claude Code registers its own
  client, so these must be relaxed. **⚠ Security:** this opens anonymous DCR; for
  production, scope the DCR policies or pre-register a client (below).
- **Stamps a token audience** — DCR clients get no audience mapper and Keycloak
  ignores the RFC 8707 `resource`, so tokens arrive with `aud: null` and the
  resource server rejects them. The script adds an audience mapper to the built-in
  **`basic`** scope, which *every* client (including DCR ones) receives, so all
  tokens carry `aud=hindsight`.

`offline_access` (the refresh-token role) is granted to the demo users in
[`keycloak-realm.json`](../examples/keycloak-realm.json).

# Production: pre-registered client instead of anonymous DCR

Anonymous DCR is convenient but permissive. For production, **pre-register one
public client** in your IdP (PKCE, redirect `http://localhost:<port>/callback`,
scopes incl. `offline_access`, an audience mapper) and have users run:

```bash
claude mcp add --transport http hindsight http://localhost:8899/mcp \
  --client-id <your-client-id> --callback-port <port>
```

Note: with `--client-id`, some hosts assume the authorization server lives at the
MCP origin — verify discovery still resolves to your IdP. The DCR path is the
zero-config option; pre-registration is the locked-down one.

# For the plugin / setup page (what to tell users)

> This server uses SSO. Add it and sign in through your browser — no API key:
> ```
> claude mcp add --transport http hindsight https://memory.example.com/mcp
> ```
> Then run `/mcp`, choose **Authenticate**, and log in. Your session refreshes
> automatically; if it ever expires, `/mcp` will prompt you to re-authenticate.

# Troubleshooting (failure → cause)

| Symptom | Cause / fix |
|---|---|
| `/mcp` shows **Failed / Needs authentication**, host can't discover login | FastMCP's empty metadata is shadowing ours → ensure the host points at the **shim** URL and the shim is up |
| `Policy 'Trusted Hosts' rejected … Host not trusted` | anonymous DCR blocked → run `setup-mcp-oauth.sh` |
| `invalid_scope: … offline_access` | client didn't register for `offline_access` → confirm the extension advertises it (`HINDSIGHT_API_OIDC_SCOPES`) |
| `Offline tokens not allowed for the user or client` | user lacks the `offline_access` realm role → granted in the realm JSON |
| Login succeeds but list shows **Needs authentication**; token `aud: null` | audience mapper missing → run `setup-mcp-oauth.sh` (adds it to `basic`) |

# See also

- [Design decisions](design-decisions.md) — ADR-011 (FastMCP shadowing + shim)
- [Configuration reference](configuration.md) — `HINDSIGHT_API_OIDC_PUBLIC_URL`, `_RESOURCE`, `_SCOPES`
- [Client & central-server-mode setup](client-configuration.md) — non-MCP clients
