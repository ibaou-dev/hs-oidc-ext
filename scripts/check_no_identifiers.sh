#!/usr/bin/env bash
# Fail if staged files contain private/corporate identifiers.
#
# The published repo ships only generic placeholders (acme/alice/bob). This hook
# lets a downstream fork keep it that way: put your real names/domains (one regex
# per line) in a *gitignored* `.forbidden-identifiers.txt`, and this hook blocks
# any commit that reintroduces them. Without that file, it is a no-op — so the
# public repo never contains the sensitive list itself.
#
# Usage: scripts/check_no_identifiers.sh [files...]   (pre-commit passes staged files)
set -euo pipefail

DENY_FILE=".forbidden-identifiers.txt"
[[ -f "$DENY_FILE" ]] || exit 0   # no deny-list configured → nothing to check

files=("$@")
[[ ${#files[@]} -eq 0 ]] && exit 0

# Build a single alternation of non-empty, non-comment patterns.
pattern="$(grep -vE '^\s*(#|$)' "$DENY_FILE" | paste -sd '|' -)"
[[ -z "$pattern" ]] && exit 0

status=0
for f in "${files[@]}"; do
  [[ -f "$f" ]] || continue
  if grep -rniE "$pattern" "$f" >/dev/null 2>&1; then
    echo "✗ forbidden identifier in: $f"
    grep -niE "$pattern" "$f" | sed 's/^/    /'
    status=1
  fi
done

[[ $status -ne 0 ]] && echo "Blocked: staged files contain identifiers from $DENY_FILE."
exit $status
