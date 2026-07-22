# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-07-19

First public release. Generic OIDC authentication + multi-tenancy for the
Hindsight memory API, with MCP OAuth discovery and a client token CLI — verified
end-to-end (including real Claude Code) and from a clean clone.

### Authentication & tenancy
- Provider-agnostic OIDC core: discovery-first configuration and 9 vendor
  **profiles** (Keycloak, Auth0, Cognito, Okta, Entra ID, Zitadel, Authentik, Dex,
  generic), verified live against Keycloak, Zitadel, Authentik, and Dex.
- Dotted-path **claim resolver** with literal URL/`urn:`/`cognito:` keys, a
  `<client>` placeholder, a `*` wildcard, and role transforms.
- `OIDCTenantExtension` — tenant claim → dedicated Postgres schema; single-tenant
  mode via `DEFAULT_TENANT` (no IdP mapper needed). Issuer matched exactly.

### MCP OAuth (browser login from Claude Code)
- `OIDCDiscoveryExtension` serves RFC 9728 protected-resource-metadata; the 401
  carries a `resource_metadata` pointer.
- A Caddy **metadata shim** works around Hindsight's embedded FastMCP serving empty
  canonical metadata; a Keycloak setup script handles DCR + audience.
- Verified end-to-end with real Claude Code 2.1.217 → ✔ Connected, with confirmed
  silent token refresh.

### Client CLI
- `hs-oidc login` / `token` / `logout` — browser (PKCE) sign-in or
  machine-to-machine tokens, cached and auto-refreshed, with discovery from the
  server URL.

### Tooling
- `hs-oidc doctor` linking tool; ruff + mypy + 58 pytest; pre-commit; CI on 3.11–3.13.

### Notes
- Fine-grained per-user/per-bank RBAC is intentionally out of scope — it will ship
  as a separate extension built on this one's verifier + claim map.
