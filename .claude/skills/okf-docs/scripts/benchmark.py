#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["requests>=2.31"]
# ///
#
# Run with uv (auto-installs deps, no venv setup needed):
#   uv run scripts/benchmark.py --skill skills/git-conventional-commits --report
#
# Or with plain python3 (requires: pip install requests):
#   python3 scripts/benchmark.py ...
"""
Unified skill benchmark runner.

Runs a skill's evals.json against any model via pluggable executor/judge backends.
Results are appended to .bench/<skill>/results.ndjson (gitignored, local history).

Usage:
    # Run with a config file
    python3 scripts/benchmark.py --config .bench/git-conventional-commits/bench.json

    # Quick single-run flags (no config file needed)
    python3 scripts/benchmark.py \\
        --skill skills/git-conventional-commits \\
        --executor opencode --model opencode/minimax-m2.5-free \\
        --judge none --mode both

    # Show merged results table (latest run per label)
    python3 scripts/benchmark.py --skill skills/git-conventional-commits --report

    # Scaffold a config file interactively
    python3 scripts/benchmark.py --skill skills/git-conventional-commits --init-config

Executor types:
    opencode      opencode run subprocess; skill loaded via ~/.agents/skills symlink
    openai_compat OpenAI-compatible HTTP POST to /v1/chat/completions
    local         Custom schema: POST /api/v1/chat {system_prompt, input} → output[N].content
    session       claude -p subprocess; skill body injected into prompt

Judge types:
    none          Regex-only (LLM-judged assertions use regex fallback)
    session       claude -p for LLM assertions; regex for the rest
    openai_compat External LLM via OpenAI-compat HTTP for LLM assertions
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

# `requests` is only needed by the HTTP executors/judges (openai_compat, local).
# Import it lazily so the CLI executors (session, agy, opencode) work without it.
try:
    import requests
except ImportError:
    requests = None


def _need_requests():
    if requests is None:
        sys.exit(
            "Missing dependency: requests (needed for openai_compat/local backends)\n"
            "  pip install requests\n"
            "  OR: uv run scripts/benchmark.py  (auto-installs, no setup needed)"
        )
    return requests

ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[mK]")
REQUEST_TIMEOUT = 300
RETRY_DELAY = 15  # seconds, doubles on each retry


# ---------------------------------------------------------------------------
# Config dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ExecutorConfig:
    type: str                   # opencode | openai_compat | local | session
    model: str = ""
    base_url: str = ""
    api_key_env: str = ""
    api_key: str = ""           # direct key, overrides api_key_env
    temperature: float = 0.2

    def resolved_key(self) -> str:
        if self.api_key:
            return self.api_key
        if self.api_key_env:
            return os.environ.get(self.api_key_env, "")
        return ""


@dataclass
class JudgeConfig:
    type: str = "none"          # none | session | openai_compat
    model: str = ""
    base_url: str = ""
    api_key_env: str = ""
    api_key: str = ""

    def resolved_key(self) -> str:
        if self.api_key:
            return self.api_key
        if self.api_key_env:
            return os.environ.get(self.api_key_env, "")
        return ""


@dataclass
class RunConfig:
    label: str
    executor: ExecutorConfig
    judge: JudgeConfig
    mode: str = "both"          # with | without | both


@dataclass
class BenchConfig:
    skill: str
    skill_version: str = "v1.0.0"
    evals: list = field(default_factory=list)   # [] = all
    delay: float = 3.0
    runs: list = field(default_factory=list)    # list[RunConfig]


def load_config(path: Path) -> BenchConfig:
    raw = json.loads(path.read_text())

    def parse_executor(d: dict) -> ExecutorConfig:
        return ExecutorConfig(**{k: v for k, v in d.items() if k in ExecutorConfig.__dataclass_fields__})

    def parse_judge(d: dict) -> JudgeConfig:
        return JudgeConfig(**{k: v for k, v in d.items() if k in JudgeConfig.__dataclass_fields__})

    runs = []
    for r in raw.get("runs", []):
        runs.append(RunConfig(
            label=r.get("label", r.get("executor", {}).get("model", "unnamed")),
            executor=parse_executor(r["executor"]),
            judge=parse_judge(r.get("judge", {"type": "none"})),
            mode=r.get("mode", raw.get("mode", "both")),
        ))

    return BenchConfig(
        skill=raw["skill"],
        skill_version=raw.get("skill_version", "v1.0.0"),
        evals=raw.get("evals", []),
        delay=raw.get("delay", 3.0),
        runs=runs,
    )


# ---------------------------------------------------------------------------
# Skill / eval loading
# ---------------------------------------------------------------------------

def load_skill_body(skill_dir: Path) -> str:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return ""
    text = skill_md.read_text()
    if text.startswith("---"):
        parts = text.split("---", 2)
        return parts[2].strip() if len(parts) >= 3 else text
    return text


def load_evals(skill_dir: Path) -> list[dict]:
    evals_file = skill_dir / "evals" / "evals.json"
    if not evals_file.exists():
        sys.exit(f"ERROR: evals.json not found at {evals_file}")
    return json.loads(evals_file.read_text())


def build_injected_prompt(prompt: str, skill_body: str, mode: str,
                          skill_context: str = "", context_label: str = "") -> str:
    """For session executor: inject skill body into the prompt text."""
    if mode == "without":
        return prompt
    label = context_label or "Supplementary context"
    if skill_context:
        return (
            f"{skill_body}\n\n"
            f"--- {label} ---\n"
            f"{skill_context}\n"
            f"--- END ---\n\n"
            f"{prompt}"
        )
    return f"{skill_body}\n\n---\n\n{prompt}"


# ---------------------------------------------------------------------------
# Executor: opencode (subprocess + symlink management)
# ---------------------------------------------------------------------------

def _skill_symlink(skill_name: str) -> Path:
    return Path.home() / ".agents" / "skills" / skill_name


def _ensure_skill_linked(skill_dir: Path) -> bool:
    target = _skill_symlink(skill_dir.name)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        return False
    target.symlink_to(skill_dir.resolve())
    return True


def _remove_skill_link(skill_name: str) -> bool:
    target = _skill_symlink(skill_name)
    if target.exists() or target.is_symlink():
        target.unlink()
        return True
    return False


def _ensure_workspace(skill_name: str) -> Path:
    workspace = Path(f"/tmp/{skill_name}-zen-workspace")
    workspace.mkdir(exist_ok=True)
    if not (workspace / ".git").exists():
        subprocess.run(["git", "init", "-q", str(workspace)], check=True, capture_output=True)
    return workspace


def _strip_opencode_chrome(raw: str) -> str:
    lines = ANSI_ESCAPE.sub("", raw).splitlines()
    result = []
    skip_until_blank = False
    for line in lines:
        s = line.strip()
        if s.startswith("> build"):
            continue
        if re.match(r"^[→✱∷⊕●•]\s", s):
            continue
        if s.startswith("$ "):
            skip_until_blank = True
            continue
        if skip_until_blank:
            if s == "":
                skip_until_blank = False
            continue
        result.append(line)
    return "\n".join(result).strip()


def execute_opencode(cfg: ExecutorConfig, prompt: str, workspace: Path) -> str:
    result = subprocess.run(
        ["opencode", "run", "--dir", str(workspace), "-m", cfg.model, prompt],
        capture_output=True, text=True, timeout=REQUEST_TIMEOUT,
    )
    return _strip_opencode_chrome(result.stdout + result.stderr)


# ---------------------------------------------------------------------------
# Executor: openai_compat (HTTP)
# ---------------------------------------------------------------------------

def execute_openai_compat(cfg: ExecutorConfig, user_prompt: str,
                          system_prompt: str = "", retries: int = 3) -> str:
    _need_requests()
    base = cfg.base_url.rstrip("/")
    url = f"{base}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {cfg.resolved_key()}",
        "Content-Type": "application/json",
    }
    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})
    payload = {
        "model": cfg.model,
        "messages": messages,
        "temperature": cfg.temperature,
        "max_tokens": 4096,
    }
    for attempt in range(retries + 1):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 429 and attempt < retries:
                wait = RETRY_DELAY * (2 ** attempt)
                print(f"\n  [rate-limit] retry in {wait}s…", end="", flush=True)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return content or ""
        except requests.RequestException:
            if attempt == retries:
                raise
            time.sleep(RETRY_DELAY)
    return ""


# ---------------------------------------------------------------------------
# Executor: local (custom schema)
# ---------------------------------------------------------------------------

def execute_local(cfg: ExecutorConfig, prompt: str, skill_body: str, mode: str) -> str:
    _need_requests()
    base = cfg.base_url.rstrip("/")
    url = f"{base}/api/v1/chat"
    payload: dict = {
        "model": cfg.model,
        "system_prompt": skill_body if mode == "with" else "",
        "input": prompt,
    }
    if cfg.temperature != 0.2:  # only include if non-default to be safe
        payload["temperature"] = cfg.temperature
    else:
        payload["temperature"] = cfg.temperature

    resp = requests.post(url, headers={"Content-Type": "application/json"},
                         json=payload, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    for item in data.get("output", []):
        if item.get("type") == "message":
            return item.get("content", "")
    return ""


# ---------------------------------------------------------------------------
# Executor: session (claude -p subprocess)
# ---------------------------------------------------------------------------

def execute_session(cfg: ExecutorConfig, full_prompt: str) -> str:
    cmd = ["claude", "-p"]
    if cfg.model:
        cmd += ["--model", cfg.model]
    cmd.append(full_prompt)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=REQUEST_TIMEOUT)
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# Executor: agy (Gemini CLI print mode) — like session, different binary.
# Skill body is injected into the prompt (no symlink skill-loading for agy).
# ---------------------------------------------------------------------------

def execute_agy(cfg: ExecutorConfig, full_prompt: str) -> str:
    cmd = ["agy", "-p", "--dangerously-skip-permissions"]
    if cfg.model:
        cmd += ["--model", cfg.model]
    cmd.append(full_prompt)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=REQUEST_TIMEOUT)
    return ANSI_ESCAPE.sub("", result.stdout).strip()


# ---------------------------------------------------------------------------
# Judge: session (claude -p)
# ---------------------------------------------------------------------------

def _judge_session(assertion_text: str, response: str) -> tuple[bool, str]:
    prompt = (
        f"You are grading an AI model's output against an assertion.\n\n"
        f"ASSERTION:\n{assertion_text}\n\n"
        f"MODEL OUTPUT:\n{response}\n\n"
        f"Does the output satisfy the assertion? "
        f"Reply with exactly one word: PASS or FAIL, then optionally a brief reason."
    )
    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True, text=True, timeout=60,
        )
        out = result.stdout.strip()
        passed = out.upper().startswith("PASS")
        return passed, "" if passed else out
    except Exception as e:
        return False, f"session judge error: {e}"


# ---------------------------------------------------------------------------
# Judge: openai_compat LLM
# ---------------------------------------------------------------------------

def _judge_openai_compat(cfg: JudgeConfig, assertion_text: str, response: str) -> tuple[bool, str]:
    _need_requests()
    prompt = (
        f"You are grading an AI model's output against an assertion.\n\n"
        f"ASSERTION:\n{assertion_text}\n\n"
        f"MODEL OUTPUT:\n{response}\n\n"
        f"Does the output satisfy the assertion? "
        f"Reply with exactly one word: PASS or FAIL, then optionally a brief reason."
    )
    try:
        base = cfg.base_url.rstrip("/")
        url = f"{base}/v1/chat/completions"
        headers = {"Authorization": f"Bearer {cfg.resolved_key()}", "Content-Type": "application/json"}
        payload = {"model": cfg.model, "messages": [{"role": "user", "content": prompt}], "temperature": 0}
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        out = resp.json()["choices"][0]["message"]["content"].strip()
        passed = out.upper().startswith("PASS")
        return passed, "" if passed else out
    except Exception as e:
        return False, f"judge error: {e}"


# ---------------------------------------------------------------------------
# Judge: batched (groups assertions from same eval into one call)
# ---------------------------------------------------------------------------

def _build_batch_prompt(assertions: list[dict], response: str) -> str:
    lines = ["You are grading an AI model's output against multiple assertions.", ""]
    lines.append("ASSERTIONS:")
    for a in assertions:
        lines.append(f"[{a['id']}] {a['text']}")
    lines.append("")
    lines.append(f"MODEL OUTPUT:\n{response}")
    lines.append("")
    lines.append("For each assertion, reply on its own line with the format:")
    lines.append("[ID] PASS or FAIL — brief reason")
    return "\n".join(lines)


def _parse_batch_response(out: str, assertions: list[dict]) -> dict[str, tuple[bool, str]]:
    results: dict[str, tuple[bool, str]] = {}
    for a in assertions:
        aid = a["id"]
        pattern = re.compile(rf"\[{re.escape(aid)}\]\s*(PASS|FAIL)\b(.*)", re.IGNORECASE)
        m = pattern.search(out)
        if m:
            passed = m.group(1).upper() == "PASS"
            note = m.group(2).strip().lstrip("—-– ").strip()
            results[aid] = (passed, "" if passed else note)
        else:
            results[aid] = (False, "batch judge: no verdict found")
    return results


def _judge_session_batch(assertions: list[dict], response: str) -> dict[str, tuple[bool, str]]:
    prompt = _build_batch_prompt(assertions, response)
    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True, text=True, timeout=60,
        )
        return _parse_batch_response(result.stdout.strip(), assertions)
    except Exception as e:
        return {a["id"]: (False, f"session judge error: {e}") for a in assertions}


def _judge_openai_compat_batch(cfg: JudgeConfig, assertions: list[dict], response: str) -> dict[str, tuple[bool, str]]:
    _need_requests()
    prompt = _build_batch_prompt(assertions, response)
    try:
        base = cfg.base_url.rstrip("/")
        url = f"{base}/v1/chat/completions"
        headers = {"Authorization": f"Bearer {cfg.resolved_key()}", "Content-Type": "application/json"}
        payload = {"model": cfg.model, "messages": [{"role": "user", "content": prompt}], "temperature": 0}
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        out = resp.json()["choices"][0]["message"]["content"].strip()
        return _parse_batch_response(out, assertions)
    except Exception as e:
        return {a["id"]: (False, f"judge error: {e}") for a in assertions}


# ---------------------------------------------------------------------------
# Assertion grader
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Target extraction helpers
# ---------------------------------------------------------------------------

def _extract_commit(text: str) -> str:
    m = re.search(r"```[a-z]*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    m = re.search(r"`([a-z]+(?:\([^)]+\))?!?:.+)`", text)
    if m:
        return m.group(1).strip()
    return text.strip()


def _first_line(text: str) -> str:
    for line in _extract_commit(text).splitlines():
        if line.strip():
            return line.strip()
    return ""


def _scope(fl: str) -> str:
    m = re.match(r"^[a-z]+\(([^)]+)\)", fl)
    return m.group(1) if m else ""


def _footer_text(text: str) -> str:
    commit = _extract_commit(text)
    lines = commit.splitlines()
    for i, line in enumerate(lines):
        if i > 0 and not line.strip():
            return "\n".join(lines[i + 1:])
    return ""


def _get_target(response: str, target: str) -> str:
    if target == "response":
        return response
    if target == "commit":
        return _extract_commit(response)
    fl = _first_line(response)
    if target == "first_line":
        return fl
    if target == "scope":
        return _scope(fl)
    if target == "footer":
        return _footer_text(response)
    return response


# ---------------------------------------------------------------------------
# Generic regex grader (reads patterns from evals.json grading objects)
# ---------------------------------------------------------------------------

def _eval_condition(cond: dict, response: str) -> tuple[bool, str]:
    target_name = cond.get("target", "response")
    pattern = cond.get("pattern", "")
    negate = cond.get("negate", False)
    target = _get_target(response, target_name)
    flags = re.MULTILINE if cond.get("multiline") else 0
    match = bool(re.search(pattern, target, flags))
    if negate:
        return (not match, "" if not match else f"pattern found in {target_name}")
    return (match, "" if match else f"{target_name}: {target[:50]}")


def _grade_regex(assertion: dict, response: str) -> tuple[bool, str]:
    grading = assertion.get("grading", {})
    if "all" in grading:
        for cond in grading["all"]:
            passed, note = _eval_condition(cond, response)
            if not passed:
                return False, note
        return True, ""
    if "any" in grading:
        notes = []
        for cond in grading["any"]:
            passed, note = _eval_condition(cond, response)
            if passed:
                return True, ""
            notes.append(note)
        return False, "; ".join(notes)
    return _eval_condition(grading, response)


def grade_assertion(assertion: dict, response: str, judge: JudgeConfig) -> tuple[bool, str]:
    grading = assertion.get("grading", {})
    method = grading.get("method", "")
    if not method:
        method = "llm" if assertion["text"].startswith("[LLM-judge]") else "regex"
    if method == "llm":
        # LLM path is handled by batch grading in caller; this is regex fallback
        fallback = grading.get("regex_fallback")
        if fallback:
            return _eval_condition(fallback, response)
        return False, "no judge configured and no regex_fallback"
    return _grade_regex(assertion, response)


# ---------------------------------------------------------------------------
# Results persistence
# ---------------------------------------------------------------------------

def _results_path(skill_name: str) -> Path:
    path = Path(".bench") / skill_name / "results.ndjson"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def save_result(skill_name: str, record: dict) -> None:
    path = _results_path(skill_name)
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")


def load_results(skill_name: str) -> list[dict]:
    path = _results_path(skill_name)
    if not path.exists():
        return []
    records = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return records


# ---------------------------------------------------------------------------
# Run orchestration
# ---------------------------------------------------------------------------

def run_one_eval(
    eval_case: dict,
    mode: str,
    executor: ExecutorConfig,
    judge: JudgeConfig,
    skill_body: str,
    workspace: Path | None,
    verbose: bool,
    delay: float,
) -> dict:
    if delay:
        time.sleep(delay)

    prompt = eval_case["prompt"]
    skill_context = eval_case.get("skill_context", "")

    print(f"  [{mode:7s}] eval {eval_case['id']:2d} · {eval_case['name']}", end="", flush=True)
    start = time.monotonic()

    try:
        if executor.type == "opencode":
            response = execute_opencode(executor, prompt, workspace)
        elif executor.type == "openai_compat":
            sys_prompt = ""
            user_prompt = prompt
            if mode == "with":
                sys_prompt = skill_body
                if skill_context:
                    label = eval_case.get("context_label", "Supplementary context")
                    user_prompt = (
                        f"--- {label} ---\n"
                        f"{skill_context}\n"
                        f"--- END ---\n\n{prompt}"
                    )
            response = execute_openai_compat(executor, user_prompt, sys_prompt)
        elif executor.type == "local":
            response = execute_local(executor, prompt, skill_body, mode)
        elif executor.type == "session":
            ctx_label = eval_case.get("context_label", "")
            full_prompt = build_injected_prompt(prompt, skill_body, mode, skill_context, ctx_label)
            response = execute_session(executor, full_prompt)
        elif executor.type == "agy":
            ctx_label = eval_case.get("context_label", "")
            full_prompt = build_injected_prompt(prompt, skill_body, mode, skill_context, ctx_label)
            response = execute_agy(executor, full_prompt)
        else:
            raise ValueError(f"Unknown executor type: {executor.type!r}")
    except Exception as e:
        print(f"  ERROR: {e}")
        return {
            "eval_id": eval_case["id"], "name": eval_case["name"], "mode": mode,
            "response": "", "results": [], "passed": 0,
            "total": len(eval_case["assertions"]), "error": str(e),
        }

    elapsed = time.monotonic() - start
    print(f"  ({elapsed:.1f}s)", flush=True)
    if verbose:
        print(f"\n--- response ---\n{response}\n--- end ---\n")

    results = []
    # Batch LLM-judged assertions into one judge call per eval
    llm_assertions = [a for a in eval_case["assertions"]
                      if a.get("grading", {}).get("method") == "llm"
                      or (not a.get("grading") and a["text"].startswith("[LLM-judge]"))]
    batch_verdicts: dict[str, tuple[bool, str]] = {}
    if llm_assertions and judge.type in ("session", "openai_compat"):
        if judge.type == "session":
            batch_verdicts = _judge_session_batch(llm_assertions, response)
        else:
            batch_verdicts = _judge_openai_compat_batch(judge, llm_assertions, response)

    for assertion in eval_case["assertions"]:
        aid = assertion["id"]
        if aid in batch_verdicts:
            passed, note = batch_verdicts[aid]
        else:
            passed, note = grade_assertion(assertion, response, judge)
        results.append({"id": aid, "text": assertion["text"], "passed": passed, "note": note})

    return {
        "eval_id": eval_case["id"], "name": eval_case["name"], "mode": mode,
        "response": response, "results": results,
        "passed": sum(1 for r in results if r["passed"]),
        "total": len(results), "elapsed_s": round(elapsed, 2),
    }


def run_benchmark(
    skill_dir: Path,
    skill_body: str,
    evals: list[dict],
    run_cfg: RunConfig,
    verbose: bool,
    delay: float,
) -> tuple[list[dict], dict]:
    """Execute one RunConfig (one label/model). Returns (all_runs, summary_record)."""
    skill_name = skill_dir.name
    modes = ["with", "without"] if run_cfg.mode == "both" else [run_cfg.mode]
    workspace = None
    executor = run_cfg.executor

    # Opencode: manage workspace + symlink
    symlink_originally_existed = False
    newly_created = False
    if executor.type == "opencode":
        workspace = _ensure_workspace(skill_name)
        symlink_originally_existed = _skill_symlink(skill_name).exists()

    all_runs: list[dict] = []
    try:
        for mode in modes:
            if executor.type == "opencode":
                if mode == "with":
                    newly_created = _ensure_skill_linked(skill_dir)
                else:
                    _remove_skill_link(skill_name)

            print(f"Running [{mode}] …")
            for eval_case in evals:
                result = run_one_eval(
                    eval_case=eval_case,
                    mode=mode,
                    executor=executor,
                    judge=run_cfg.judge,
                    skill_body=skill_body,
                    workspace=workspace,
                    verbose=verbose,
                    delay=delay,
                )
                all_runs.append(result)
    finally:
        if executor.type == "opencode":
            current = _skill_symlink(skill_name).exists()
            if symlink_originally_existed and not current:
                _ensure_skill_linked(skill_dir)
            elif not symlink_originally_existed and current and newly_created:
                _remove_skill_link(skill_name)

    # Build summary record
    by_mode: dict[str, list[dict]] = {}
    for r in all_runs:
        by_mode.setdefault(r["mode"], []).append(r)

    def pct(runs): return 100 * sum(r["passed"] for r in runs) / sum(r["total"] for r in runs) if runs else 0.0

    record: dict = {
        "timestamp": datetime.now(UTC).isoformat(),
        "skill": skill_name,
        "skill_version": "",   # filled by caller
        "label": run_cfg.label,
        "executor": dataclasses.asdict(executor),
        "judge": dataclasses.asdict(run_cfg.judge),
        "mode": run_cfg.mode,
    }
    if "with" in by_mode and "without" in by_mode:
        pw, pwo = pct(by_mode["with"]), pct(by_mode["without"])
        n = sum(r["total"] for r in by_mode["with"])
        record.update({"n": n, "pct_with": round(pw, 1), "pct_without": round(pwo, 1), "delta_pp": round(pw - pwo, 1)})
    elif "with" in by_mode:
        record.update({"n": sum(r["total"] for r in by_mode["with"]), "pct_with": round(pct(by_mode["with"]), 1)})
    else:
        record.update({"n": sum(r["total"] for r in by_mode.get("without",[])), "pct_without": round(pct(by_mode.get("without",[])), 1)})

    record["runs"] = all_runs
    return all_runs, record


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

PASS_ICON = "\033[32m✓\033[0m"
FAIL_ICON = "\033[31m✗\033[0m"


def print_run_summary(all_runs: list[dict], label: str) -> None:
    by_mode: dict[str, list[dict]] = {}
    for run in all_runs:
        by_mode.setdefault(run["mode"], []).append(run)

    print(f"\n{'='*70}")
    print(f"Label: {label}")
    print(f"{'='*70}\n")

    if "with" in by_mode and "without" in by_mode:
        with_r = {r["eval_id"]: r for r in by_mode["with"]}
        without_r = {r["eval_id"]: r for r in by_mode["without"]}
        ids = sorted(set(with_r) | set(without_r))
        hdr = f"{'Eval':<40} {'WITH':>6} {'WITHOUT':>9} {'Δ':>5}"
        print(hdr); print("-" * len(hdr))
        tw = two = ta = 0
        for eid in ids:
            w, wo = with_r.get(eid, {}), without_r.get(eid, {})
            wp, wt = w.get("passed", 0), w.get("total", 0)
            wop, wot = wo.get("passed", 0), wo.get("total", 0)
            d = wp - wop
            print(f"  {eid:2d}. {(w.get('name') or wo.get('name') or str(eid))[:35]:<35} {wp}/{wt}   {wop}/{wot}   {'+'+str(d) if d>0 else str(d):>3}")
            tw += wp; two += wop; ta += wt
        print("-" * len(hdr))
        pw, pwo = 100*tw/ta, 100*two/ta
        print(f"  {'TOTAL':<38} {tw}/{ta}  {two}/{ta}  {pw-pwo:+.0f}pp")
        print(f"\n  WITH:    {tw}/{ta} ({pw:.0f}%)")
        print(f"  WITHOUT: {two}/{ta} ({pwo:.0f}%)")
        print(f"  Delta:   {pw-pwo:+.0f}pp  ({pw/pwo:.2f}×)" if pwo else f"  Delta:   +{pw:.0f}pp  (∞×)")
    else:
        mode = next(iter(by_mode))
        runs = by_mode[mode]
        tp = sum(r["passed"] for r in runs); tt = sum(r["total"] for r in runs)
        print(f"Mode: {mode}")
        for run in runs:
            print(f"  {run['eval_id']:2d}. {run['name'][:45]:<45} {run['passed']}/{run['total']}")
            for res in run.get("results", []):
                if not res["passed"]:
                    print(f"       {FAIL_ICON} {res['id']}: {res['note'] or res['text'][:60]}")
        print(f"\n  TOTAL: {tp}/{tt} ({100*tp/tt:.0f}%)" if tt else "")
    print()


def print_detail(all_runs: list[dict]) -> None:
    for run in all_runs:
        if run.get("error"):
            continue
        print(f"\n  Eval {run['eval_id']} [{run['mode']}] · {run['name']} — {run['passed']}/{run['total']}")
        for res in run["results"]:
            note = f"  ({res['note']})" if res["note"] else ""
            print(f"    {PASS_ICON if res['passed'] else FAIL_ICON} {res['id']}: {res['text'][:65]}{note}")


def print_report(skill_name: str) -> None:
    records = load_results(skill_name)
    if not records:
        print(f"No results found in .bench/{skill_name}/results.ndjson")
        return

    # Latest run per label
    seen: dict[str, dict] = {}
    for r in records:
        seen[r["label"]] = r  # last write wins

    print(f"\n{'='*90}")
    print(f"Benchmark results: {skill_name}")
    print(f"{'='*90}")
    hdr = f"{'Label':<28} {'Version':<9} {'Date':<12} {'N':>4} {'With':>6} {'W/out':>6} {'Δ':>6} {'Judge'}"
    print(hdr); print("-" * len(hdr))
    for label, r in seen.items():
        date = r.get("timestamp", "")[:10]
        ver = r.get("skill_version", "?")
        n = r.get("n", "?")
        pw = f"{r['pct_with']:.0f}%" if "pct_with" in r else "—"
        pwo = f"{r['pct_without']:.0f}%" if "pct_without" in r else "—"
        delta = f"{r['delta_pp']:+.0f}pp" if "delta_pp" in r else "—"
        judge = r.get("judge", {}).get("type", "none")
        print(f"  {label[:26]:<26} {ver:<9} {date:<12} {str(n):>4} {pw:>6} {pwo:>6} {delta:>6}  {judge}")
    print()


def to_evaluations_md_row(record: dict) -> str:
    label = record.get("label", "?")
    ver = record.get("skill_version", "?")
    n = record.get("n", "?")
    pw = f"{record['pct_with']:.0f}%" if "pct_with" in record else "—"
    pwo = f"{record['pct_without']:.0f}%" if "pct_without" in record else "—"
    delta = f"{record['delta_pp']:+.0f}pp" if "delta_pp" in record else "—"
    uplift = ""
    if "pct_with" in record and "pct_without" in record and record["pct_without"]:
        uplift = f"{record['pct_with']/record['pct_without']:.2f}×"
    skill = record.get("skill", "?")
    return f"| `{skill}` | {label} | {ver} | {n} | {pw} | {pwo} | {delta} | {uplift} |"


# ---------------------------------------------------------------------------
# Config scaffold
# ---------------------------------------------------------------------------

SAMPLE_CONFIG = """\
{
  "skill": "skills/git-conventional-commits",
  "skill_version": "v1.0.0",
  "mode": "both",
  "evals": [],
  "delay": 3,
  "runs": [
    {
      "label": "minimax-zen",
      "executor": {
        "type": "opencode",
        "model": "opencode/minimax-m2.5-free"
      },
      "judge": { "type": "none" }
    },
    {
      "label": "qwen3-local",
      "executor": {
        "type": "local",
        "model": "qwen3-coder-30b-a3b-instruct",
        "base_url": "http://100.84.126.41:1453",
        "temperature": 0.2
      },
      "judge": { "type": "session" }
    },
    {
      "label": "haiku-session",
      "executor": {
        "type": "session",
        "model": "claude-haiku-4-5-20251001"
      },
      "judge": { "type": "none" }
    },
    {
      "label": "nemotron-openrouter",
      "executor": {
        "type": "openai_compat",
        "model": "nvidia/llama-3.1-nemotron-70b-instruct",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "temperature": 0.2
      },
      "judge": {
        "type": "openai_compat",
        "model": "nvidia/llama-3.1-nemotron-70b-instruct",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY"
      }
    }
  ]
}
"""


def scaffold_config(skill_name: str) -> Path:
    config_dir = Path(".bench") / skill_name
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "bench.json"
    if config_path.exists():
        print(f"Config already exists: {config_path}")
        return config_path
    sample = json.loads(SAMPLE_CONFIG)
    sample["skill"] = f"skills/{skill_name}"
    config_path.write_text(json.dumps(sample, indent=2))
    print(f"Created config scaffold: {config_path}")
    print("Edit it to configure your benchmark runs, then rerun without --init-config.")
    return config_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Unified skill benchmark runner.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--config", default="", help="Path to bench.json config file")
    p.add_argument("--skill", default="skills/git-conventional-commits",
                   help="Skill directory (used when no --config, or for --report/--init-config)")
    p.add_argument("--report", action="store_true", help="Print merged results table and exit")
    p.add_argument("--init-config", action="store_true", help="Scaffold a bench.json and exit")

    # Quick single-run flags (override config)
    p.add_argument("--executor", default="", help="Executor type: opencode|openai_compat|local|session")
    p.add_argument("--model", default="", help="Model ID for executor")
    p.add_argument("--base-url", default="", help="Base URL for openai_compat or local executor")
    p.add_argument("--api-key", default="", help="API key (overrides api_key_env)")
    p.add_argument("--api-key-env", default="", help="Env var name for API key")
    p.add_argument("--judge", default="", help="Judge type: none|session|openai_compat")
    p.add_argument("--mode", default="both", choices=["with","without","both"])
    p.add_argument("--evals", default="", help="Comma-separated eval IDs, e.g. 1,3,9")
    p.add_argument("--delay", type=float, default=-1)
    p.add_argument("--skill-version", default="v1.0.0")

    p.add_argument("--detail", action="store_true", help="Print per-assertion detail")
    p.add_argument("--verbose", action="store_true", help="Print full model responses")
    p.add_argument("--output", default="", help="Save full results JSON to file")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    skill_dir = Path(args.skill)

    if args.report:
        print_report(skill_dir.name)
        return

    if args.init_config:
        scaffold_config(skill_dir.name)
        return

    # Build config: from file, or from CLI flags, or scaffold prompt
    if args.config:
        cfg = load_config(Path(args.config))
        skill_dir = Path(cfg.skill)
    elif args.executor:
        exec_cfg = ExecutorConfig(
            type=args.executor, model=args.model, base_url=args.base_url,
            api_key=args.api_key, api_key_env=args.api_key_env,
        )
        judge_cfg = JudgeConfig(type=args.judge or "none")
        label = f"{args.model or args.executor}"
        cfg = BenchConfig(
            skill=args.skill,
            skill_version=args.skill_version,
            evals=[int(x) for x in args.evals.split(",") if x] if args.evals else [],
            delay=args.delay if args.delay >= 0 else 3.0,
            runs=[RunConfig(label=label, executor=exec_cfg, judge=judge_cfg, mode=args.mode)],
        )
    else:
        # Try auto-loading config from .bench/<skill>/bench.json
        auto = Path(".bench") / skill_dir.name / "bench.json"
        if auto.exists():
            print(f"Using config: {auto}")
            cfg = load_config(auto)
            skill_dir = Path(cfg.skill)
        else:
            print("No config found. Run with --init-config to scaffold one:")
            print(f"  python3 scripts/benchmark.py --skill {args.skill} --init-config")
            sys.exit(1)

    if not skill_dir.exists():
        sys.exit(f"ERROR: skill directory not found: {skill_dir}")

    skill_body = load_skill_body(skill_dir)
    evals = load_evals(skill_dir)

    # Apply eval filter (config level, then CLI level)
    wanted_ids = set(cfg.evals) or set()
    if args.evals:
        wanted_ids = {int(x) for x in args.evals.split(",") if x}
    if wanted_ids:
        evals = [e for e in evals if e["id"] in wanted_ids]
        if not evals:
            sys.exit(f"ERROR: no evals match IDs {wanted_ids}")

    delay = args.delay if args.delay >= 0 else cfg.delay

    print(f"\nSkill:  {skill_dir.name} ({cfg.skill_version})")
    print(f"Evals:  {len(evals)} cases")
    print(f"Runs:   {len(cfg.runs)}\n")

    all_records = []
    for run_cfg in cfg.runs:
        model_display = run_cfg.executor.model or run_cfg.executor.type
        print(f"── {run_cfg.label}  [{model_display}]  judge={run_cfg.judge.type}")
        all_runs, record = run_benchmark(
            skill_dir=skill_dir, skill_body=skill_body, evals=evals,
            run_cfg=run_cfg, verbose=args.verbose, delay=delay,
        )
        record["skill_version"] = cfg.skill_version
        save_result(skill_dir.name, record)
        all_records.append(record)
        print_run_summary(all_runs, run_cfg.label)
        if args.detail:
            print_detail(all_runs)
        print("  EVALUATIONS.md row:")
        print(f"  {to_evaluations_md_row(record)}\n")

    if args.output:
        Path(args.output).write_text(json.dumps(all_records, indent=2))
        print(f"Results saved to {args.output}")


if __name__ == "__main__":
    main()
