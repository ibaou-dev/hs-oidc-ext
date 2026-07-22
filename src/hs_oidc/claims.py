"""Vendor-agnostic OIDC claim mapping.

The only thing that genuinely differs between OIDC providers is *where the claims
live* — roles under ``realm_access.roles`` (Keycloak), ``cognito:groups``
(Cognito), a namespaced URL (Auth0), a nested map (Zitadel), etc. This module
turns that variation into pure declarative config so an admin picks a **profile**
(a preset of claim paths) and, at most, overrides one path — no code changes.

A *path* is either:
  * a literal top-level claim key — used verbatim when it exists as a key
    (this is how URL/``urn:``/``cognito:`` claim names resolve), or
  * a dotted nested path walked segment by segment (``realm_access.roles``).
The token ``<client>`` inside a path is replaced with the configured client id
(for Keycloak client roles: ``resource_access.<client>.roles``).

Roles may arrive as an array, a space/comma-delimited string, or a map whose
*keys* are the role names (Zitadel) — see :data:`TRANSFORMS`.
"""

from __future__ import annotations

import fnmatch
import os
from collections.abc import Mapping
from dataclasses import dataclass, replace

# --- Vendor profiles: presets for where each claim lives -------------------
# Each profile maps the three logical claims (roles, tenant, username) to a path,
# plus how to read the roles value. Admins select one via HINDSIGHT_API_OIDC_PROFILE
# and may override any single field. "generic" is the spec-only baseline.


@dataclass(frozen=True)
class Profile:
    roles_claim: str = "roles"
    tenant_claim: str = "tenant"
    username_claim: str = "preferred_username"
    roles_transform: str = "array"


PROFILES: dict[str, Profile] = {
    # Spec baseline — a flat "roles" array and a custom "tenant" claim.
    "generic": Profile(),
    # Keycloak realm roles (the default). For client roles, override roles_claim
    # to "resource_access.<client>.roles".
    "keycloak": Profile(roles_claim="realm_access.roles"),
    # Auth0 forbids bare custom claims — roles must be a namespaced URL claim the
    # admin adds via an Action. The profile can't know the namespace, so the path
    # is a placeholder the admin MUST override (doctor flags this).
    "auth0": Profile(roles_claim="https://YOUR-NAMESPACE/roles"),
    "cognito": Profile(
        roles_claim="cognito:groups",
        tenant_claim="custom:tenant",
        username_claim="cognito:username",
    ),
    "okta": Profile(roles_claim="groups"),
    # Microsoft Entra ID (Azure AD) app roles.
    "entra": Profile(roles_claim="roles"),
    # Zitadel emits roles under a PROJECT-ID-keyed claim,
    # urn:zitadel:iam:org:project:<projectid>:roles, whose value is a map
    # {role: {orgid: orgname}}. The "*" wildcard matches any project's claim (and
    # merges across projects); map_keys turns the map into role names.
    "zitadel": Profile(
        roles_claim="urn:zitadel:iam:org:project:*:roles",
        roles_transform="map_keys",
    ),
    "authentik": Profile(roles_claim="groups"),
    # Dex is a login/federation IdP: tokens carry identity only (no roles/tenant).
    # username comes from `email` (always present). Use it for pure OIDC login /
    # as a deterministic verifier; pair with a real RBAC source for authz.
    "dex": Profile(username_claim="email"),
}

# How to coerce a raw roles claim value into a set of role names.
TRANSFORMS = ("array", "space_delimited", "csv", "map_keys")


def resolve_path(claims: dict, path: str, client_id: str | None = None):
    """Return the value at ``path`` in ``claims``, or ``None``.

    Resolution order:
      1. literal top-level key (URL/``urn:``/``cognito:`` claim names work verbatim);
      2. ``*`` glob over top-level keys → a *list* of the matching values (used for
         Zitadel's per-project ``...:project:<id>:roles`` claims — merges projects);
      3. dotted nested walk (``realm_access.roles``).
    ``<client>`` is substituted first.
    """
    if not path:
        return None
    if client_id:
        path = path.replace("<client>", client_id)
    if path in claims:  # literal key: "cognito:groups", "https://app/roles", "urn:..."
        return claims[path]
    if "*" in path:  # glob across literal top-level keys
        matches = [claims[k] for k in claims if fnmatch.fnmatch(k, path)]
        return matches or None
    cur = claims
    for seg in path.split("."):
        if isinstance(cur, dict) and seg in cur:
            cur = cur[seg]
        else:
            return None
    return cur


def to_roles(value, transform: str = "array") -> set[str]:
    """Coerce a raw roles claim value into a set of role-name strings.

    Handles scalars, strings (array/space/csv), maps (map_keys → keys), and *lists*
    of any of those — the list case merges (e.g. a wildcard match across several
    Zitadel per-project role maps).
    """
    if value is None:
        return set()
    if isinstance(value, (list, tuple, set)):
        out: set[str] = set()
        for item in value:
            out |= to_roles(item, transform)
        return out
    if transform == "map_keys" and isinstance(value, dict):
        return {str(k) for k in value}
    if isinstance(value, str):
        if transform == "space_delimited":
            return {s for s in value.split() if s}
        if transform == "csv":
            return {s.strip() for s in value.split(",") if s.strip()}
        return {value} if value else set()
    if isinstance(value, dict):  # sensible default: treat keys as roles
        return {str(k) for k in value}
    return set()


@dataclass(frozen=True)
class ClaimMap:
    """Resolved, provider-agnostic claim configuration."""

    profile: str
    roles_claim: str
    tenant_claim: str
    username_claim: str
    roles_transform: str
    client_id: str | None = None

    def roles(self, claims: dict) -> set[str]:
        return to_roles(resolve_path(claims, self.roles_claim, self.client_id), self.roles_transform)

    def tenant(self, claims: dict):
        return resolve_path(claims, self.tenant_claim, self.client_id)

    def username(self, claims: dict) -> str | None:
        val = resolve_path(claims, self.username_claim, self.client_id)
        return str(val) if val is not None else None


def build_claim_map(env: Mapping[str, str] | None = None) -> ClaimMap:
    """Build the claim map from a profile + per-field overrides.

    Reads ``HINDSIGHT_API_OIDC_PROFILE`` then applies any of
    ``HINDSIGHT_API_OIDC_{ROLES,TENANT,USERNAME}_CLAIM`` /
    ``HINDSIGHT_API_OIDC_ROLES_TRANSFORM`` / ``HINDSIGHT_API_OIDC_CLIENT_ID``
    overrides. Legacy ``HINDSIGHT_API_TENANT_TENANT_CLAIM`` is honored as a
    fallback for the tenant claim so existing deployments keep working.
    """
    env = os.environ if env is None else env
    name = (env.get("HINDSIGHT_API_OIDC_PROFILE") or "generic").strip().lower()
    base = PROFILES.get(name)
    if base is None:
        raise ValueError(f"Unknown OIDC profile '{name}'. Choose one of: {', '.join(sorted(PROFILES))}.")

    overrides = {}
    if v := env.get("HINDSIGHT_API_OIDC_ROLES_CLAIM"):
        overrides["roles_claim"] = v
    if v := (
        env.get("HINDSIGHT_API_OIDC_TENANT_CLAIM") or env.get("HINDSIGHT_API_TENANT_TENANT_CLAIM")  # legacy fallback
    ):
        overrides["tenant_claim"] = v
    if v := env.get("HINDSIGHT_API_OIDC_USERNAME_CLAIM"):
        overrides["username_claim"] = v
    if v := env.get("HINDSIGHT_API_OIDC_ROLES_TRANSFORM"):
        if v not in TRANSFORMS:
            raise ValueError(f"Unknown roles transform '{v}'. Choose one of: {', '.join(TRANSFORMS)}.")
        overrides["roles_transform"] = v

    profile = replace(base, **overrides)
    return ClaimMap(
        profile=name,
        roles_claim=profile.roles_claim,
        tenant_claim=profile.tenant_claim,
        username_claim=profile.username_claim,
        roles_transform=profile.roles_transform,
        client_id=env.get("HINDSIGHT_API_OIDC_CLIENT_ID") or None,
    )
