#!/usr/bin/env python3
"""okf_index.py — Generate/refresh OKF `index.md` files for progressive disclosure.

For each directory in a bundle it writes an `index.md` that lists:
  - child subdirectories (linking to their own index.md), then
  - concept documents in that directory,
each with the `description` pulled from the target's frontmatter (SPEC §6).

By default it (re)generates the index for every directory that contains concepts
or subdirectories. The bundle-root index.md is preserved if it carries an
`okf_version` frontmatter block — that line is re-emitted at the top.

Usage:
  okf_index.py <bundle-root>                 # write index.md everywhere
  okf_index.py <bundle-root> --dir docs/specs  # just one directory
  okf_index.py <bundle-root> --check         # don't write; exit 1 if stale
  okf_index.py <bundle-root> --print         # print to stdout, don't write
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.stderr.write("okf_index: PyYAML is required (pip install pyyaml)\n")
    sys.exit(2)

RESERVED = {"index.md", "log.md"}
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?\n)^---\s*\n?", re.DOTALL | re.MULTILINE)


def frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    try:
        data = yaml.safe_load(m.group(1))
        return data if isinstance(data, dict) else {}
    except yaml.YAMLError:
        return {}


def title_for(path: Path, fm: dict) -> str:
    return fm.get("title") or path.stem.replace("_", " ").replace("-", " ").title()


def dir_description(d: Path) -> str:
    idx = d / "index.md"
    if idx.is_file():
        # A generated index has no per-dir description; fall back to first concept's.
        for p in sorted(d.glob("*.md")):
            if p.name not in RESERVED:
                desc = frontmatter(p).get("description")
                if desc:
                    return desc
    return ""


def render_index(d: Path, bundle_root: Path) -> str:
    is_root = d.resolve() == bundle_root.resolve()
    subdirs = sorted([c for c in d.iterdir() if c.is_dir() and not c.name.startswith(".")])
    concepts = sorted([c for c in d.glob("*.md") if c.name not in RESERVED])

    lines: list[str] = []

    # Preserve okf_version at the root.
    if is_root:
        fm = frontmatter(d / "index.md") if (d / "index.md").is_file() else {}
        version = fm.get("okf_version")
        if version:
            lines += ["---", f'okf_version: "{version}"', "---", ""]

    if subdirs:
        lines.append("# Subdirectories")
        lines.append("")
        for sub in subdirs:
            if not any(sub.rglob("*.md")):
                continue
            desc = dir_description(sub)
            suffix = f" - {desc}" if desc else ""
            lines.append(f"* [{sub.name}]({sub.name}/index.md){suffix}")
        lines.append("")

    if concepts:
        lines.append("# Concepts")
        lines.append("")
        for c in concepts:
            fm = frontmatter(c)
            desc = fm.get("description", "")
            suffix = f" - {desc}" if desc else ""
            lines.append(f"* [{title_for(c, fm)}]({c.name}){suffix}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def target_dirs(bundle_root: Path, only: Path | None) -> list[Path]:
    if only:
        return [only]
    dirs = {bundle_root}
    for p in bundle_root.rglob("*.md"):
        if p.name not in RESERVED:
            dirs.add(p.parent)
    return sorted(dirs)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Generate OKF index.md files.")
    ap.add_argument("bundle_root")
    ap.add_argument("--dir", help="only (re)generate this directory's index.md")
    ap.add_argument("--check", action="store_true", help="exit 1 if any index is stale; write nothing")
    ap.add_argument("--print", dest="do_print", action="store_true", help="print instead of writing")
    args = ap.parse_args(argv)

    bundle_root = Path(args.bundle_root)
    if not bundle_root.is_dir():
        sys.stderr.write(f"okf_index: not a directory: {bundle_root}\n")
        return 2
    only = Path(args.dir) if args.dir else None

    stale = 0
    for d in target_dirs(bundle_root, only):
        if not any(d.glob("*.md")) and not any(c.is_dir() for c in d.iterdir()):
            continue
        content = render_index(d, bundle_root)
        idx = d / "index.md"
        current = idx.read_text(encoding="utf-8") if idx.is_file() else None
        if args.do_print:
            print(f"===== {idx} =====")
            print(content)
            continue
        if content != current:
            stale += 1
            if args.check:
                print(f"stale: {idx}")
            else:
                idx.write_text(content, encoding="utf-8")
                print(f"wrote: {idx}")

    if args.check and stale:
        return 1
    if not args.do_print and not args.check:
        print(f"done ({stale} file(s) updated)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
