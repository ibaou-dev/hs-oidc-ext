---
type: Component
title: The optional proxy trick — SSO for the Hindsight web UI
description: An oauth2-proxy + small SSO-shell reverse proxy that puts OIDC login and an identity header in front of the stock Hindsight control-plane UI, with zero fork.
tags: [oidc, proxy, oauth2-proxy, sso, control-plane, ui]
timestamp: 2026-07-19T00:00:00Z
---

# Overview

The extension protects the **API**. The stock Hindsight **control-plane web UI**,
however, has no login of its own. This optional layer puts SSO in front of it
**without forking Hindsight** — a bundle you run beside the server. It is a
quality-of-life add-on, not required for backend protection.

Runnable version: [`examples/proxy/`](../examples/proxy/).

```
browser ──▶ oauth2-proxy ──▶ sso-shell ──▶ stock control-plane
             OIDC login       identity      (unmodified)
             (Keycloak)       header +
                              iframe
```

# Two pieces

## 1. oauth2-proxy — the login gate

[`oauth2-proxy`](https://github.com/oauth2-proxy/oauth2-proxy) sits in front and
does the OIDC dance against the same issuer the server uses:

- `--provider=oidc --oidc-issuer-url=<issuer>`
- `--pass-access-token` — forwards the user's access token upstream as
  `X-Forwarded-Access-Token`
- `--backend-logout-url=<issuer>/protocol/openid-connect/logout?id_token_hint={id_token}`
  — RP-initiated logout, so "sign out" actually ends the IdP session

## 2. The SSO shell — identity header without forking

A tiny reverse proxy renders a thin **identity header** above the real UI. It must
not inject into the UI's DOM: React 19's streaming SSR strips any foreign node it
finds (hydration error #418). Instead, for a top-level navigation it serves a
wrapper page *it owns* — a **non-sticky** header (username / tenant) above an
`<iframe>` of the real control-plane. Everything else is proxied straight through.
See ADR-009 in [design-decisions.md](design-decisions.md).

# The embedded control-plane needs a dataplane key

oauth2-proxy authenticates the **user**, but the bundled control-plane is a
*separate SPA* that makes its own calls to the (now protected) dataplane API —
with **one static key**, not the user's token. If that key isn't accepted, the
embedded UI shows *"Enter your access key / Authentication failed: Missing bearer
token"* even though you are logged in.

Fix: give the extension the same key the control-plane uses, via the internal
service-key bypass (see [ADR-007](design-decisions.md)):

```bash
HINDSIGHT_API_TENANT_INTERNAL_API_KEY=cp-internal-service-key-demo   # == the CP's key
HINDSIGHT_API_TENANT_INTERNAL_SCHEMA=tenant_acme                     # schema the UI browses
HINDSIGHT_CP_DATAPLANE_API_KEY=cp-internal-service-key-demo          # the CP's dataplane key
```

Consequence: the UI browses one **fixed schema** (`INTERNAL_SCHEMA`) for everyone
who signs in — a shared memory space, consistent with the "authenticated = full
access" model. Per-user schemas in the UI would require the CP to forward each
user's OIDC token as its dataplane key, which the stock CP does not do (that is the
future "tap into the control-plane" work). The [example stack](../examples/compose.yaml)
sets these three variables already.

# Sequence

```mermaid
sequenceDiagram
    participant B as Browser
    participant P as oauth2-proxy
    participant K as Keycloak
    participant S as SSO shell
    participant C as Control-plane

    B->>P: GET /
    P->>K: redirect to login
    K-->>B: login page
    B->>K: credentials
    K-->>P: code → tokens
    P->>S: proxy + X-Forwarded-Access-Token
    S-->>B: wrapper page (header + <iframe src=/>)
    B->>S: iframe loads /
    S->>C: proxy (with token)
    C-->>B: control-plane UI
    Note over B,S: "Sign out" → oauth2-proxy → RP-initiated logout at Keycloak
```

# Scope note

This layer shows **who is signed in**; it does not do per-user authorization. In
line with ADR-008, per-user/per-bank filtering belongs to the separate RBAC
extension, not here. The shell grants the signed-in user the same full access the
API already allows.

# Configuration

See [`examples/proxy/README.md`](../examples/proxy/README.md) for the compose file,
the `oauth2-proxy` flags, and the shell proxy. The only client-registration detail:
add `http://localhost:4180/oauth2/callback` to the OIDC client's redirect URIs and
enable RP-initiated logout (`post.logout.redirect.uris`).
