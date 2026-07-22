# OKF v0.1 cheatsheet

The full normative text is `SPEC.md`. This is the fast reference for authoring.
When something here is ambiguous, `SPEC.md` wins.

## The whole format in one breath

A **bundle** is a directory tree of markdown files. Each `.md` file (except the
reserved `index.md` and `log.md`) is a **concept**. A concept's **ID** is its
path within the bundle minus `.md` (`specs/stack.md` → `specs/stack`). A concept
is YAML **frontmatter** + a markdown **body**. Concepts link to each other with
ordinary markdown links.

## Frontmatter (SPEC §4.1)

```yaml
---
type: <Type>                 # REQUIRED — the only hard field. See type-vocabulary.md
title: <Display name>        # recommended
description: <One sentence>   # recommended — feeds index.md, previews, search
resource: <canonical URI>    # only if the concept describes a real addressable asset
tags: [<tag>, <tag>]         # optional
timestamp: 2026-07-16T00:00:00Z   # optional ISO 8601 last-meaningful-change
# any extra producer-defined keys are allowed
---
```

- `type` is the one required field, and it must be non-empty. Everything else is
  soft — consumers must not reject a doc for missing optional fields (SPEC §9).
- Include `resource` only when the concept *is about* a specific addressable thing
  (a table, an endpoint, a container). Abstract concepts (a metric, a playbook)
  omit it.
- Preserve unknown keys when you edit a doc — don't strip fields you don't
  recognize.

## Body (SPEC §4.2)

Standard markdown. Favor **structure** — headings, tables, lists, fenced code —
over prose, because structure helps both human skimming and agent retrieval.
No section is required. Conventional headings that carry meaning:

| Heading       | Purpose                                         |
|---------------|-------------------------------------------------|
| `# Schema`    | Columns/fields of an asset.                     |
| `# Examples`  | Concrete usage, usually fenced code.            |
| `# Citations` | Numbered external sources (see below).          |

## Cross-links (SPEC §5)

- **Preferred — bundle-absolute:** starts with `/`, resolved from the bundle root.
  Stable when files move within a subdirectory.
  `See the [orders table](/services/langfuse.md).`
- **Relative:** `[neighbor](./other.md)` — fine for same-directory links.
- A link asserts an *untyped relationship*; the *kind* (joins-with, depends-on,
  parent) lives in the surrounding prose, not the link.
- Broken links are legal (SPEC §5.3) — they may be not-yet-written knowledge. Our
  validator flags them as warnings so you notice, not as errors.

## index.md — progressive disclosure (SPEC §6)

One per directory (optional but recommended). **No frontmatter** — except the
bundle-root `index.md`, which may carry only `okf_version`. Body groups entries
under headings, each entry linking to a concept/subdir with its description:

```markdown
# Subdirectories
* [services](services/index.md) - The deployed stack components.

# Concepts
* [Stack Architecture](stack.md) - How Wakapi, LiteLLM, and Langfuse fit together.
```

Generate/refresh these with `scripts/okf_index.py` instead of hand-maintaining.

## log.md — history (SPEC §7)

Optional, at any level. No frontmatter. Date-grouped, newest first, ISO dates:

```markdown
# Update Log

## 2026-07-16
* **Creation**: Added the [stack spec](/specs/stack.md).
* **Update**: Refreshed the root [index](/index.md).
```

The leading bold verb is a convention. Append entries with `scripts/okf_log.py`.

## Citations (SPEC §8)

When the body makes externally-sourced claims, list them numbered under a
trailing `# Citations` heading:

```markdown
# Citations
[1] [LiteLLM passthrough auth](https://docs.litellm.ai/docs/tutorials/claude_code_byok)
[2] [Langfuse data model](https://langfuse.com/docs/observability/data-model)
```

Citations may be external URLs, bundle-relative paths, or `references/<slug>.md`
concepts that mirror external material.

## Conformance (SPEC §9) — what `okf_validate.py` enforces as ERRORS

1. Every non-reserved `.md` has a parseable YAML frontmatter block.
2. Every frontmatter has a non-empty `type`.
3. Reserved files are well-formed: `index.md` has no frontmatter (except root
   `okf_version`); `log.md` date headings are ISO `YYYY-MM-DD`.

Everything else (missing `title`/`description`, unknown `type`, broken links,
missing `index.md`, non-ISO `timestamp`, schemeless `resource`) is a **warning** —
surfaced so you can improve the doc, never a reason to reject a bundle.
