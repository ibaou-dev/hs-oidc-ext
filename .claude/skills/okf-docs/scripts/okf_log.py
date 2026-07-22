#!/usr/bin/env python3
"""okf_log.py — Append a dated entry to an OKF `log.md` (SPEC §7).

Keeps entries grouped under ISO `YYYY-MM-DD` date headings, newest group first.
A new entry for today is added under today's heading (created if absent, and
floated to the top). The leading bold verb (**Update**, **Creation**, …) is a
convention, not a requirement — pass it via --kind.

Usage:
  okf_log.py <path/to/log.md> --kind Creation --message "Added [orders](/tables/orders.md)."
  okf_log.py docs/log.md --kind Update --message "Revised the stack spec." --date 2026-07-16

--date defaults to today's date. Because the sandbox forbids reading the clock in
some contexts, pass --date explicitly in automated/agentic use.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import UTC
from pathlib import Path

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
HEADING_RE = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})\s*$")


def today() -> str:
    from datetime import datetime
    return datetime.now(UTC).date().isoformat()


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Append an entry to an OKF log.md")
    ap.add_argument("log_path")
    ap.add_argument("--message", required=True)
    ap.add_argument("--kind", default="Update", help="leading bold verb, e.g. Creation/Update/Deprecation")
    ap.add_argument("--date", help="ISO YYYY-MM-DD; defaults to today (UTC)")
    ap.add_argument("--title", default="Update Log", help="H1 used when creating a new log")
    args = ap.parse_args(argv)

    day = args.date or today()
    if not DATE_RE.match(day):
        sys.stderr.write(f"okf_log: --date must be ISO YYYY-MM-DD, got {day!r}\n")
        return 2

    entry = f"* **{args.kind}**: {args.message}".rstrip()
    path = Path(args.log_path)

    if not path.exists():
        path.write_text(f"# {args.title}\n\n## {day}\n{entry}\n", encoding="utf-8")
        print(f"created {path} with first entry")
        return 0

    lines = path.read_text(encoding="utf-8").splitlines()
    h1_idx = next((i for i, l in enumerate(lines) if l.startswith("# ")), -1)
    # All existing date headings with their line index, in file order.
    dates = [(i, m.group(1)) for i, l in enumerate(lines) if (m := HEADING_RE.match(l))]

    day_idx = next((i for i, d in dates if d == day), None)

    if day_idx is not None:
        # Same day already present — add this entry directly under its heading.
        lines.insert(day_idx + 1, entry)
    else:
        block = [f"## {day}", entry, ""]
        # Keep date groups sorted newest-first: insert before the first existing
        # group whose date is older than `day`; if none is older, append after the
        # last group; if there are no groups yet, place right after the H1.
        insert_at = next((i for i, d in dates if d < day), None)
        if insert_at is None:
            if dates:
                # After the last group — find end of the file's content.
                insert_at = len(lines)
            else:
                insert_at = h1_idx + 1 if h1_idx >= 0 else 0
        if insert_at > 0 and insert_at <= len(lines) and lines[insert_at - 1].strip():
            block = [""] + block
        lines[insert_at:insert_at] = block

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"appended {args.kind} entry under {day} in {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
