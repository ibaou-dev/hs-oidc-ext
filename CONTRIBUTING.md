# Contributing

Thanks for helping improve `hs-oidc-ext`.

## Development setup

```bash
python -m venv .venv && . .venv/bin/activate     # or: uv venv
pip install -e ".[dev]"                          # or: uv pip install -e ".[dev]"
pre-commit install
```

## The quality gate

Everything CI runs, locally:

```bash
ruff check .            # lint
ruff format --check .   # formatting
mypy                    # type-check src/
pytest                  # 58 offline, deterministic tests
```

`pre-commit run --all-files` runs the same checks plus whitespace/EOF/YAML hooks
and the private-identifier guard.

## Adding a provider profile

A profile is pure config in [`src/hs_oidc/claims.py`](src/hs_oidc/claims.py) — the
claim paths (`roles`, `tenant`, `username`) and a roles transform. To add one:

1. Add an entry to `PROFILES` with the vendor's claim locations.
2. Add a synthetic-token case to `tests/test_profiles.py` (a claims dict shaped like
   that vendor + the expected `(username, tenant, roles)`).
3. If possible, verify live with `hs-oidc doctor <issuer> --profile <name> --token …`
   and note any findings in `docs/providers/`.

No changes to the verifier or extensions should be needed — that's the point.

## Keeping the repo publish-safe

This repo uses only generic placeholders (`acme`, `alice`, `bob`). If you fork it
for internal use, copy `.forbidden-identifiers.txt.example` to
`.forbidden-identifiers.txt` (gitignored) and list your real names — the
`no-private-identifiers` pre-commit hook then blocks commits that reintroduce them.

## Documentation

Durable docs live in [`docs/`](docs/) as an Open Knowledge Format bundle. Use the
bundled `okf-docs` skill (`.claude/skills/okf-docs`) and validate with
`python .claude/skills/okf-docs/scripts/okf_validate.py docs`.

## Scope

This extension is **authentication + tenancy** only. Authorization (RBAC) is a
separate, forthcoming extension — please keep per-user/per-bank policy out of here
(see ADR-008 in [docs/design-decisions.md](docs/design-decisions.md)).
