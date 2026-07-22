---
type: Reference
title: Diagrams — sequence & flow
description: Mermaid sequence and flow diagrams for OIDC backend authentication, startup discovery, tenant mapping, and claim resolution.
tags: [oidc, diagrams, mermaid, sequence, flow]
timestamp: 2026-07-19T00:00:00Z
---

# Summary

Mermaid diagrams (rendered natively by GitHub) for how `hs-oidc-ext` works. For
the UI SSO sequence, see [proxy-trick.md](../proxy-trick.md).

# Topology

```mermaid
flowchart LR
    subgraph clients [Clients]
      U[Interactive user]
      A[Service / agent]
    end
    IdP[(OIDC provider<br/>Keycloak / Auth0 / …)]
    subgraph server [Central Hindsight]
      API[Hindsight API]
      EXT[hs-oidc TenantExtension]
      API --- EXT
    end
    PG[(Postgres<br/>schema per tenant)]

    U -- auth-code --> IdP
    A -- client-credentials --> IdP
    IdP -- access token --> clients
    clients -- "Bearer token" --> API
    EXT -- "verify (JWKS)" --> IdP
    EXT -- "tenant → schema" --> PG
```

# Backend authentication (per request)

```mermaid
sequenceDiagram
    participant C as Client
    participant H as Hindsight API
    participant E as hs-oidc extension
    participant J as JWKS (cached)
    participant DB as Postgres

    C->>H: POST /v1/.../memories  (Authorization: Bearer <token>)
    H->>E: authenticate(context.api_key)
    alt no / invalid token
        E-->>C: 401 Unauthorized
    else valid
        E->>J: signing key for kid (cached)
        E->>E: verify iss / aud / exp / signature
        E->>E: claims.tenant(token) → tenant
        E->>DB: ensure schema tenant_<name>
        E-->>H: TenantContext(schema)
        H-->>C: 200  (operation runs in tenant schema)
    end
```

# Startup discovery

```mermaid
flowchart TD
    S[Server start] --> Q{JWKS_URL set?}
    Q -- yes --> V[Build verifier with issuer + JWKS_URL]
    Q -- no --> D["GET {issuer}/.well-known/openid-configuration"]
    D --> J[Read jwks_uri + authoritative issuer]
    J --> V
    V --> R[Verifier ready<br/>first token triggers JWKS fetch, then cached]
```

# Claim resolution

```mermaid
flowchart TD
    T[Verified claims] --> P[Profile + overrides]
    P --> R{Resolve roles/tenant/username path}
    R -- literal key --> L["claims[path] (URL / urn: / cognito:)"]
    R -- contains * --> W[glob top-level keys, merge]
    R -- dotted --> N[walk nested a.b.c]
    L --> X[transform: array / csv / space / map_keys]
    W --> X
    N --> X
    X --> O[username, tenant, roles]
```

# Tenant → schema

```mermaid
flowchart LR
    TC["tenant claim = 'acme'"] --> SL["slugify → 'acme'"]
    SL --> SC["schema = prefix + '_' + slug = 'tenant_acme'"]
    NC["no tenant claim"] --> DT{DEFAULT_TENANT set?}
    DT -- yes --> SL
    DT -- no --> ERR[401 missing tenant]
```
