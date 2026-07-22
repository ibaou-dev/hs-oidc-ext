"""RFC 9728 Protected Resource Metadata + WWW-Authenticate for MCP OAuth discovery.

Pure helpers (no web-framework imports) so both the verifier (:mod:`._oidc`) and the
HTTP extension (:mod:`.http`) can use them. When ``HINDSIGHT_API_OIDC_PUBLIC_URL`` is
set, an MCP host (e.g. Claude Code) can discover how to log in: the 401 it gets
carries a ``resource_metadata`` pointer, which resolves to the metadata document
naming the authorization server (see :func:`build_resource_metadata`).

Config:

    HINDSIGHT_API_OIDC_PUBLIC_URL  the server's browser-reachable base URL, e.g.
                                   http://localhost:8893 — enables MCP discovery.
    HINDSIGHT_API_OIDC_RESOURCE    canonical resource identifier (the MCP URL);
                                   defaults to ``{PUBLIC_URL}/mcp``.
    HINDSIGHT_API_OIDC_SCOPES      space-separated scopes to advertise (default
                                   "openid profile email").

Discovery is opt-in: without ``PUBLIC_URL`` the WWW-Authenticate header is
unchanged and no pointer is advertised.
"""

from __future__ import annotations

import os

_METADATA_PATH = "/ext/oauth-protected-resource"


def _env(*names: str) -> str | None:
    for n in names:
        v = os.getenv(n)
        if v:
            return v
    return None


def public_url() -> str | None:
    """The server's browser-reachable base URL (enables discovery when set)."""
    v = _env("HINDSIGHT_API_OIDC_PUBLIC_URL")
    return v.rstrip("/") if v else None


def issuer() -> str:
    return (_env("HINDSIGHT_API_OIDC_ISSUER", "HINDSIGHT_API_TENANT_ISSUER") or "").rstrip("/")


def resource_id() -> str | None:
    """Canonical resource identifier — the MCP URL the client targets (RFC 8707)."""
    v = _env("HINDSIGHT_API_OIDC_RESOURCE")
    if v:
        return v.rstrip("/")
    pub = public_url()
    return f"{pub}/mcp" if pub else None


def resource_metadata_url() -> str | None:
    """Absolute URL of the protected-resource-metadata document, or None if off."""
    pub = public_url()
    return f"{pub}{_METADATA_PATH}" if pub else None


def build_resource_metadata() -> dict:
    """The RFC 9728 Protected Resource Metadata document."""
    scopes = (_env("HINDSIGHT_API_OIDC_SCOPES") or "openid profile email").split()
    return {
        "resource": resource_id(),
        "authorization_servers": [issuer()],
        "bearer_methods_supported": ["header"],
        "scopes_supported": scopes,
    }


def www_authenticate(error: str | None = None) -> str:
    """Build the WWW-Authenticate value for a 401.

    Always advertises ``Bearer realm="hindsight"``; adds ``error=...`` for an
    invalid/expired token, and ``resource_metadata="..."`` (RFC 9728 §5.1) when
    discovery is enabled — that pointer is what lets an MCP host auto-discover the
    login. Unchanged from the classic header when ``PUBLIC_URL`` is unset.
    """
    parts = ['Bearer realm="hindsight"']
    if error:
        parts.append(f'error="{error}"')
    url = resource_metadata_url()
    if url:
        parts.append(f'resource_metadata="{url}"')
    return ", ".join(parts)
