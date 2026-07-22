"""``hs-oidc doctor`` — link an OIDC provider without being a rocket scientist.

Point it at an issuer (and optionally a sample token) and it tells you, in plain
green/red, exactly what resolved and what to put in your environment:

    hs-oidc doctor https://id.example.com/realms/acme --profile keycloak
    hs-oidc doctor https://id.example.com/realms/acme --profile keycloak --token "$JWT"

Steps it runs:
  1. Fetch ``{issuer}/.well-known/openid-configuration`` → jwks_uri + endpoints.
  2. With ``--token``: decode it (verifying against the discovered JWKS when it can)
     and show which claim path yielded username / tenant / roles under the profile.
  3. Print a copy-paste ``HINDSIGHT_API_OIDC_*`` block.

No dependency on a running Hindsight; usable standalone by an admin.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request

import jwt as pyjwt

from .claims import PROFILES, build_claim_map

OK = "\033[32m✓\033[0m"
NO = "\033[31m✗\033[0m"
DIM = "\033[2m"
END = "\033[0m"


def _get(url: str, timeout: int = 5):
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read())


def _claim_map(profile: str, overrides: dict[str, str]):
    env = {"HINDSIGHT_API_OIDC_PROFILE": profile}
    env.update({k: v for k, v in overrides.items() if v})
    return build_claim_map(env)


def doctor(args) -> int:
    issuer = args.issuer
    print(f"\nOIDC doctor — issuer {issuer}\n" + "-" * 60)

    # 1) Discovery (well-known tolerates a trailing slash; the issuer INSIDE the
    # document is authoritative for `iss` validation — Authentik keeps the slash).
    well_known = f"{issuer.rstrip('/')}/.well-known/openid-configuration"
    try:
        disc = _get(well_known)
    except Exception as e:
        print(f"{NO} discovery: could not fetch {well_known}\n    {e}")
        return 1
    issuer = disc.get("issuer") or issuer
    jwks_uri = disc.get("jwks_uri")
    print(f"{OK} discovery: {well_known}")
    print(f"  {'jwks_uri':<22} {jwks_uri or '(missing!)'}")
    for k in ("authorization_endpoint", "token_endpoint", "end_session_endpoint"):
        v = disc.get(k)
        print(f"  {(OK if v else NO)} {k:<20} {v or DIM + '(not advertised)' + END}")
    if not jwks_uri:
        print(f"\n{NO} no jwks_uri — cannot verify tokens from this issuer.")
        return 1

    # 2) Claim mapping (+ optional token)
    overrides = {
        "HINDSIGHT_API_OIDC_ROLES_CLAIM": args.roles_claim,
        "HINDSIGHT_API_OIDC_TENANT_CLAIM": args.tenant_claim,
        "HINDSIGHT_API_OIDC_USERNAME_CLAIM": args.username_claim,
        "HINDSIGHT_API_OIDC_ROLES_TRANSFORM": args.roles_transform,
        "HINDSIGHT_API_OIDC_CLIENT_ID": args.client_id,
    }
    cm = _claim_map(args.profile, overrides)
    print(f"\nprofile: {cm.profile}")
    print(f"  roles    ← {cm.roles_claim}   ({cm.roles_transform})")
    print(f"  tenant   ← {cm.tenant_claim}")
    print(f"  username ← {cm.username_claim}")
    if "YOUR-NAMESPACE" in cm.roles_claim:
        print(f"  {NO} this profile needs --roles-claim (e.g. https://yourapp/roles)")

    if args.token:
        try:
            claims = pyjwt.decode(args.token, options={"verify_signature": False})
        except Exception as e:
            print(f"\n{NO} token: could not decode — {e}")
            return 1
        print("\ntoken claims resolved:")
        u, t, r = cm.username(claims), cm.tenant(claims), cm.roles(claims)
        print(f"  {(OK if u else NO)} username = {u!r}")
        print(f"  {(OK if t else NO)} tenant   = {t!r}")
        print(f"  {(OK if r else NO)} roles    = {sorted(r) or '[]'}")
        aud = claims.get("aud")
        print(f"  {DIM}aud = {aud!r}, iss = {claims.get('iss')!r}{END}")
        # Try a real verification if we can reach the JWKS.
        try:
            from jwt import PyJWKClient

            key = PyJWKClient(jwks_uri).get_signing_key_from_jwt(args.token).key
            pyjwt.decode(
                args.token,
                key,
                algorithms=["RS256"],
                issuer=issuer,
                audience=args.audience,
                options={"verify_aud": bool(args.audience)},
            )
            print(f"  {OK} signature/iss{'/aud' if args.audience else ''} verified against JWKS")
        except Exception as e:
            print(f"  {DIM}(signature check skipped/failed: {e}){END}")

    # 3) Env block
    print("\ncopy-paste config:\n" + "-" * 60)
    print(f"HINDSIGHT_API_OIDC_ISSUER={issuer}")
    if args.audience:
        print(f"HINDSIGHT_API_OIDC_AUDIENCE={args.audience}")
    print(f"HINDSIGHT_API_OIDC_PROFILE={cm.profile}")
    for env_key, val, default in (
        ("HINDSIGHT_API_OIDC_ROLES_CLAIM", cm.roles_claim, PROFILES[cm.profile].roles_claim),
        ("HINDSIGHT_API_OIDC_TENANT_CLAIM", cm.tenant_claim, PROFILES[cm.profile].tenant_claim),
        ("HINDSIGHT_API_OIDC_USERNAME_CLAIM", cm.username_claim, PROFILES[cm.profile].username_claim),
    ):
        if val != default:  # only emit overrides that differ from the profile
            print(f"{env_key}={val}")
    print(f"{DIM}# jwks_uri auto-discovered; set HINDSIGHT_API_OIDC_JWKS_URL only if the")
    print(f"# issuer host is unreachable from inside the container.{END}\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="hs-oidc", description="Hindsight OIDC helper")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("doctor", help="probe an OIDC issuer and resolve claim mapping")
    d.add_argument("issuer", help="OIDC issuer URL (e.g. https://id.example.com/realms/acme)")
    d.add_argument("--profile", default="generic", choices=sorted(PROFILES), help="vendor profile")
    d.add_argument("--audience", help="expected aud")
    d.add_argument("--token", help="a sample access token to resolve claims against")
    d.add_argument("--roles-claim", dest="roles_claim")
    d.add_argument("--tenant-claim", dest="tenant_claim")
    d.add_argument("--username-claim", dest="username_claim")
    d.add_argument("--roles-transform", dest="roles_transform")
    d.add_argument("--client-id", dest="client_id", help="for <client> in resource_access.<client>.roles")

    li = sub.add_parser("login", help="browser (PKCE) sign-in; caches tokens for a server")
    li.add_argument("server_url", help="the Hindsight server URL (e.g. http://localhost:8899)")
    li.add_argument("--client-id", dest="client_id", required=True, help="a public OAuth client id")
    li.add_argument("--issuer", help="authorization server (skips discovery)")
    li.add_argument("--port", type=int, default=8765, help="loopback callback port (default 8765)")
    li.add_argument("--no-browser", action="store_true", help="print the URL instead of opening a browser")

    tk = sub.add_parser("token", help="print a fresh access token (refresh, or machine-to-machine)")
    tk.add_argument("server_url", help="the Hindsight server URL")
    tk.add_argument("--client-id", dest="client_id", help="client id (with --client-secret = machine-to-machine)")
    tk.add_argument("--client-secret", dest="client_secret", help="client secret → client-credentials grant")
    tk.add_argument("--issuer", help="authorization server (skips discovery)")

    lo = sub.add_parser("logout", help="clear cached tokens for a server")
    lo.add_argument("server_url")

    args = p.parse_args(argv)
    if args.cmd == "doctor":
        return doctor(args)
    if args.cmd == "login":
        from . import login as _login

        _login.login(args.server_url, args.client_id, args.port, args.issuer, no_browser=args.no_browser)
        return 0
    if args.cmd == "token":
        from . import login as _login

        print(_login.token(args.server_url, args.client_id, args.client_secret, args.issuer))
        return 0
    if args.cmd == "logout":
        from . import login as _login

        _login.logout(args.server_url)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
