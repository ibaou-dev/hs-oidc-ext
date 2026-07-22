# OKF Type Vocabulary — this repo

OKF does not register `type` values centrally; producers pick descriptive,
self-explanatory strings and consumers tolerate unknown ones (SPEC §4.1). To
keep *our* bundle self-consistent and easy to filter, we standardize on the
set below. `okf_validate.py` warns (never errors) on a type outside this list —
if you have a genuinely new kind of concept, add it here in the same PR rather
than silencing the warning.

Pick the **most specific** type that fits. When two fit, prefer the one a reader
would search for.

| `type`      | Use for                                                        | Home directory   | Key body headings |
|-------------|----------------------------------------------------------------|------------------|-------------------|
| `Spec`      | A specification of a system, format, protocol, or interface.   | `specs/`         | Overview, Requirements, Interfaces |
| `Plan`      | An implementation / project plan with phases and decisions.    | `plans/`         | Goals, Phases, Risks |
| `ADR`       | An Architecture Decision Record (one decision, its context, consequences). | `adr/` | Context, Decision, Consequences |
| `Reference` | Reference material distilled from external sources; the facts we rely on. | `references/` | Summary, Details, Citations |
| `Research`  | A research report / investigation with findings and sources.   | `research/`      | Question, Findings, Citations |
| `Analysis`  | Analysis of data, tradeoffs, or options (comparisons, evaluations). | `analysis/` | Question, Analysis, Recommendation |
| `Runbook`   | Operational procedure for a routine task (deploy, rotate a key, back up). | `runbooks/` | Trigger, Steps, Verification |
| `Playbook`  | Incident/triage response for a specific alert or failure mode. | `playbooks/`     | Trigger, Steps, Escalation |
| `Service`   | A deployed service/component in the stack (Wakapi, LiteLLM, Langfuse, Postgres). | `services/` | Overview, Config, Schema, Dependencies |
| `Component` | A sub-part of a service or a client integration (a VS Code plugin, a header injector). | `components/` | Overview, Config |
| `Metric`    | A tracked metric or KPI (definition, source, formula).         | `metrics/`       | Definition, Source, Formula |
| `Dashboard` | A dashboard/report definition and what it shows.               | `dashboards/`    | Purpose, Panels, Queries |
| `Config`    | A configuration surface (env vars, compose file, a settings block). | `config/`   | Overview, Keys, Example |
| `FeatureRequest` | A proposed feature / change request with problem + proposal. | `feature-requests/` | Problem, Proposed, Notes |
| `Guide`     | A how-to / tutorial that walks a reader through a task end-to-end. | `guides/`     | Goal, Steps |
| `Index`     | Reserved-ish: only for a hand-authored landing concept if ever needed (normally use `index.md`). | — | — |

## Choosing between close types

- **Spec vs Plan** — a Spec says *what the thing is / must do*; a Plan says *how
  and when we'll build it*. The stack architecture is a Spec; "how we'll roll out
  the stack over three sprints" is a Plan.
- **Reference vs Research** — Research captures an *investigation* (a question we
  asked, what we found, sources). Reference is the *settled, reusable distillation*
  we cite going forward. Research often gets mined into References.
- **Runbook vs Playbook** — Runbook = planned, routine ("rotate the master key").
  Playbook = reactive, triggered by an alert/incident ("freshness alert fired").
- **Service vs Component** — Service = a top-level box in the compose file.
  Component = a client integration or a piece inside a service.

## Home directories are conventions, not rules

The directory a concept lives in is independent of its `type` (SPEC §3) — the
table's "Home directory" column is our default so the bundle stays navigable.
Deviate when a different grouping tells the reader more (e.g. grouping all
Langfuse concepts under `services/langfuse/`).
