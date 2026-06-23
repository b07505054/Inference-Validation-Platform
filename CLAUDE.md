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
- Runtime artifact validation reports for runtime decisions, in-flight scheduling, serving-framework comparisons, vLLM/SGLang trace adapters, cold start, page prefetch, distributed serving, load balancing, fault tolerance, gRPC contract coverage, GPU PGO-like evidence, technology gates, and statistical validation where sample-backed data is available.

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

Existing focused tests:

- `tests/test_statistics.py`
- `tests/test_control_plane_metrics.py`
- `tests/test_validate_runtime_artifacts_statistics.py`

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

When optional source artifacts are present, runtime artifact validation may emit:

- `runtime_decision_validation_report.json`
- `inflight_scheduler_validation_report.json`
- `serving_framework_validation_report.json`
- `vllm_trace_adapter_validation_report.json`
- `sglang_trace_adapter_validation_report.json`
- `cold_start_validation_report.json`
- `page_prefetch_validation_report.json`
- `distributed_serving_validation_report.json`
- `load_balancing_validation_report.json`
- `fault_tolerance_validation_report.json`
- `grpc_contract_validation_report.json`
- `gpu_pgo_like_validation_report.json`
- `technology_gate_validation_report.json`
- `statistical_validation_report.json`

## Handoff Assumptions

- This project is local/demo oriented, not production deployed.
- Sibling repositories may be expected at `../heterogeneous-inference-runtime` and `../ml-graph-compiler-runtime`.
- Checked-in reports are examples or generated artifacts and may be stale.
- Control-plane metrics describe IVP state, not live inference serving performance.
- Any estimated metrics must be labeled estimated.

## Portfolio-Level Policy

When this repository is maintained inside the `systems-portfolio` wrapper, follow the root `CLAUDE.md` for shared documentation hierarchy, benchmark honesty, and Git authorship rules. Keep this file focused on repository-specific capabilities, truth boundaries, and validation commands.
