---
type: Reference
title: Design decisions (ADRs)
description: The architecture decisions behind hs-oidc-ext — provider-agnostic OIDC, discovery-first config, the claim resolver, tenancy model, and the RBAC boundary — each with context and consequences.
tags: [adr, design, oidc, architecture, hindsight]
timestamp: 2026-07-19T00:00:00Z
---

# Summary

Each decision is recorded as a short ADR: **Context** (why it came up),
**Decision** (what we chose), **Consequences** (what follows). Several were forced
by verifying against *real* identity providers, not just synthetic tokens.

---

## ADR-001 — Provider-agnostic, not Keycloak-specific

**Context.** The prototype was named and shaped around Keycloak, yet only one line
(the roles claim path) was actually Keycloak-specific. Verification (JWKS, RS256,
`iss`/`aud`/`exp`) is identical for every compliant OIDC provider.

**Decision.** Ship one generic extension. Encode the only real per-vendor
difference — *where claims live* — as declarative **profiles** (`keycloak`,
`auth0`, `cognito`, `okta`, `entra`, `zitadel`, `authentik`, `dex`, `generic`),
with per-claim overrides.

**Consequences.** New providers are usually zero-code (a profile entry + a test).
Verified live against Keycloak, Zitadel, Authentik, and Dex.

---

## ADR-002 — Discovery-first configuration

**Context.** Requiring an admin to hand-configure JWKS URL, endpoints, and claim
paths is error-prone and reads as "rocket science".

**Decision.** Require only the **issuer**. Fetch `jwks_uri` and endpoints from
`{issuer}/.well-known/openid-configuration`. Keep a `JWKS_URL` override for the
container-can't-reach-issuer case. Ship an `hs-oidc doctor` CLI that probes an
issuer + token and prints exactly what resolved.

**Consequences.** The happy path is one variable. Startup does one network call
(cached thereafter).

---

## ADR-003 — A single dotted-path claim resolver with literal/wildcard support

**Context.** Roles live in wildly different places: `realm_access.roles` (nested),
`cognito:groups` (a literal key with a colon), `https://app/roles` (a URL key),
`urn:zitadel:iam:org:project:<id>:roles` (a per-project literal key).

**Decision.** One resolver that (1) prefers an exact literal top-level key, (2)
supports a `*` glob across top-level keys and merges matches, (3) falls back to a
dotted nested walk, with a `<client>` placeholder and value transforms
(`array`/`space_delimited`/`csv`/`map_keys`).

**Consequences.** All observed vendor shapes resolve with config alone. Covered by
a synthetic-token profile matrix.

---

## ADR-004 — Match the issuer exactly (never strip a trailing slash)

**Context.** Authentik advertises an issuer that ends in `/`, and that slash is
part of the token's `iss`. An earlier `issuer.rstrip("/")` made the extension
reject every Authentik token.

**Decision.** Match `iss` exactly, and treat the issuer inside the discovery
document as authoritative.

**Consequences.** Correct across providers regardless of slash conventions. A
regression test pins it. (Found only by running a live provider.)

---

## ADR-005 — Tenancy = one Postgres schema per tenant

**Context.** A shared central server must isolate tenants' memory hard, not by a
filter that can be forgotten.

**Decision.** The `tenant` claim maps to a dedicated Postgres schema
(`{prefix}_{tenant}`). The base `public` schema is migrated first so shared
extensions (`pg_trgm`, `vector`) sit on the query-time `search_path`.

**Consequences.** Hard isolation. A `DEFAULT_TENANT` gives a trivial single-tenant
mode (no IdP mapper needed). Cross-tenant queries are impossible by construction.

---

## ADR-006 — Decouple JWKS URL from the issuer

**Context.** In containerized deployments the public issuer host is often
unreachable from inside the network.

**Decision.** Validate `iss` against the configured issuer, but allow fetching
JWKS from a separate in-network URL.

**Consequences.** Works in split-horizon DNS / docker networks without weakening
issuer validation.

---

## ADR-007 — An internal service-key bypass for the control-plane

**Context.** The bundled control-plane authenticates to the dataplane with a single
static key, not a user token, so it can't present a JWT.

**Decision.** Accept one configured static key that maps to a fixed schema, bypassing
OIDC — used only by the co-located CP.

**Consequences.** The CP works unmodified. Regular clients still require OIDC
tokens. Per-user SSO for the CP is the optional proxy layer, not this key.

---

## ADR-008 — Authorization (RBAC) is a separate extension

**Context.** It is tempting to fold per-user/per-bank write policy into this
extension. Early attempts were opinionated and string-based (inferring bank
ownership from names), which is fragile and rename-hostile.

**Decision.** Keep this extension **authentication + tenancy only** — an
authenticated caller has full access within its tenant (Hindsight's original
model). Fine-grained RBAC ships as a *separate* extension that reuses this one's
`get_verifier()` and claim map.

**Consequences.** A clean, publishable foundation now; RBAC gets the deeper design
it needs without blocking SSO. Roles are still surfaced (via profiles) for that
future extension to consume.

---

## ADR-009 — The optional proxy trick uses an iframe shell (React 19)

**Context.** We wanted a thin identity header above the stock control-plane UI
without forking it. React 19's streaming SSR strips any node injected into its
document (observed: hydration error #418, DOM torn down).

**Decision.** For top-level navigations, serve a small wrapper page we own — a
non-sticky identity header above an `<iframe>` of the real UI — instead of
injecting into React's document. See [proxy-trick.md](proxy-trick.md).

**Consequences.** Robust against React's reconciliation; a clean, optional QoL
layer. Not required for backend protection (the token already protects the API).

---

## ADR-011 — A metadata shim for MCP OAuth (FastMCP shadowing)

**Context.** For an MCP host (Claude Code) to log a user in via the browser, the
server must serve RFC 9728 Protected Resource Metadata at the canonical well-known
path. Hindsight embeds FastMCP, which serves an **empty** metadata document there
and offers no configuration hook — shadowing the correct metadata this extension
publishes at `/ext/oauth-protected-resource`. Verified live: the host reads the
empty canonical doc, can't find the authorization server, and fails. An
`HttpExtension` can't fix this — it mounts only under `/ext/`, so it can neither
override `/mcp/.well-known/*` nor serve the root well-known paths.

**Decision.** Ship a small reverse-proxy **shim** (Caddy) that routes the canonical
protected-resource-metadata paths to this extension's endpoint (single source of
truth) and streams everything else — including `/mcp` — through to Hindsight, which
still validates the token via the tenant extension. Point the MCP host at the shim.

**Consequences.** Real Claude Code completes the full browser OAuth flow and
connects. The shim is one small container; the longer-term fix is an upstream
Hindsight change to configure FastMCP's auth natively. Also surfaced the Keycloak
requirements (DCR enablement, `offline_access` role, an `aud` mapper on the `basic`
scope) — see [mcp-oauth.md](mcp-oauth.md).

---

## ADR-010 — src layout + a strict, pragmatic quality gate

**Context.** A publishable extension needs to pass the usual bars without fighting
untyped host dependencies.

**Decision.** `src/` layout; ruff (lint+format), mypy on `src/` only (host
framework imports skipped), pytest with an offline profile matrix, pre-commit
(incl. a configurable private-identifier guard), and CI on 3.11–3.13.

**Consequences.** Green gate out of the box; type-checking focuses on our code, not
`hindsight_api`'s untyped surface.
