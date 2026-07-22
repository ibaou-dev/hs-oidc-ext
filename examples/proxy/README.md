# SSO for the control-plane web UI (optional)

Puts OIDC login + an identity header in front of the stock Hindsight control-plane
UI, **without forking it**. Authentication/identity only — no per-user
authorization (see [ADR-008](../../docs/design-decisions.md) and
[proxy-trick.md](../../docs/proxy-trick.md)).

## Run

Assumes the example stack is up (`examples/compose.yaml`), so the control-plane is
at `http://localhost:9998`.

```bash
# 1. Start the SSO shell (host process) — wraps the real UI with an identity header
UPSTREAM=http://127.0.0.1:9998 python3 examples/proxy/sso_shell_proxy.py 5155 &

# 2. Start oauth2-proxy (login gate) in front of the shell
docker compose -f examples/proxy/compose.yaml up -d

# 3. Browse
open http://localhost:4280      # → Keycloak login → control-plane, with a header
```

Log in as `alice` / `alice`. The header shows the signed-in user + tenant; **Sign
out** performs RP-initiated logout at Keycloak.

## How it works

```
browser → oauth2-proxy (:4280, OIDC login) → sso_shell_proxy (:5155) → control-plane (:9998)
```

`oauth2-proxy` forwards the access token as `X-Forwarded-Access-Token`; the shell
decodes it only to render the header and serves a wrapper page (header + `<iframe>`
of the real UI) for top-level navigations — React 19 strips injected nodes, so we
own the page instead. The `hindsight` realm client already allows the
`http://localhost:4280/oauth2/callback` redirect and RP-initiated logout.

## Tear down

```bash
docker compose -f examples/proxy/compose.yaml down
pkill -f sso_shell_proxy.py
```
