# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] — 2026-07-19

### Added
- Provider-agnostic OIDC core: discovery-first configuration, 9 vendor **profiles**
  (Keycloak, Auth0, Cognito, Okta, Entra ID, Zitadel, Authentik, Dex, generic).
- Dotted-path **claim resolver** with literal URL/`urn:`/`cognito:` keys, a
  `<client>` placeholder, a `*` wildcard, and role transforms
  (`array`/`space_delimited`/`csv`/`map_keys`).
- `hs-oidc doctor` CLI — probe an issuer + token, print the resolved claim mapping
  and a copy-paste env block.
- `OIDCTenantExtension` **single-tenant mode** via `DEFAULT_TENANT` (no IdP tenant
  mapper required).
- Full docs, mermaid diagrams, Keycloak example stack, and the optional SSO-shell
  proxy for the web UI.

### Changed
- Renamed from the Keycloak-specific prototype to the generic `hs-oidc-ext`.
- The issuer is matched **exactly** (never trailing-slash-stripped) and taken from
  the discovery document — fixes token rejection with providers (e.g. Authentik)
  whose issuer carries a trailing slash.

### Notes
- Fine-grained per-user/per-bank RBAC is intentionally **out of scope** — it will
  ship as a separate extension built on this one's verifier + claim map.
