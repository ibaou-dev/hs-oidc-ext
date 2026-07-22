"""OIDCDiscoveryExtension — serves RFC 9728 Protected Resource Metadata.

Enables MCP OAuth *discovery*: an MCP host (Claude Code, …) that hits a protected
``/mcp`` gets a 401 whose ``WWW-Authenticate`` points here (see :mod:`._metadata`);
this endpoint then tells it which authorization server to log in against. That is
the whole "click authorize in a browser, no pasted token" experience.

Hindsight mounts HTTP extensions under ``/ext/``, so the document is served at
``/ext/oauth-protected-resource`` and the ``resource_metadata`` pointer in the 401
resolves to it. The endpoint is intentionally **unauthenticated** — a client must
read it *before* it has a token.

Enable via environment (alongside the tenant extension):

    HINDSIGHT_API_HTTP_EXTENSION=hs_oidc.http:OIDCDiscoveryExtension
    HINDSIGHT_API_OIDC_PUBLIC_URL=http://localhost:8893     # required for discovery
    HINDSIGHT_API_OIDC_RESOURCE=http://localhost:8893/mcp   # optional (defaults to {PUBLIC_URL}/mcp)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter
from hindsight_api.extensions.http import HttpExtension

from ._metadata import build_resource_metadata

if TYPE_CHECKING:
    from hindsight_api.engine.memory_engine import MemoryEngine

__all__ = ["OIDCDiscoveryExtension"]


class OIDCDiscoveryExtension(HttpExtension):
    """Publishes the protected-resource-metadata document for MCP OAuth discovery."""

    def get_router(self, memory: MemoryEngine) -> APIRouter:
        router = APIRouter(tags=["OIDC Discovery"])

        @router.get("/oauth-protected-resource")
        async def protected_resource_metadata() -> dict:
            # RFC 9728 — names the authorization server(s) for this resource.
            return build_resource_metadata()

        return router
