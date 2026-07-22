# Adding model backends to the okf-docs benchmark

The benchmark matrix lives in `bench/bench.json` and is run with the vendored
`scripts/benchmark.py`. Iteration-1 uses only CLI backends that need no API keys:
`session` (Claude via `claude -p`), `opencode` (free OSS Zen models), and `agy`
(Gemini CLI). Below are the ready-to-paste `runs[]` entries for the other
backends — add them when the dependency is available.

Run everything with:

```bash
python3 .claude/skills/okf-docs/scripts/benchmark.py --config .claude/skills/okf-docs/bench/bench.json
python3 .claude/skills/okf-docs/scripts/benchmark.py --skill .claude/skills/okf-docs --report
```

## Local qwen on the 3090 via LM Studio (the target)

Start LM Studio → Developer tab → enable **"Serve on Local Network"** so WSL can
reach the Windows host, and load a coder model that fits a 3090 (e.g.
`qwen3-coder-30b-a3b-instruct` at Q4). LM Studio serves an OpenAI-compatible API
on `:1234`, so use the `openai_compat` executor. From WSL, the Windows host is
reachable at the default-route IP (`ip route | awk '/^default/{print $3}'`) or,
with network serving on, `http://<windows-lan-ip>:1234`.

```json
{
  "label": "qwen3-coder-30b-lmstudio",
  "executor": {
    "type": "openai_compat",
    "model": "qwen3-coder-30b-a3b-instruct",
    "base_url": "http://<windows-host-ip>:1234",
    "temperature": 0.2
  },
  "judge": { "type": "none" }
}
```

`openai_compat` posts to `{base_url}/v1/chat/completions` and needs the `requests`
package (`pip install requests`). No API key is required for LM Studio; leave
`api_key`/`api_key_env` unset.

### Alternative: the old custom `local` endpoint

If you serve qwen behind the custom `{system_prompt, input}` schema at
`/api/v1/chat` (the shape in the original sample config), use the `local`
executor instead:

```json
{
  "label": "qwen3-local",
  "executor": {
    "type": "local",
    "model": "qwen3-coder-30b-a3b-instruct",
    "base_url": "http://<host>:1453",
    "temperature": 0.2
  },
  "judge": { "type": "none" }
}
```

## OpenRouter (SOTA OSS without local hardware)

Set a key first: `export OPENROUTER_API_KEY=sk-or-v1-…` (or put it in a
gitignored `.env` and source it).

```json
{
  "label": "qwen3-235b-openrouter",
  "executor": {
    "type": "openai_compat",
    "model": "qwen/qwen3-235b-a22b-instruct",
    "base_url": "https://openrouter.ai/api/v1",
    "api_key_env": "OPENROUTER_API_KEY",
    "temperature": 0.2
  },
  "judge": { "type": "none" }
}
```

## opencode routed OSS (vertex / openrouter via opencode, no key management)

`opencode models` lists routes already configured on this machine. Any of these
can be an `opencode` executor model — opencode handles auth:

```json
{ "label": "qwen3-235b-vertex", "executor": { "type": "opencode", "model": "google-vertex/qwen/qwen3-235b-a22b-instruct-2507-maas" }, "judge": { "type": "none" } },
{ "label": "glm-5-vertex",     "executor": { "type": "opencode", "model": "google-vertex/zai-org/glm-5-maas" }, "judge": { "type": "none" } },
{ "label": "kimi-k2-vertex",   "executor": { "type": "opencode", "model": "google-vertex/moonshotai/kimi-k2-thinking-maas" }, "judge": { "type": "none" } }
```

## Turning on LLM-as-judge

The iteration-1 matrix uses `judge: {"type": "none"}` — every assertion is graded
by regex (LLM-judge assertions fall back to their `regex_fallback`). This is free,
deterministic, and fair across models. To grade the `[LLM-judge]` assertions
semantically instead, set a judge on a run:

```json
"judge": { "type": "session" }                      // uses claude -p (current Claude)
"judge": { "type": "openai_compat", "model": "…", "base_url": "…", "api_key_env": "…" }
```

Hybrid pattern: cheap/local model as executor + `session` (or a cheap
`openai_compat`) as judge — LLM-graded quality without a second paid executor.
