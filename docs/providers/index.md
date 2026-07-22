# Providers

Provider-specific guides. Verification is identical everywhere; a **profile**
selects where each vendor's claims live (see [configuration](../configuration.md)).

- [Keycloak](keycloak.md) — the primary, worked example `Guide`

Other profiles ship built-in and are covered in the configuration reference:
`auth0`, `cognito`, `okta`, `entra`, `zitadel`, `authentik`, `dex`, `generic`.
Link any of them with `hs-oidc doctor <issuer> --profile <name> --token <jwt>`.
