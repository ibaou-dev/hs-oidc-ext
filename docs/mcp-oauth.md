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

# Relationship to Hindsight's official Claude Code plugin

Hindsight's [official Claude Code integration](https://hindsight.vectorize.io/sdks/integrations/claude-code)
is a **plugin** (`claude plugin install hindsight-memory`) that, by default, runs a
**local** `hindsight-embed` daemon (stdio) — personal memory, no server, no auth.
It can point at a remote server via `~/.hindsight/claude-code.json`
(`hindsightApiUrl` + an optional **static** `hindsightApiToken`).

That is a different world from this one. Two connection models:

| | Official plugin | This extension (OIDC) |
|---|---|---|
| Transport | local **stdio** daemon → remote REST | Claude Code → remote **`/mcp`** (HTTP) directly |
| Auth to a remote server | a **static pasted token** (`hindsightApiToken`) | **browser OAuth** (SSO), auto-refreshed |
| Best for | local personal memory, or a trusted static token | **central, governed, multi-user** memory with SSO |

**The important warning for users:** if you point the *official plugin* at an
OIDC-protected central server using a static `hindsightApiToken`, it will **break
when that token expires** — the plugin does not refresh OAuth tokens. For an
OIDC-protected central Hindsight, use **this** path instead:

```
claude mcp add --transport http hindsight https://memory.example.com/mcp
# then /mcp → Authenticate   (browser SSO, auto-refresh)
```

So: **local/personal → the plugin; central/governed/SSO → direct HTTP MCP + OAuth
(here).** They coexist; pick by deployment, not preference.

# Relationship to Hindsight's Cloudflare OAuth proxy

Hindsight ships an
[`cloudflare-oauth-proxy`](https://github.com/vectorize-io/hindsight/tree/main/hindsight-integrations/cloudflare-oauth-proxy)
(a Cloudflare Worker, since v0.5.1) that also puts OAuth 2.1 in front of a
self-hosted `/mcp` — cloud clients like Gemini Spark and claude.ai *require* that
handshake. It solves the same *client-facing* problem this extension does, so it's
a fair question whether one replaces the other. It does not, because of what sits
**behind** the handshake. From its own source and config:

- login is a **single shared password** (`SESSION_SECRET`);
- the user identity is **one hardcoded email** (`userId: ALLOWED_EMAIL` for every
  session);
- downstream it swaps in **one static Hindsight API token** for everyone
  (`Authorization: Bearer ${HINDSIGHT_API_TOKEN}`) — so the server sees a single
  identity and **one shared memory space**;
- it requires **Cloudflare** (account, domain, Tunnel, Worker, KV).

| | `cloudflare-oauth-proxy` | this extension + an IdP |
|---|---|---|
| For | a **solo** self-hoster's personal memory | a **multi-user, governed** team |
| Login / identity | one password → one hardcoded email | real OIDC — each person as themselves |
| Downstream to Hindsight | **one static shared token → one memory space** | **per-user token → per-user tenant/schema** |
| Multi-tenancy, roles | none | tenant claim → schema; roles for RBAC |
| Identity provider | none (the Worker *is* the gate) | any OIDC provider (Keycloak, Auth0, …) |
| Infrastructure | Cloudflare-locked | any Docker host |

The two are complementary: the Cloudflare Worker is a great **single-identity**
front door for one person already on Cloudflare; this extension delegates the
handshake to a **real IdP** so the token carries genuine per-user identity that
drives tenancy (and, later, RBAC) — with no Cloudflare dependency. Same pattern in
front, very different backend.

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
