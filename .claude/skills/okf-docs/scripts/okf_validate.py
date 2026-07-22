#!/usr/bin/env python3
"""okf_validate.py — Conformance checker + linter for Open Knowledge Format (OKF v0.1) bundles.

Splits findings into two tiers, mirroring the spec:

  ERRORS   — hard conformance violations from SPEC §9. A bundle with any error
             is NOT conformant. These fail the run (exit code 1).
  WARNINGS — soft guidance (recommended frontmatter, resolvable links, index
             coverage, ISO timestamps, known type vocabulary). A consumer MUST
             tolerate these (SPEC §9), so they never fail the run on their own.

Usage:
  okf_validate.py <path> [<path> ...]        # dirs (bundle roots) or single .md files
  okf_validate.py docs/ --json               # machine-readable report to stdout
  okf_validate.py docs/ --strict             # treat warnings as failures too
  okf_validate.py docs/ --vocab a,b,c        # override the known type vocabulary

Exit codes: 0 = conformant (no errors; no warnings under --strict), 1 = violations,
2 = bad invocation (path missing, etc.).

Pure-stdlib except PyYAML, which the spec-producing ecosystem already depends on.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.stderr.write("okf_validate: PyYAML is required (pip install pyyaml)\n")
    sys.exit(2)

RESERVED = {"index.md", "log.md"}

# Repo-specific type vocabulary. Unknown types are legal per SPEC (consumers must
# tolerate them) — this list only drives a soft warning to keep our own bundle
# self-consistent. Override with --vocab.
DEFAULT_VOCAB = {
    "Spec", "Plan", "ADR", "Reference", "Playbook", "Runbook",
    "Analysis", "Research", "Service", "Component", "Metric",
    "Dashboard", "Config", "Guide", "Index", "FeatureRequest",
}

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?\n)^---\s*\n?", re.DOTALL | re.MULTILINE)
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ISO_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$")
# Markdown links: [text](target). Captures the target.
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


@dataclass
class Finding:
    level: str   # "error" | "warning"
    concept: str  # concept id or file path relative to bundle root
    rule: str
    message: str


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    files_checked: int = 0

    def add(self, level: str, concept: str, rule: str, message: str) -> None:
        self.findings.append(Finding(level, concept, rule, message))

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "error"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "warning"]


def split_frontmatter(text: str):
    """Return (frontmatter_dict_or_None, parse_error_or_None, had_delimiters)."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None, None, False
    raw = m.group(1)
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        return None, str(e).replace("\n", " "), True
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return None, "frontmatter is not a YAML mapping", True
    return data, None, True


def concept_id(bundle_root: Path, path: Path) -> str:
    rel = path.relative_to(bundle_root)
    return str(rel.with_suffix("")) if rel.suffix == ".md" else str(rel)


def has_uri_scheme(value: str) -> bool:
    return bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", value))


def check_concept(bundle_root: Path, path: Path, all_ids: set[str], vocab: set[str], rep: Report) -> None:
    cid = concept_id(bundle_root, path)
    text = path.read_text(encoding="utf-8", errors="replace")
    fm, err, had = split_frontmatter(text)

    # §9.1 — parseable frontmatter block
    if not had:
        rep.add("error", cid, "frontmatter-present",
                "no YAML frontmatter block (file must open with '---' ... '---')")
        return
    if err:
        rep.add("error", cid, "frontmatter-parseable", f"unparseable YAML frontmatter: {err}")
        return

    # §9.2 — non-empty type
    t = fm.get("type")
    if t is None or (isinstance(t, str) and not t.strip()):
        rep.add("error", cid, "type-required", "missing or empty required field 'type'")
    elif not isinstance(t, str):
        rep.add("error", cid, "type-required", f"'type' must be a string, got {type(t).__name__}")
    elif t not in vocab:
        rep.add("warning", cid, "type-known",
                f"type '{t}' is not in the repo vocabulary (legal, but check it is intentional)")

    # Recommended fields (soft)
    if not fm.get("title"):
        rep.add("warning", cid, "title-recommended", "no 'title' (consumers will fall back to the filename)")
    if not fm.get("description"):
        rep.add("warning", cid, "description-recommended",
                "no 'description' (index generators and previews rely on it)")

    # timestamp shape (soft)
    ts = fm.get("timestamp")
    if ts is not None and not ISO_DATETIME_RE.match(str(ts).strip()):
        rep.add("warning", cid, "timestamp-iso", f"'timestamp' is not ISO 8601: {ts!r}")

    # resource shape (soft)
    res = fm.get("resource")
    if res is not None and isinstance(res, str) and res.strip() and not has_uri_scheme(res.strip()):
        rep.add("warning", cid, "resource-uri", f"'resource' is not a URI (no scheme): {res!r}")

    # Cross-links (soft) — flag targets that don't resolve within the bundle.
    body = text[FRONTMATTER_RE.match(text).end():]
    for target in LINK_RE.findall(body):
        check_link(bundle_root, path, cid, target, all_ids, rep)


def check_link(bundle_root: Path, path: Path, cid: str, target: str, all_ids: set[str], rep: Report) -> None:
    raw = target.strip()
    # External / anchors / mailto — not our concern.
    if (has_uri_scheme(raw) and not raw.startswith("/")) or raw.startswith("#") or raw.startswith("mailto:"):
        return
    link = raw.split("#", 1)[0].split("?", 1)[0]
    if not link:
        return
    # Directory link (index reference) — resolve to that dir existing.
    if link.endswith("/"):
        if link.startswith("/"):
            resolved = bundle_root / link.lstrip("/")
        else:
            resolved = (path.parent / link)
        if not resolved.is_dir():
            rep.add("warning", cid, "link-resolves",
                    f"link to directory '{target}' does not exist in the bundle")
        return
    if not link.endswith(".md"):
        return  # links to non-markdown assets aren't validated here
    if link.startswith("/"):
        resolved = bundle_root / link.lstrip("/")
    else:
        resolved = (path.parent / link).resolve()
        try:
            resolved = bundle_root / resolved.relative_to(bundle_root.resolve())
        except ValueError:
            return  # escapes bundle; leave it alone
    if not resolved.is_file():
        rep.add("warning", cid, "link-resolves",
                f"broken cross-link '{target}' (target not in bundle — may be not-yet-written)")


def check_index(bundle_root: Path, path: Path, rep: Report) -> None:
    cid = concept_id(bundle_root, path)
    text = path.read_text(encoding="utf-8", errors="replace")
    fm, err, had = split_frontmatter(text)
    is_root = path.parent.resolve() == bundle_root.resolve()
    if had:
        # §6 / §11 — frontmatter permitted ONLY in the bundle-root index.md, and
        # then only to carry okf_version.
        if not is_root:
            rep.add("error", cid, "index-no-frontmatter",
                    "index.md must not contain frontmatter except at the bundle root")
        elif err:
            rep.add("error", cid, "index-frontmatter-parseable", f"unparseable frontmatter: {err}")
        elif fm and set(fm.keys()) - {"okf_version"}:
            extra = ", ".join(sorted(set(fm.keys()) - {"okf_version"}))
            rep.add("warning", cid, "index-root-frontmatter",
                    f"root index.md frontmatter should only carry 'okf_version' (also has: {extra})")


def check_log(bundle_root: Path, path: Path, rep: Report) -> None:
    cid = concept_id(bundle_root, path)
    text = path.read_text(encoding="utf-8", errors="replace")
    if FRONTMATTER_RE.match(text):
        rep.add("warning", cid, "log-no-frontmatter", "log.md should not carry frontmatter")
    # §7 — date headings must be ISO YYYY-MM-DD.
    for line in text.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m and not ISO_DATE_RE.match(m.group(1)):
            rep.add("error", cid, "log-date-iso",
                    f"log date heading '## {m.group(1)}' is not ISO 8601 (YYYY-MM-DD)")


def collect_ids(bundle_root: Path) -> set[str]:
    ids = set()
    for p in bundle_root.rglob("*.md"):
        if p.name in RESERVED:
            continue
        ids.add(concept_id(bundle_root, p))
    return ids


def validate_bundle(bundle_root: Path, vocab: set[str], rep: Report) -> None:
    all_ids = collect_ids(bundle_root)
    dirs_with_concepts: set[Path] = set()
    for p in sorted(bundle_root.rglob("*.md")):
        rep.files_checked += 1
        if p.name == "index.md":
            check_index(bundle_root, p, rep)
        elif p.name == "log.md":
            check_log(bundle_root, p, rep)
        else:
            check_concept(bundle_root, p, all_ids, vocab, rep)
            dirs_with_concepts.add(p.parent)
    # Index coverage (soft): a directory holding concepts benefits from an index.md.
    for d in sorted(dirs_with_concepts):
        if not (d / "index.md").is_file():
            rel = d.relative_to(bundle_root)
            rep.add("warning", str(rel) or ".", "index-coverage",
                    f"directory '{rel or '.'}/' has concepts but no index.md (progressive disclosure)")


def print_human(rep: Report, roots: list[str]) -> None:
    for f in rep.errors:
        print(f"  ERROR   [{f.rule}] {f.concept}: {f.message}")
    for f in rep.warnings:
        print(f"  warning [{f.rule}] {f.concept}: {f.message}")
    print()
    print(f"Checked {rep.files_checked} file(s) under: {', '.join(roots)}")
    print(f"  {len(rep.errors)} error(s), {len(rep.warnings)} warning(s)")
    print("  CONFORMANT ✓" if not rep.errors else "  NOT CONFORMANT ✗")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Validate OKF v0.1 bundles.")
    ap.add_argument("paths", nargs="+", help="bundle root dir(s) or single .md file(s)")
    ap.add_argument("--json", action="store_true", help="emit a JSON report")
    ap.add_argument("--strict", action="store_true", help="treat warnings as failures too")
    ap.add_argument("--vocab", help="comma-separated type vocabulary override")
    args = ap.parse_args(argv)

    vocab = set(v.strip() for v in args.vocab.split(",")) if args.vocab else DEFAULT_VOCAB
    rep = Report()

    for raw in args.paths:
        path = Path(raw)
        if not path.exists():
            sys.stderr.write(f"okf_validate: path not found: {raw}\n")
            return 2
        if path.is_dir():
            validate_bundle(path, vocab, rep)
        elif path.suffix == ".md":
            # Single-file mode: treat the file's parent as the (mini) bundle root.
            root = path.parent
            all_ids = collect_ids(root)
            rep.files_checked += 1
            if path.name == "index.md":
                check_index(root, path, rep)
            elif path.name == "log.md":
                check_log(root, path, rep)
            else:
                check_concept(root, path, all_ids, vocab, rep)
        else:
            sys.stderr.write(f"okf_validate: not a directory or .md file: {raw}\n")
            return 2

    if args.json:
        print(json.dumps({
            "files_checked": rep.files_checked,
            "conformant": not rep.errors,
            "error_count": len(rep.errors),
            "warning_count": len(rep.warnings),
            "findings": [f.__dict__ for f in rep.findings],
        }, indent=2))
    else:
        print_human(rep, args.paths)

    if rep.errors:
        return 1
    if args.strict and rep.warnings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
