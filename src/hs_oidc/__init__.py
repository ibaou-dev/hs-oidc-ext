"""Generic OIDC authentication + multi-tenancy for the Hindsight memory API.

Provider-agnostic — point it at any compliant OIDC issuer and pick a profile
(Keycloak, Auth0, Cognito, Okta, Entra ID, Zitadel, Authentik, Dex, or generic).

- :class:`hs_oidc.tenant.OIDCTenantExtension` authenticates the caller's OIDC token
  and isolates each tenant in its own Postgres schema.
- :mod:`hs_oidc.claims` is the profile / claim-mapping model.
- :mod:`hs_oidc._oidc` is discovery + verification; :func:`get_verifier` is the
  shared verifier a downstream RBAC extension can reuse.
"""

from ._metadata import build_resource_metadata, www_authenticate
from ._oidc import OidcVerifier, get_verifier
from .claims import PROFILES, ClaimMap, build_claim_map
from .http import OIDCDiscoveryExtension
from .tenant import OIDCTenantExtension

__all__ = [
    "PROFILES",
    "ClaimMap",
    "OIDCDiscoveryExtension",
    "OIDCTenantExtension",
    "OidcVerifier",
    "build_claim_map",
    "build_resource_metadata",
    "get_verifier",
    "www_authenticate",
]
