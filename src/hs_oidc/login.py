"""Client-side token helper: one command to log in (browser) or mint an M2M token,
cache it, and keep it fresh — so non-MCP clients (SDKs, scripts, agents) never
paste or manage tokens by hand.

Discovery is automatic: point it at the Hindsight server and it finds the
authorization server from the same RFC 9728 metadata an MCP host uses.

    hs-oidc login  http://localhost:8899 --client-id hs-oidc-cli   # browser (PKCE)
    hs-oidc token  http://localhost:8899                           # print fresh access token
    hs-oidc token  http://localhost:8899 --client-id agent --client-secret … # machine-to-machine
    hs-oidc logout http://localhost:8899

Use it as a credential source:  export/attach  api_key=$(hs-oidc token <url>).
Tokens (access + refresh) are cached under ~/.hs-oidc/ and refreshed on demand.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import http.server
import json
import os
import pathlib
import secrets
import threading
import time
import urllib.parse
import urllib.request
import webbrowser

DEFAULT_SCOPES = "openid profile email offline_access"
_LEEWAY = 30  # refresh this many seconds before the access token actually expires


# --------------------------------------------------------------------------- #
# token cache (~/.hs-oidc/tokens.json)
# --------------------------------------------------------------------------- #
def _cache_file() -> pathlib.Path:
    d = pathlib.Path(os.environ.get("HS_OIDC_HOME", pathlib.Path.home() / ".hs-oidc"))
    d.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        d.chmod(0o700)
    return d / "tokens.json"


def _load_cache() -> dict:
    f = _cache_file()
    if f.exists():
        try:
            return json.loads(f.read_text())
        except (OSError, ValueError):
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    f = _cache_file()
    f.write_text(json.dumps(cache, indent=2))
    with contextlib.suppress(OSError):
        f.chmod(0o600)


def _key(server_url: str) -> str:
    return server_url.rstrip("/")


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #
def _get_json(url: str, timeout: int = 10) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as r:  # noqa: S310
        return json.loads(r.read())


def _post_form(url: str, data: dict, timeout: int = 15) -> dict:
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
        return json.loads(r.read())


# --------------------------------------------------------------------------- #
# discovery — server URL → authorization server endpoints
# --------------------------------------------------------------------------- #
def discover(server_url: str, issuer: str | None = None) -> dict:
    """Resolve the OAuth endpoints for a Hindsight server.

    Finds the authorization server from the server's protected-resource-metadata
    (RFC 9728), then the AS's endpoints (RFC 8414 / OIDC discovery).
    """
    server_url = server_url.rstrip("/")
    resource = f"{server_url}/mcp"
    if not issuer:
        # Try the canonical MCP metadata path, then the root.
        for path in ("/mcp/.well-known/oauth-protected-resource", "/.well-known/oauth-protected-resource"):
            try:
                doc = _get_json(server_url + path)
                servers = doc.get("authorization_servers") or []
                if servers:
                    issuer = servers[0]
                    resource = doc.get("resource") or resource
                    break
            except Exception:
                continue
    if not issuer:
        raise SystemExit(
            f"Could not discover the authorization server from {server_url}.\n"
            "Pass it explicitly with --issuer https://<keycloak>/realms/<realm>."
        )
    meta = _get_json(issuer.rstrip("/") + "/.well-known/openid-configuration")
    return {
        "issuer": meta["issuer"],
        "resource": resource,
        "authorization_endpoint": meta["authorization_endpoint"],
        "token_endpoint": meta["token_endpoint"],
    }


# --------------------------------------------------------------------------- #
# PKCE browser (authorization-code) flow
# --------------------------------------------------------------------------- #
def _pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    result: dict = {}
    event: threading.Event

    def do_GET(self) -> None:  # noqa: N802
        q = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(q)
        type(self).result = {k: v[0] for k, v in params.items()}
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        ok = "code" in params
        self.wfile.write(
            (f"<h3>{'✓ Signed in — you can close this tab.' if ok else '✗ Sign-in failed.'}</h3>").encode()
        )
        type(self).event.set()

    def log_message(self, *a: object) -> None:
        pass


def login(
    server_url: str,
    client_id: str,
    port: int = 8765,
    issuer: str | None = None,
    scopes: str = DEFAULT_SCOPES,
    no_browser: bool = False,
    timeout: int = 300,
) -> None:
    """Browser (PKCE authorization-code) login; caches access + refresh tokens."""
    cfg = discover(server_url, issuer)
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(24)
    redirect_uri = f"http://localhost:{port}/callback"
    auth_url = (
        cfg["authorization_endpoint"]
        + "?"
        + urllib.parse.urlencode(
            {
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "scope": scopes,
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "resource": cfg["resource"],
            }
        )
    )

    _CallbackHandler.event = threading.Event()
    _CallbackHandler.result = {}
    server = http.server.HTTPServer(("127.0.0.1", port), _CallbackHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    print(f"Signing in to {cfg['issuer']} …")
    if no_browser or not webbrowser.open(auth_url):
        print(f"\nOpen this URL to authorize:\n  {auth_url}\n")
    if not _CallbackHandler.event.wait(timeout):
        server.shutdown()
        raise SystemExit("Timed out waiting for the browser sign-in.")
    server.shutdown()

    res = _CallbackHandler.result
    if res.get("state") != state:
        raise SystemExit("State mismatch — aborting.")
    if "code" not in res:
        raise SystemExit(f"Sign-in failed: {res.get('error_description', res.get('error', 'no code'))}")

    tok = _post_form(
        cfg["token_endpoint"],
        {
            "grant_type": "authorization_code",
            "code": res["code"],
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "code_verifier": verifier,
            "resource": cfg["resource"],
        },
    )
    _store(server_url, cfg, client_id, tok)
    print(f"✓ Signed in. Token cached; use `hs-oidc token {server_url}`.")


# --------------------------------------------------------------------------- #
# token: print a fresh access token (refresh, or machine-to-machine)
# --------------------------------------------------------------------------- #
def _store(server_url: str, cfg: dict, client_id: str, tok: dict) -> dict:
    cache = _load_cache()
    entry = {
        "issuer": cfg["issuer"],
        "resource": cfg["resource"],
        "token_endpoint": cfg["token_endpoint"],
        "client_id": client_id,
        "access_token": tok["access_token"],
        "refresh_token": tok.get("refresh_token"),
        "expires_at": time.time() + float(tok.get("expires_in", 60)),
    }
    cache[_key(server_url)] = entry
    _save_cache(cache)
    return entry


def token(
    server_url: str,
    client_id: str | None = None,
    client_secret: str | None = None,
    issuer: str | None = None,
    scopes: str = DEFAULT_SCOPES,
) -> str:
    """Return a valid access token: refresh a cached one, or mint via client-credentials."""
    # Machine-to-machine: client-credentials, no cache needed.
    if client_secret:
        cfg = discover(server_url, issuer)
        tok = _post_form(
            cfg["token_endpoint"],
            {
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": scopes,
                "resource": cfg["resource"],
            },
        )
        return tok["access_token"]

    # Interactive: use the cached tokens, refreshing if near expiry.
    entry = _load_cache().get(_key(server_url))
    if not entry:
        raise SystemExit(f"Not logged in to {server_url}. Run: hs-oidc login {server_url} --client-id <id>")
    if time.time() < entry["expires_at"] - _LEEWAY:
        return entry["access_token"]
    if not entry.get("refresh_token"):
        raise SystemExit("Access token expired and no refresh token. Run `hs-oidc login` again.")
    tok = _post_form(
        entry["token_endpoint"],
        {
            "grant_type": "refresh_token",
            "refresh_token": entry["refresh_token"],
            "client_id": entry["client_id"],
            "resource": entry["resource"],
        },
    )
    entry["access_token"] = tok["access_token"]
    entry["expires_at"] = time.time() + float(tok.get("expires_in", 60))
    if tok.get("refresh_token"):
        entry["refresh_token"] = tok["refresh_token"]
    cache = _load_cache()
    cache[_key(server_url)] = entry
    _save_cache(cache)
    return entry["access_token"]


def logout(server_url: str) -> None:
    cache = _load_cache()
    if cache.pop(_key(server_url), None) is not None:
        _save_cache(cache)
        print(f"✓ Cleared cached tokens for {server_url}.")
    else:
        print(f"No cached tokens for {server_url}.")
