# CLAUDE.md

## Project Handoff Notes

This repository is an Inference Validation Platform. It schedules compiler/runtime inference artifacts onto registered workers, validates correctness and latency budgets, tracks worker health, quarantines failed devices, retries on alternate workers, and writes JSON/Markdown reports. It also contains scripts that validate runtime artifact directories produced by sibling systems such as `heterogeneous-inference-runtime`.

Read these docs first:

- `docs/architecture.md`
- `docs/data_flow.md`
- `docs/design_decisions.md`
- `docs/technical_debt.md`
- `docs/future_work.md`

## Runtime and Style

- Use Python 3.11.
- Prefer dataclasses for simple internal data structures.
- Use Pydantic where API or serialized artifact contracts already use it.
- Avoid unnecessary classes.
- Keep functions under 100 lines when practical.
- Use type hints.
- Prefer simple modular design.
- Avoid over-engineering.
- Prefer composition over inheritance.
- Avoid giant classes.
- Write tests for non-trivial logic.
- Run tests after changes.
- Explain changes after implementation.

## Development Rules

- Do not treat mock/demo latency values as benchmark numbers.
- Clearly label simulated, estimated, aggregate-only, and sample-backed metrics.
- Clearly distinguish implemented components from simulations in docs and reports.
- Avoid changing generated reports unless the task is specifically to regenerate artifacts.
- Avoid changing source code while doing documentation-only tasks.

## Current Architecture Summary

Core package:

- `src/ivp/models.py`: Pydantic contracts for artifacts, devices, heartbeats, validation results, events, and reports.
- `src/ivp/inventory.py`: in-memory device state and health transitions.
- `src/ivp/heartbeat.py`: heartbeat receive/miss wrapper.
- `src/ivp/scheduler.py`: health-aware scheduler using backend, labels, resource capacity, queue depth, preferred devices, and latency history.
- `src/ivp/worker.py`: `MockWorker` and `ExternalRuntimeWorker`.
- `src/ivp/validation.py`: synchronous schedule/run/retry/quarantine pipeline.
- `src/ivp/event_log.py`: in-memory and optionally persisted event timeline.
- `src/ivp/report.py`: JSON and Markdown control-plane reports.
- `src/ivp/store.py`: SQLite persistence.
- `src/ivp/api.py`: FastAPI control plane.
- `src/ivp/metrics.py`: Prometheus text metrics.
- `src/ivp/statistics.py`: percentile, bootstrap CI, Mann-Whitney, and regression gate helpers.

Scripts:

- `scripts/run_demo.py`: simulated control-plane demo.
- `scripts/run_external_runtime_validation.py`: external runtime summary/live benchmark validation wrapper.
- `scripts/validate_runtime_artifacts.py`: large runtime artifact validation CLI.
- `scripts/generate_llm_demo_artifacts.py`: writes fixed/demo LLM validation artifacts.

## Implemented vs Simulated Boundaries

Implemented:

- API endpoints, SQLite persistence, Prometheus control-plane metrics, scheduler filtering/ranking, retry/quarantine flow, report writing, external runtime summary ingestion, and runtime artifact report generation.

Simulated/demo-only:

- `MockWorker` execution and correctness.
- Random mock latency values.
- Fixed LLM demo values in `src/ivp/llm_reports.py`.
- Heartbeat timing unless explicitly driven by scripts/API calls.
- Priority/preemption behavior in scheduling constraints.

## Known High-Value Fixes

- Fix `scripts/validate_runtime_artifacts.py` so the statistical regression override does not reference `validation_report` or `slo_report` before those dictionaries exist.
- Add scheduler and validation pipeline tests.
- Add external runtime worker tests.
- Split the large runtime validator script into smaller modules.
- Add explicit evidence/metric source labels to reports.

## Common Commands

Set up the project-local virtualenv (one-time):

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Run tests:

```bash
.venv/bin/python -m pytest
```

Run the same checks CI runs (used by `.github/workflows/ci.yml` and optionally by a Claude Code post-edit hook):

```bash
bash scripts/check.sh
```

`scripts/check.sh` strictly requires `.venv/bin/python`. It does not fall back
to `python3`/system Python and does not install or upgrade packages. If
`.venv` or its dependencies are missing, it stops with an error rather than
silently using a different interpreter. CI creates and populates `.venv`
itself on every run.

Run the API:

```bash
uvicorn src.ivp.api:app --reload
```

Run the control-plane demo:

```bash
python3 scripts/run_demo.py
```

Run the retry/quarantine demo:

```bash
python3 scripts/run_demo.py --artifact configs/retry_artifact.json --prefer-cpu-first
```

Run external runtime summary validation:

```bash
python3 scripts/run_external_runtime_validation.py \
  --artifact configs/external_runtime_summary_artifact.json \
  --job-id external-runtime-job-001 \
  --output-prefix reports/external-runtime-job-001
```

Run runtime artifact validation:

```bash
python3 scripts/validate_runtime_artifacts.py \
  --runtime-artifact-dir ../heterogeneous-inference-runtime/results/llm_runtime_artifacts \
  --output-dir reports/runtime_artifact_validation
```

## Handoff Assumptions

- This project is local/demo oriented, not production deployed.
- Sibling repositories may be expected at `../heterogeneous-inference-runtime` and `../ml-graph-compiler-runtime`.
- Checked-in reports are examples or generated artifacts and may be stale.
- Control-plane metrics describe IVP state, not live inference serving performance.
- Any estimated metrics must be labeled estimated.

## Documentation Hierarchy

Truth must flow in the following order:

Code
↓
Artifacts
↓
README.md
↓
CLAUDE.md
↓
docs/

Lower levels must never contradict higher levels.

Documentation must describe reality rather than invent behavior.

If uncertainty exists, trust code and generated artifacts.

Never exaggerate capabilities.

Never claim production behavior unless code and artifacts support it.

## README Contract

README.md exists to answer:

1. What is it?
2. Why is it interesting?
3. How do I run it?
4. What results does it produce?

README should emphasize user-facing understanding.

Avoid implementation details unless necessary.

Avoid maintenance instructions.

## CLAUDE.md Contract

CLAUDE.md exists to answer:

1. How do I maintain it?
2. What commands are canonical?
3. Which components are implemented?
4. Which components are simulated?
5. Which validation commands must pass?
6. What files should not be changed casually?

CLAUDE.md is intended for maintainers and future AI agents.

## docs/ Contract

docs/ exists to answer:

1. Why is it designed this way?
2. What tradeoffs were made?
3. What is measured versus modeled?
4. What assumptions exist?
5. What limitations remain?
6. What future work is possible?

docs/ explains architecture and rationale rather than usage.

## Documentation Principles

Code > Artifacts > README > CLAUDE.md > docs/

Never reverse this order.

Never infer unsupported features.

Never create claims unsupported by code or artifacts.

Prefer conservative wording.

Call synthetic benchmarks synthetic.

Call simulated systems simulated.

Distinguish measured behavior from modeled behavior.

## Git Authorship Policy

The user is the sole maintainer and owner of this repository.

AI agents may modify files as requested.

AI agents must not add AI authorship metadata.

Never add:

* Co-Authored-By entries
* Co-authored-by trailers
* Claude authorship metadata
* AI signatures
* Generated-by-AI footers
* any metadata that makes an AI system appear as a repository contributor

Commit policy:

* By default, do not run git commit.
* If the user explicitly asks in the current conversation to commit, an AI agent may run git add and git commit.
* Commits created by an AI agent must use the user's configured git author and committer identity.
* Commit messages must not mention AI authorship unless the user explicitly asks.
* Before committing, show git status and the staged diff summary when practical.

Push policy:

* By default, do not run git push.
* Only run git push if the user explicitly asks in the current conversation.
* Never force-push unless the user explicitly asks for a force push and the reason is explained.

History policy:

* Do not create branches, rewrite history, rebase, reset, or amend commits unless the user explicitly asks in the current conversation.
* Never rewrite public history without explicit user approval.

Ownership rule:

* The user remains the sole author/maintainer for portfolio presentation purposes.
* No AI system should appear as a repository contributor.
