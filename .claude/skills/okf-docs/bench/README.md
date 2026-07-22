# okf-docs benchmark

This folder benchmarks the `okf-docs` skill: does loading it actually make a
model produce conformant OKF documents, and how cheap a model can we get away
with before quality drops? Results are tracked per skill version in
[`../EVALUATIONS.md`](../EVALUATIONS.md) so we can see whether each refinement
iteration improves things.

## How it works

The runner is [`../scripts/benchmark.py`](../scripts/benchmark.py) (vendored from
[`ibaou-dev/skills`](https://github.com/ibaou-dev/skills), MIT, extended here with
an `agy` executor). For every eval in [`../evals/evals.json`](../evals/evals.json)
it runs the model **with** the skill loaded and **without** it, grades the emitted
document against that eval's assertions, and reports the pass-rate delta.

Grading targets the **emitted markdown text**, not files on disk — so every
backend is judged the same way, from `claude -p` to a chat-only local model. The
eval prompts therefore demand the finished document inline (no file writes). This
measures the skill's real contribution: does the output carry YAML frontmatter, a
valid `type`, bundle-absolute cross-links, and a `# Citations` block, or is it
free-form prose?

Assertions are ~85% deterministic regex (free, reproducible) plus a few
`[LLM-judge]` ones that fall back to regex when `judge: none` — so the whole
matrix runs offline with no judge cost.

## Reproduce

```bash
# From the repo root
python3 .claude/skills/okf-docs/scripts/benchmark.py \
    --config .claude/skills/okf-docs/bench/bench.json

# Merged table, latest run per model label
python3 .claude/skills/okf-docs/scripts/benchmark.py \
    --skill .claude/skills/okf-docs --report

# One model, ad-hoc
python3 .claude/skills/okf-docs/scripts/benchmark.py \
    --skill .claude/skills/okf-docs \
    --executor session --model claude-haiku-4-5-20251001 \
    --judge none --mode both --detail
```

Raw results append to `.bench/okf-docs/results.ndjson` (gitignored). The
per-version summary tables live in `../EVALUATIONS.md` (tracked).

## The matrix

`bench.json` defines the runs. Iteration-1 uses key-free CLI backends:

| Label | Backend | Why |
|-------|---------|-----|
| `opus-session` | `claude -p --model opus` | Quality ceiling / reference |
| `sonnet-session` | `claude -p --model sonnet` | Mid Claude tier |
| `haiku-session` | `claude -p --model claude-haiku-4-5-20251001` | Cheapest Claude — the "is it good enough" line |
| `north-mini-code-oss` | `opencode` free Zen | Cheap OSS coder |
| `deepseek-v4-flash-oss` | `opencode` free Zen | Cheap OSS |
| `nemotron-3-ultra-oss` | `opencode` free Zen | Cheap OSS |
| `agy-gemini` | `agy -p` | Gemini CLI |

To add local qwen (LM Studio on the 3090), OpenRouter, or bigger routed OSS, see
[`adding-backends.md`](adding-backends.md).

## Iterating

1. Run the matrix, read `--report` and the per-assertion `--detail`.
2. Improve `SKILL.md` / templates where models fail (especially the cheap ones —
   they reveal where the skill leans on the model being clever).
3. Bump `metadata.version` in `SKILL.md`.
4. Re-run, append a new versioned section to `../EVALUATIONS.md`, and check the
   delta moved the right way.
