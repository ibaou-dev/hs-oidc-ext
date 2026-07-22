# `okf-docs` — benchmark history

Tracks per-model, per-version skill uplift. Newest first. See [bench/README.md](bench/README.md).

<!-- prettier-ignore-start -->

## `okf-docs` — v0.2.0

_Assertions: 34 · grading: regex + LLM-judge-with-regex-fallback (judge=none) · 2026-07-16_

Changes since v0.1.0: an inline **Shape by type** heading table, a firm
bundle-absolute cross-link mandate with example, and the exact `[N]` citation
format — so a model no longer has to open `type-vocabulary.md` mid-task.

| Model | Backend | With v0.1.0 → v0.2.0 | Without | Improvement |
| --- | --- | --- | --- | --- |
| `opus-session` | session | 88% → **100%** | 65% | +12pp with-skill |
| `sonnet-session` | session | 85% → **100%** | 68% | +15pp with-skill |
| `haiku-session` | session | 79% → **94%** | 38% | +15pp with-skill |

**Cheapest tier that holds:** `haiku-session` now reaches 94% with the skill (from
79%). The three recurring v0.1.0 gaps — bundle-absolute cross-links, Runbook
`Trigger`/`Steps`/`Verification` headings, numbered `[1]` citations — are resolved
for the Claude trio.

### Analysis

Comparing *with-skill absolute score* across versions (the without baseline is
noisy at one sample per eval, so it isn't the right yardstick). The inline table
+ mandates lifted every Claude tier, Opus and Sonnet to 34/34. Remaining Haiku
misses are occasional (2/34). **OSS not re-benchmarked at v0.2.0** — the opencode
free tier rate-limited under the full matrix's sustained load (it ran clean when
the OSS trio was benchmarked in isolation at v0.1.0). Re-run the OSS trio alone,
or via the LM Studio `openai_compat` path (injected skill, no auto-trigger
confound), for clean v0.2.0 OSS numbers.

<!-- prettier-ignore-end -->

<!-- prettier-ignore-start -->

## `okf-docs` — v0.1.0

_Assertions: 34 · grading: regex + LLM-judge-with-regex-fallback (judge=none) · 2026-07-16_

| Model | Backend | With | Without | Δ | Uplift |
| --- | --- | --- | --- | --- | --- |
| `deepseek-v4-flash-oss` | opencode | 62% | 41% | +21pp | 1.50× |
| `nemotron-3-ultra-oss` | opencode | 59% | 29% | +29pp | 2.00× |
| `north-mini-code-oss` | opencode | 29% | 26% | +3pp | 1.11× |
| `haiku-session` | session | 79% | 29% | +50pp | 2.70× |
| `sonnet-session` | session | 85% | 47% | +38pp | 1.81× |
| `opus-session` | session | 88% | 68% | +21pp | 1.30× |

**Cheapest tier that holds (≥75% with-skill, positive delta):** `haiku-session` — 79% with the skill vs 29% without (+50pp).

### Analysis

**The skill works and helps cheaper models most.** Every model improves with it;
uplift peaks in the mid/cheap tier (Haiku +50pp, nemotron +29pp) and is smallest
for Opus (+21pp) because Opus already writes decent structure unaided (68%
baseline). Haiku reaches 79% — the cheapest Claude that holds — up from 29%.

**Absolute conformance ceiling for cheap OSS is ~60%.** Two causes:

1. **opencode auto-trigger confound.** The `opencode` executor symlink-loads the
   skill and relies on the model *discovering* it in a single `opencode run`.
   Weak free models don't: `north-mini-code` emitted a plain doc with no
   frontmatter in "with" mode (≈ its "without" output) → only +3pp. The injected
   `session` runs don't have this problem. The eventual LM Studio qwen target
   uses `openai_compat`, which injects the skill as a system prompt, so it will
   measure application-given-context like `session` does — the fairer local test.
2. **Convention misses even when the skill is applied.** Recurring *with-skill*
   failures across models: bundle-absolute `/path.md` cross-links (Sonnet, Haiku),
   the Runbook conventional headings Trigger/Steps/Verification (all three Claude
   tiers paraphrased), and numbered `[1]` citations (Opus, Haiku). These live in
   `references/type-vocabulary.md`, which the model doesn't open mid-task.

**Non-discriminating assertions** (pass regardless of skill, candidates to prune
or harden in a later iteration): 0.9 (mentions all three services — they're named
in the prompt) and the `no-placeholder` checks 0.10/1.11/2.10 (trivially pass
when the model writes real content).

**Next (v0.2.0):** lift the per-type conventional headings, the cross-link
mandate, and the `[1]` citation format from the reference into the SKILL.md body
so they land without opening a second file — expected to raise the cheap-model
with-skill scores most. `agy` dropped this iteration (headless mode auto-denies an
MCP tool and emits nothing); LM Studio qwen deferred.

<!-- prettier-ignore-end -->

