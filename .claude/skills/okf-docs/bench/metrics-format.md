# Benchmark Metrics Format

## results.ndjson — primary results store (benchmark.py)

Written by `scripts/benchmark.py`. Lives at `.bench/<skill-name>/results.ndjson`
(gitignored). One JSON record per line, append-only. View with `--report`.

```json
{"timestamp":"2026-03-30T10:00:00+00:00","skill":"git-conventional-commits","skill_version":"v1.0.0","label":"minimax-zen","executor":{"type":"opencode","model":"opencode/minimax-m2.5-free","base_url":"","api_key_env":"","api_key":"","temperature":0.2},"judge":{"type":"none","model":"","base_url":"","api_key_env":"","api_key":""},"mode":"both","n":50,"pct_with":96.0,"pct_without":54.0,"delta_pp":42.0,"runs":[...]}
```

Top-level fields:

| Field | Type | Description |
|---|---|---|
| `timestamp` | ISO-8601 | UTC run time |
| `skill` | string | skill directory name |
| `skill_version` | string | from config |
| `label` | string | human label from bench.json |
| `executor` | object | full ExecutorConfig |
| `judge` | object | full JudgeConfig |
| `mode` | string | `with`, `without`, or `both` |
| `n` | int | total assertions graded |
| `pct_with` | float | pass % with skill |
| `pct_without` | float | pass % without skill |
| `delta_pp` | float | pct_with − pct_without |
| `runs` | array | per-eval detail (see below) |

Per-eval run fields (inside `runs[]`):

```json
{"eval_id":1,"name":"type-discrimination-refactor-vs-feat","mode":"with","response":"...","results":[{"id":"1.1","text":"...","passed":true,"note":""}],"passed":5,"total":5,"elapsed_s":17.3}
```

---

## benchmark.json schema (skill-creator legacy format)

Written per-skill after a full benchmark run. Lives at
`<workspace>/benchmark.json`.

```json
{
  "skill": "git-conventional-commits",
  "version": "1.0.0",
  "run_date": "2026-03-29T00:00:00Z",
  "models": [
    {
      "model": "claude-sonnet-4-6",
      "with_skill": {
        "pass_count": 48,
        "total": 50,
        "pass_rate": 0.96,
        "avg_tokens": 8400,
        "avg_time_seconds": 23.1,
        "eval_results": [
          {
            "eval_id": 1,
            "eval_name": "type-discrimination-refactor-vs-feat",
            "pass_count": 5,
            "total": 5,
            "assertions": [
              { "id": "1.1", "pass": true },
              { "id": "1.2", "pass": true },
              { "id": "1.3", "pass": true },
              { "id": "1.4", "pass": true },
              { "id": "1.5", "pass": true }
            ]
          }
        ]
      },
      "without_skill": {
        "pass_count": 27,
        "total": 50,
        "pass_rate": 0.54,
        "avg_tokens": 6200,
        "avg_time_seconds": 18.4,
        "eval_results": []
      },
      "delta_pp": 42
    }
  ],
  "summary": {
    "total_assertions": 50,
    "best_model": "claude-sonnet-4-6",
    "best_with_skill_rate": 0.96,
    "best_delta_pp": 42
  }
}
```

## grading.json schema

Written per eval run (one file per model × mode × eval).

```json
{
  "eval_id": 1,
  "eval_name": "type-discrimination-refactor-vs-feat",
  "model": "claude-sonnet-4-6",
  "mode": "with_skill",
  "output_file": "eval-1-output.txt",
  "grading_method": "regex",
  "assertions": [
    {
      "id": "1.1",
      "text": "The commit type is exactly 'refactor'...",
      "pass": true,
      "grading_method": "regex",
      "pattern": "^refactor"
    },
    {
      "id": "1.2",
      "text": "The description uses imperative mood...",
      "pass": true,
      "grading_method": "regex",
      "pattern": "^refactor[^:]*: (extract|rename|restructure|move|reorganize|split)"
    }
  ],
  "pass_count": 5,
  "total": 5,
  "tokens_used": 8412,
  "time_seconds": 22.3
}
```

## timing.json schema

Written per eval run alongside the output file.

```json
{
  "eval_id": 1,
  "model": "claude-sonnet-4-6",
  "mode": "with_skill",
  "start_time": "2026-03-29T10:00:00Z",
  "end_time": "2026-03-29T10:00:22Z",
  "elapsed_seconds": 22.3,
  "tokens_input": 1240,
  "tokens_output": 380,
  "tokens_total": 1620
}
```

## EVALUATIONS.md row format

Each model run appends a row to the skill's section in EVALUATIONS.md:

```markdown
## `git-conventional-commits` — v1.0.0

|             | With Skill      | Without Skill   | Delta     |
| ----------- | --------------- | --------------- | --------- |
| **Overall** | **48/50 (96%)** | **27/50 (54%)** | **+42pp** |

<details>
<summary>Full breakdown (50 assertions)</summary>

_Model: claude-sonnet-4-6 · 1 run · 2026-03-29 · grading: regex + LLM-as-judge
(assertions 9.1, 9.2, 10.1, 10.2)_

| #   | Assertion                                                                      | With                           | Without                        |
| --- | ------------------------------------------------------------------------------ | ------------------------------ | ------------------------------ |
|     | **type-discrimination-refactor-vs-feat** — rename+extract is refactor not feat | **<span class="g">5/5</span>** | **<span class="r">2/5</span>** |
| 1.1 | type is refactor                                                               | <span class="g">✓</span>       | <span class="r">✗</span>       |
```

## Summary table update rules

After every eval run, update the Summary table in EVALUATIONS.md:

1. Add or update the row for the evaluated skill
2. Recompute the Total row (sum all numerators and denominators)
3. Sort rows by Delta ascending (lowest delta first)
4. Populate the Concern column:
   - "Low delta" if Delta ≤ 32pp
   - "High without" if Without ≥ 65%
   - "Low with-skill score" if With ≤ 90%
   - Combine multiple concerns with comma
5. Uplift = With / Without, rounded to 2 decimal places, suffixed with `×`
