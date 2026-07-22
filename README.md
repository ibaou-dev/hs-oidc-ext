# hs-oidc-ext

**Generic OIDC authentication + multi-tenancy for the [Hindsight](https://github.com/vectorize-io/hindsight) memory API.**

Put any standards-compliant OpenID Connect provider — Keycloak, Auth0, Cognito,
Okta, Entra ID, Zitadel, Authentik, … — in front of a Hindsight server. Users and
agents authenticate with an OIDC token; each tenant is isolated in its own Postgres
schema. Loaded via environment variables — **zero changes to Hindsight core**.

```
   ┌────────┐  OIDC token   ┌───────────────────────────┐   schema
   │ client │ ────────────▶ │  Hindsight API            │  ┌──────────────┐
   │ / agent│               │  + hs-oidc TenantExtension │─▶│ tenant_<name>│
   └────────┘               └───────────────────────────┘  └──────────────┘
        ▲  Bearer <token>              │ verify (JWKS)
        │                              ▼
   ┌────────────┐   discovery   ┌──────────────┐
   │ OIDC / IdP │ ◀──────────── │ .well-known  │
   └────────────┘               └──────────────┘
```

> **Scope.** This extension **authenticates** and **isolates tenants** — an
> authenticated caller gets full access, which is how Hindsight was designed to
> work. Fine-grained per-user/per-bank **authorization (RBAC)** is a *separate*
> extension that builds on this one; it is intentionally out of scope here. See
> [docs/design-decisions.md](docs/design-decisions.md) (ADR-008).

## Why this exists

Hindsight's HTTP API is unauthenticated by default. In a central / multi-user
deployment you want SSO — and you don't want to hardcode a single vendor. The only
thing that actually differs between OIDC providers is *where the claims live*, so
this extension makes that pure configuration: pick a **profile**, point it at an
**issuer**, done.

| Feature | |
|---|---|
| **Any OIDC provider** | 9 built-in profiles + full override; verified live against Keycloak, Zitadel, Authentik, Dex |
| **Discovery-first** | one required setting — the issuer; `jwks_uri` and endpoints are auto-discovered |
| **Multi-tenant or single-tenant** | tenant claim → dedicated Postgres schema, or one shared schema |
| **`hs-oidc doctor`** | a CLI that probes an issuer + token and prints the exact config |
| **Protects UI *and* backend** | the API requires a token; an optional proxy adds SSO to the web UI |
| **No core fork** | loaded via `HINDSIGHT_API_*` env vars |

## Install

```bash
pip install hs-oidc-ext      # into the same environment as the Hindsight server
```

## Quickstart (Keycloak, single-tenant)

A complete, runnable stack lives in [`examples/`](examples/). The short version:

```bash
# 1. Server env — authenticate every request via Keycloak, one shared tenant:
HINDSIGHT_API_TENANT_EXTENSION=hs_oidc.tenant:OIDCTenantExtension
HINDSIGHT_API_OIDC_ISSUER=http://localhost:8080/realms/hindsight
HINDSIGHT_API_OIDC_PROFILE=keycloak
HINDSIGHT_API_OIDC_AUDIENCE=hindsight
HINDSIGHT_API_TENANT_DEFAULT_TENANT=main

# 2. Link it (prints the resolved claim mapping + copy-paste config):
hs-oidc doctor http://localhost:8080/realms/hindsight --profile keycloak --audience hindsight --token "$JWT"

# 3. Call the now-protected API with a bearer token:
curl -H "Authorization: Bearer $JWT" http://localhost:8888/v1/default/banks
```

Full walk-through: [`examples/README.md`](examples/README.md) and the
[Keycloak provider guide](docs/providers/keycloak.md).

## Configuration at a glance

The only required setting is the issuer; everything else has a sensible default.

```bash
# --- shared OIDC config (auto-discovers jwks_uri + endpoints) ---
HINDSIGHT_API_OIDC_ISSUER=https://id.example.com/realms/acme
HINDSIGHT_API_OIDC_PROFILE=keycloak            # keycloak|auth0|cognito|okta|entra|zitadel|authentik|dex|generic
HINDSIGHT_API_OIDC_AUDIENCE=hindsight          # optional; validated if set

# --- tenancy extension ---
HINDSIGHT_API_TENANT_EXTENSION=hs_oidc.tenant:OIDCTenantExtension
HINDSIGHT_API_TENANT_DEFAULT_TENANT=main       # single-tenant mode (no IdP tenant mapper needed)
# ...or multi-tenant: emit a `tenant` claim and set KNOWN_TENANTS to pre-provision.
```

The complete reference — every variable, every profile, the discovery/override
rules — is in [docs/configuration.md](docs/configuration.md). Client-side and
central-server-mode setup (protecting the **backend**, not just the UI) is in
[docs/client-configuration.md](docs/client-configuration.md).

## Provider profiles

Verification (JWKS, RS256, `iss`/`aud`/`exp`) is identical everywhere; a **profile**
is a preset of *where the claims live*:

| Profile | roles claim | notes |
|---|---|---|
| `keycloak` | `realm_access.roles` | client roles: `resource_access.<client>.roles` |
| `auth0` | `https://<ns>/roles` | namespaced; set your namespace |
| `cognito` | `cognito:groups` | `cognito:username`, `custom:tenant` |
| `okta` / `authentik` | `groups` | |
| `entra` | `roles` | Entra ID app roles |
| `zitadel` | `urn:zitadel:iam:org:project:*:roles` | wildcard across projects; nested-map → `map_keys` |
| `dex` | — | login/verify only; `username ← email` |
| `generic` | `roles` | spec baseline |

*(roles are surfaced for the forthcoming RBAC extension; this extension itself
needs only `iss`/`sub`/`exp` + optionally the `tenant` claim.)*

## The optional proxy trick (SSO for the web UI)

The API is protected by the token. To also put SSO in front of the stock Hindsight
**control-plane UI** without forking it, an [`oauth2-proxy` + a small SSO shell](examples/proxy/)
sits in front. See [docs/proxy-trick.md](docs/proxy-trick.md) for the design (and
why the identity header is an iframe wrapper — a React 19 finding).

## Documentation

- [Configuration reference](docs/configuration.md) — every setting + profiles
- [Client & central-server-mode setup](docs/client-configuration.md) — protecting the backend; SDK/CLI/agent tokens
- [Design decisions (ADRs)](docs/design-decisions.md) — every choice, with rationale
- [The proxy trick](docs/proxy-trick.md) — SSO for the web UI
- [Diagrams](docs/diagrams/) — sequence & flow (mermaid)
- [Provider guides](docs/providers/) — Keycloak (primary), and the others
- [Runbook: fresh setup](docs/runbooks/fresh-setup-keycloak.md)

## Develop

Python 3.11–3.13 (the range CI covers). With pip:

```bash
pip install -e ".[dev]"
pre-commit install
ruff check . && ruff format --check . && mypy && pytest    # the full gate
```

...or with [uv](https://docs.astral.sh/uv/) (useful if your system Python is newer
than 3.13):

```bash
uv venv --python 3.13 && uv pip install -e ".[dev]"
.venv/bin/ruff check . && .venv/bin/mypy && .venv/bin/pytest
```

Tests are offline and deterministic (throwaway RSA keypair, stubbed JWKS); a
**profile matrix** proves claim extraction for every vendor above — no live IdP
required. CI runs the same gate on 3.11–3.13.

## License

[MIT](LICENSE)
