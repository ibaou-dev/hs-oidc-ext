#!/usr/bin/env python3
"""render_evaluations.py — turn benchmark results into an EVALUATIONS.md section.

Reads .bench/okf-docs/results.ndjson (latest run per model label), renders a
per-model summary table sorted best-first, and highlights the *cheapest tier that
still holds quality* — the whole point of the exercise. Appends (or previews) a
versioned section to the skill's EVALUATIONS.md.

Usage:
  render_evaluations.py --skill-name okf-docs --version v0.1.0            # preview to stdout
  render_evaluations.py --skill-name okf-docs --version v0.1.0 --write    # append to EVALUATIONS.md
  render_evaluations.py ... --hold-threshold 80                           # quality bar for the callout

Cost tiers are heuristic (by label/model substring) only to order the table from
cheap→expensive so "cheapest that holds" reads top-down; they don't affect grading.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


# Lower rank = cheaper. Used only for display ordering + the callout.
def cost_rank(label: str, model: str) -> int:
    s = f"{label} {model}".lower()
    if "free" in s or "oss" in s:
        return 0
    if "haiku" in s:
        return 1
    if "agy" in s or "gemini" in s or "flash" in s or "mini" in s:
        return 1
    if "sonnet" in s:
        return 2
    if "opus" in s:
        return 3
    return 2


def latest_per_label(records: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for r in records:
        seen[r["label"]] = r
    return list(seen.values())


def fmt_pct(r: dict, key: str) -> str:
    return f"{r[key]:.0f}%" if key in r else "—"


def uplift(r: dict) -> str:
    if "pct_with" in r and "pct_without" in r and r["pct_without"]:
        return f"{r['pct_with'] / r['pct_without']:.2f}×"
    if r.get("pct_with"):
        return "∞×"
    return "—"


def render(records: list[dict], skill_name: str, version: str, hold: float) -> str:
    rows = latest_per_label(records)
    rows.sort(key=lambda r: (cost_rank(r["label"], r.get("executor", {}).get("model", "")), -r.get("pct_with", 0)))

    date = max((r.get("timestamp", "") for r in rows), default="")[:10]
    n = rows[0].get("n", "?") if rows else "?"

    lines = ["<!-- prettier-ignore-start -->", ""]
    lines.append(f"## `{skill_name}` — {version}")
    lines.append("")
    lines.append(f"_Assertions: {n} · grading: regex + LLM-judge-with-regex-fallback (judge=none) · {date}_")
    lines.append("")
    lines.append("| Model | Backend | With | Without | Δ | Uplift |")
    lines.append("| --- | --- | --- | --- | --- | --- |")

    hold_candidates = []
    for r in rows:
        model = r.get("executor", {}).get("model", "") or r.get("executor", {}).get("type", "")
        backend = r.get("executor", {}).get("type", "")
        pw = fmt_pct(r, "pct_with")
        pwo = fmt_pct(r, "pct_without")
        delta = f"{r['delta_pp']:+.0f}pp" if "delta_pp" in r else "—"
        lines.append(f"| `{r['label']}` | {backend} | {pw} | {pwo} | {delta} | {uplift(r)} |")
        if r.get("pct_with", 0) >= hold and r.get("delta_pp", 0) > 0:
            hold_candidates.append(r)

    lines.append("")
    if hold_candidates:
        cheapest = min(hold_candidates, key=lambda r: cost_rank(r["label"], r.get("executor", {}).get("model", "")))
        lines.append(
            f"**Cheapest tier that holds (≥{hold:.0f}% with-skill, positive delta):** "
            f"`{cheapest['label']}` — {fmt_pct(cheapest, 'pct_with')} with the skill "
            f"vs {fmt_pct(cheapest, 'pct_without')} without ({cheapest.get('delta_pp', 0):+.0f}pp)."
        )
    else:
        lines.append(f"**No model cleared the ≥{hold:.0f}% with-skill bar this iteration.** "
                     f"Improve the skill and re-run.")
    lines.append("")
    lines.append("### Analysis")
    lines.append("")
    lines.append("_(fill in: where cheap models fail, which assertions never discriminate, next steps)_")
    lines.append("")
    lines.append("<!-- prettier-ignore-end -->")
    lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill-name", default="okf-docs")
    ap.add_argument("--version", required=True)
    ap.add_argument("--results", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--hold-threshold", type=float, default=80.0)
    ap.add_argument("--write", action="store_true", help="append the section to EVALUATIONS.md")
    args = ap.parse_args(argv)

    results = Path(args.results) if args.results else Path(".bench") / args.skill_name / "results.ndjson"
    if not results.exists():
        print(f"no results at {results}")
        return 1
    records = [json.loads(l) for l in results.read_text().splitlines() if l.strip()]
    section = render(records, args.skill_name, args.version, args.hold_threshold)

    out = Path(args.out) if args.out else Path(".claude/skills") / args.skill_name / "EVALUATIONS.md"
    if args.write:
        header = (
            f"# `{args.skill_name}` — benchmark history\n\n"
            "Tracks per-model, per-version skill uplift. Newest first. "
            "See [bench/README.md](bench/README.md).\n\n"
        )
        existing = out.read_text() if out.exists() else ""
        body = existing[len(header):] if existing.startswith(header) else existing
        out.write_text(header + section + "\n" + body)
        print(f"wrote {out}")
    else:
        print(section)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
