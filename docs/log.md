# Update Log

## 2026-07-19

* **Initialization**: OKF documentation bundle for `hs-oidc-ext` — the generic OIDC
  authentication + multi-tenancy extension for Hindsight.
* **Creation**: [Configuration reference](configuration.md) — every env var, the nine
  vendor profiles, discovery/override rules.
* **Creation**: [Client & central-server-mode setup](client-configuration.md) — how
  clients (SDK/CLI/agents/MCP) authenticate to a protected central server; token
  acquisition + refresh; protecting the backend, not just the UI.
* **Creation**: [Design decisions](design-decisions.md) — ADR-001..010, including the
  RBAC-is-separate boundary (ADR-008) and the two bugs found by live providers.
* **Creation**: [Proxy trick](proxy-trick.md) — optional SSO shell for the web UI.
* **Creation**: [Diagrams](diagrams/index.md) — backend auth, discovery, claim
  resolution, tenant mapping (mermaid).
* **Creation**: [Keycloak provider guide](providers/keycloak.md) and
  [Fresh-setup runbook](runbooks/fresh-setup-keycloak.md).
* **Creation**: [MCP OAuth](mcp-oauth.md) + ADR-011 — browser login from an MCP host
  (Claude Code) via RFC 9728 discovery. Adds `OIDCDiscoveryExtension`, a Caddy
  metadata **shim** (FastMCP serves empty canonical metadata with no config hook),
  and a Keycloak setup script (DCR + `aud` on the `basic` scope). Verified
  end-to-end with real Claude Code 2.1.217 → ✔ Connected.
