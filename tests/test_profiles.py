"""Profile matrix — prove the claim resolver extracts roles/tenant/username from
tokens shaped like each real vendor, without any live provider.

Each case is a synthetic claims dict in that vendor's actual token layout, plus the
env config an admin would set. We assert the resolved (username, tenant, roles).
This is what lets Auth0/Cognito/Okta/Entra ship as verified profiles with no cloud
account.
"""

from __future__ import annotations

import pytest

from hs_oidc.claims import build_claim_map, resolve_path, to_roles

# (profile, env_overrides, claims, expected_username, expected_tenant, expected_roles)
CASES = [
    (
        "keycloak",
        {},
        {
            "preferred_username": "alice",
            "tenant": "acme",
            "realm_access": {"roles": ["admin", "editor"]},
        },
        "alice",
        "acme",
        {"admin", "editor"},
    ),
    (
        # Keycloak *client* roles (override roles_claim with the <client> placeholder)
        "keycloak",
        {
            "HINDSIGHT_API_OIDC_ROLES_CLAIM": "resource_access.<client>.roles",
            "HINDSIGHT_API_OIDC_CLIENT_ID": "hindsight",
        },
        {
            "preferred_username": "bob",
            "tenant": "acme",
            "resource_access": {"hindsight": {"roles": ["viewer"]}},
        },
        "bob",
        "acme",
        {"viewer"},
    ),
    (
        # Auth0: roles under a namespaced URL claim (admin supplies the namespace)
        "auth0",
        {
            "HINDSIGHT_API_OIDC_ROLES_CLAIM": "https://acme.example.com/roles",
            "HINDSIGHT_API_OIDC_TENANT_CLAIM": "https://acme.example.com/tenant",
        },
        {
            "preferred_username": "alice",
            "https://acme.example.com/roles": ["admin"],
            "https://acme.example.com/tenant": "acme",
        },
        "alice",
        "acme",
        {"admin"},
    ),
    (
        # Cognito: cognito:groups, cognito:username, custom:tenant
        "cognito",
        {},
        {
            "cognito:username": "bob",
            "custom:tenant": "acme",
            "cognito:groups": ["viewer", "editor"],
        },
        "bob",
        "acme",
        {"viewer", "editor"},
    ),
    (
        "okta",
        {"HINDSIGHT_API_OIDC_TENANT_CLAIM": "tenant"},
        {"preferred_username": "carol", "tenant": "acme", "groups": ["admin"]},
        "carol",
        "acme",
        {"admin"},
    ),
    (
        "entra",
        {"HINDSIGHT_API_OIDC_TENANT_CLAIM": "tenant"},
        {"preferred_username": "dave", "tenant": "acme", "roles": ["editor"]},
        "dave",
        "acme",
        {"editor"},
    ),
    (
        # Zitadel: roles live under a PROJECT-ID-keyed claim; the profile's "*"
        # wildcard matches it and map_keys turns the nested map into role names.
        "zitadel",
        {"HINDSIGHT_API_OIDC_TENANT_CLAIM": "tenant"},
        {
            "preferred_username": "erin",
            "tenant": "acme",
            "urn:zitadel:iam:org:project:382496254594124547:roles": {
                "admin": {"orgid1": "acme"},
                "editor": {"orgid1": "acme"},
            },
        },
        "erin",
        "acme",
        {"admin", "editor"},
    ),
    (
        # Zitadel with roles granted across TWO projects — wildcard merges both.
        "zitadel",
        {"HINDSIGHT_API_OIDC_TENANT_CLAIM": "tenant"},
        {
            "preferred_username": "grace",
            "tenant": "acme",
            "urn:zitadel:iam:org:project:111:roles": {"admin": {"o": "acme"}},
            "urn:zitadel:iam:org:project:222:roles": {"viewer": {"o": "acme"}},
        },
        "grace",
        "acme",
        {"admin", "viewer"},
    ),
    (
        "authentik",
        {"HINDSIGHT_API_OIDC_TENANT_CLAIM": "tenant"},
        {"preferred_username": "frank", "tenant": "acme", "groups": ["viewer"]},
        "frank",
        "acme",
        {"viewer"},
    ),
    (
        # Dex: identity only — username from email, no roles, no tenant claim.
        "dex",
        {},
        {"email": "alice@example.com", "name": "alice", "sub": "CgVhbGljZQ"},
        "alice@example.com",
        None,
        set(),
    ),
]


@pytest.mark.parametrize("profile,env,claims,exp_user,exp_tenant,exp_roles", CASES)
def test_profile_resolves(profile, env, claims, exp_user, exp_tenant, exp_roles):
    env = {"HINDSIGHT_API_OIDC_PROFILE": profile, **env}
    cm = build_claim_map(env)
    assert cm.username(claims) == exp_user
    assert cm.tenant(claims) == exp_tenant
    assert cm.roles(claims) == exp_roles


def test_unknown_profile_rejected():
    with pytest.raises(ValueError, match="Unknown OIDC profile"):
        build_claim_map({"HINDSIGHT_API_OIDC_PROFILE": "nope"})


def test_legacy_tenant_claim_env_fallback():
    cm = build_claim_map({"HINDSIGHT_API_OIDC_PROFILE": "generic", "HINDSIGHT_API_TENANT_TENANT_CLAIM": "dept"})
    assert cm.tenant_claim == "dept"


def test_resolve_literal_url_key_beats_dotted_walk():
    # A URL claim name is a single literal key, not a nested path.
    claims = {"https://a.example/roles": ["x"]}
    assert resolve_path(claims, "https://a.example/roles") == ["x"]


def test_resolve_missing_path_returns_none():
    assert resolve_path({"a": {"b": 1}}, "a.c") is None
    assert resolve_path({}, "nope") is None


@pytest.mark.parametrize(
    "value,transform,expected",
    [
        (["a", "b"], "array", {"a", "b"}),
        ("a b c", "space_delimited", {"a", "b", "c"}),
        ("a, b ,c", "csv", {"a", "b", "c"}),
        ({"admin": {}, "editor": {}}, "map_keys", {"admin", "editor"}),
        (None, "array", set()),
        ("solo", "array", {"solo"}),
    ],
)
def test_to_roles_transforms(value, transform, expected):
    assert to_roles(value, transform) == expected
