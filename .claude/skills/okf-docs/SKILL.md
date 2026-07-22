---
name: okf-docs
description: >-
  Author every durable markdown/documentation artifact in this repository as a
  conformant Open Knowledge Format (OKF v0.1) concept in the docs/ bundle —
  markdown files with YAML frontmatter, organized in a directory tree with
  index.md and log.md, cross-linked, and cited. Use this whenever you write,
  update, or restructure any lasting textual artifact here: a spec, plan, README,
  design doc, ADR, research report, analysis, runbook, playbook, reference note,
  or "let's write this down / document this / capture our findings" request —
  even when the user never says "OKF", "frontmatter", or "bundle", and even if
  they just say "write a doc", "make a markdown file", or "add notes". If the
  output is a durable .md file that lives in the repo, it belongs in the bundle
  and this skill governs its shape. Do NOT use it for throwaway scratch, code
  comments, commit messages, or chat-only answers.
user-invocable: false
license: MIT
compatibility:
  Designed for Claude Code or similar AI coding agents. Requires python3 for the
  bundled okf_validate.py / okf_index.py / okf_log.py scripts.
metadata:
  author: ibaou-dev
  version: "0.2.0"
allowed-tools: Read Glob Grep Edit Write Bash(python3:*)
---

# OKF documentation for this repo

Every piece of durable knowledge we produce here — specs, plans, research,
analyses, runbooks, references — lives as an **Open Knowledge Format (OKF)**
concept in the `docs/` bundle. OKF is deliberately tiny: a directory of markdown
files, each with a little YAML frontmatter, cross-linked with ordinary markdown
links. The payoff is that our knowledge is readable with `cat`, diffable in git,
navigable one level at a time, and consumable verbatim by an agent — the same way
we already collaborate on source code.

The whole point of using it consistently is **compounding**: when the last five
docs all have a `type`, a `description`, and bundle-absolute links, the sixth doc
(and any agent reading the repo) can find and trust them. One free-form markdown
file dropped outside the bundle breaks that. So the job of this skill is to make
"write it down" reliably produce a well-formed concept in the right place, with
the index and log kept current.

## Read these when you need them

- `references/okf-cheatsheet.md` — the format on one page. **Read it first** if
  you're not already fluent in OKF; it's short.
- `references/type-vocabulary.md` — the `type` values we use and where each kind
  of concept lives. Consult it when choosing a `type` and a path.
- `references/SPEC.md` — the full normative OKF v0.1 spec. Go here only for edge
  cases the cheatsheet doesn't settle.

## The bundle

The bundle root is `docs/`. Its root `index.md` carries `okf_version: "0.1"` and
nothing else. Concepts are grouped into subdirectories by kind
(`specs/`, `plans/`, `research/`, `references/`, `runbooks/`, `playbooks/`,
`adr/`, `analysis/`, `services/`, …) — see `type-vocabulary.md` for the mapping.
The grouping is a convention for navigability, not a rule: put a concept where a
reader would look for it.

## Authoring workflow

When you're about to produce or change a durable markdown artifact, work through
these steps. Skip the ceremony for genuinely trivial edits (fixing a typo in an
existing concept) — but a *new* artifact always gets frontmatter and a home.

1. **Decide it belongs in the bundle.** Durable and repo-resident → yes. A
   throwaway summary in chat, a code comment, a commit message → no. When unsure,
   lean toward yes: a well-formed concept costs little and compounds.

2. **Pick the `type` and the path.** Choose the most specific `type` from
   `type-vocabulary.md`, then the matching home directory. The filename becomes
   the concept ID — use a short, stable, kebab_or_snake slug (`stack.md`,
   `rotate-litellm-key.md`). Prefer adding to an existing subdirectory over
   inventing a new one.

3. **Write the frontmatter.** Always set `type` (required) plus `title` and
   `description` (a single sentence — it's what shows up in `index.md`, previews,
   and search, so make it carry weight). Add `resource` only when the concept
   describes a specific addressable asset (a container, a table, an endpoint).
   Add `tags` for cross-cutting retrieval and `timestamp` (ISO 8601) for the last
   meaningful change. Starting from a file in `assets/templates/` (e.g.
   `spec.md`, `research.md`, `runbook.md`, `adr.md`, `service.md`, or the generic
   `concept.md`) saves you from a blank page.

4. **Write a structured body with the conventional headings for the type.**
   Favor headings, tables, lists, and fenced code over long prose — structure is
   what makes a concept skimmable by a human and retrievable by an agent. Use the
   section headings the type expects (see **Shape by type** below) rather than
   inventing your own — a runbook with `# Trigger` / `# Steps` / `# Verification`
   is far more useful than the same content under `# Procedure`, because readers
   and tools can rely on the shape. The templates in `assets/templates/` already
   have these headings.

5. **Cross-link every concept you mention, bundle-absolute.** This is the single
   most-skipped step and the one that turns a pile of files into a navigable
   graph — so treat it as required, not optional. When you name another concept
   (a service, a table, a related doc), link it as `[name](/path/to/concept.md)`
   with a leading slash (resolved from the bundle root; it survives file moves).
   Link even concepts that don't exist yet — a broken link is legal in OKF and
   marks knowledge worth writing later. Example: a stack spec should say
   `LiteLLM proxies requests — see [LiteLLM](/services/litellm.md).`, not just
   "LiteLLM proxies requests."

6. **Cite external claims in a numbered `# Citations` block.** Anything sourced
   from outside the repo goes at the bottom under `# Citations`, one numbered
   entry per source in exactly this form:

   ```markdown
   # Citations

   [1] [Langfuse token & cost tracking](https://langfuse.com/docs/observability/features/token-and-cost-tracking)
   [2] [LiteLLM passthrough auth](https://docs.litellm.ai/docs/tutorials/claude_code_byok)
   ```

   Use the `[N]` marker form (not `-` bullets) so citations are unambiguous and
   greppable. If a source is important enough to reuse, mint a
   `references/<slug>.md` concept for it and link that.

7. **Refresh `index.md` and `log.md`.** After adding or moving concepts,
   regenerate the affected indexes and record the change:

   ```bash
   python .claude/skills/okf-docs/scripts/okf_index.py docs/
   python .claude/skills/okf-docs/scripts/okf_log.py docs/log.md \
       --kind Creation --message "Added [<title>](/<concept-id>.md)." --date <YYYY-MM-DD>
   ```

   `okf_index.py` rebuilds every directory listing from frontmatter descriptions,
   so you never hand-maintain them. Pass `--date` explicitly to `okf_log.py` (the
   sandbox can't always read the clock) — use the current date from your context.

8. **Validate before you're done.** Run the conformance checker and clear the
   errors:

   ```bash
   python .claude/skills/okf-docs/scripts/okf_validate.py docs/
   ```

   Errors are hard OKF violations (missing/empty `type`, unparseable frontmatter,
   malformed `index.md`/`log.md`) and must be fixed. Warnings (missing
   `description`, unknown `type`, broken link, no `index.md`) are guidance — fix
   the ones that reflect a real gap; a broken link to a not-yet-written concept is
   an acceptable warning to leave.

## Shape by type

The conventional body headings per type. These are conventions, not hard rules,
but following them is what lets a reader (or a script) know where to look — so use
them unless the content genuinely doesn't fit. Full detail in
`references/type-vocabulary.md`.

| `type`      | Body headings (in order)                                | Cite sources? |
|-------------|---------------------------------------------------------|---------------|
| `Spec`      | `# Overview`, `# Requirements`, `# Interfaces`           | yes           |
| `Plan`      | `# Goals`, `# Phases`, `# Risks`                         | if sourced    |
| `ADR`       | `# Context`, `# Decision`, `# Consequences`              | if sourced    |
| `Reference` | `# Summary`, `# Details`, `# Citations`                  | yes           |
| `Research`  | `# Question`, `# Findings`, `# Citations`                | yes           |
| `Analysis`  | `# Question`, `# Analysis`, `# Recommendation`           | if sourced    |
| `Runbook`   | `# Trigger`, `# Steps`, `# Verification`, `# Rollback`   | rarely        |
| `Playbook`  | `# Trigger`, `# Steps`, `# Escalation`                   | rarely        |
| `Service`   | `# Overview`, `# Config`, `# Dependencies`               | yes           |

## Tools (in `scripts/`)

| Script            | Does                                                            |
|-------------------|----------------------------------------------------------------|
| `okf_validate.py` | Checks §9 conformance (errors) + soft lints (warnings). `--json` for machine output, `--strict` to fail on warnings, `--vocab` to override the type list. Exit 0 = conformant. |
| `okf_index.py`    | (Re)generates `index.md` for every directory from frontmatter. `--check` reports staleness without writing; `--dir` targets one directory. |
| `okf_log.py`      | Appends a dated entry to a `log.md`, newest-first, ISO dates. Pass `--date`, `--kind`, `--message`. |

Run them with the repo root as the working directory so `docs/` resolves.

## What good looks like

A new spec request — "write up how the Wakapi + LiteLLM + Langfuse stack fits
together" — should end as `docs/specs/stack.md` with `type: Spec`, a one-sentence
`description`, a structured body (Overview / Requirements / Interfaces) that links
to `/services/wakapi.md`, `/services/litellm.md`, `/services/langfuse.md`
(broken links are fine if those aren't written yet), a `# Citations` block for the
upstream docs it leans on, an updated `docs/specs/index.md`, a new `docs/log.md`
entry, and a clean `okf_validate.py docs/` run. Not a stray `stack-notes.md` in
the repo root with no frontmatter.

## When not to use this

Don't force OKF onto: code comments, commit messages, PR descriptions, transient
answers that live only in the conversation, generated files a build step owns, or
files whose format is dictated by a tool (a `docker-compose.yml`, a `.env`). The
skill is for the repo's *authored knowledge*, not for every file that happens to
be text.
