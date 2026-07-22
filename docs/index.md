# hs-oidc-ext documentation

Open Knowledge Format bundle for the generic OIDC authentication + multi-tenancy
extension for Hindsight. Start with the [README](../README.md) for the overview;
this bundle holds the durable reference material.

## Concepts

- [Configuration reference](configuration.md) — every env var, the profiles, discovery rules `Config`
- [Client & central-server-mode setup](client-configuration.md) — protecting the backend; SDK/CLI/agent tokens `Guide`
- [Design decisions (ADRs)](design-decisions.md) — every architectural choice `Reference`
- [The proxy trick](proxy-trick.md) — optional SSO for the web UI `Component`
- [Diagrams](diagrams/sequences-and-flows.md) — sequence & flow (mermaid) `Reference`

## Providers

- [Keycloak](providers/keycloak.md) — the primary, worked example `Guide`

## Runbooks

- [Fresh setup with Keycloak](runbooks/fresh-setup-keycloak.md) — zero to protected server `Runbook`

## Changes

See [log.md](log.md).
