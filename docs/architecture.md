# Architecture

## Purpose

Inference Validation Platform is a small Python control plane for validating compiler/runtime inference artifacts. It models the infrastructure layer between compiler/runtime outputs and a heterogeneous worker fleet. The repository supports two related workflows:

- Control-plane validation: register workers, receive heartbeats, schedule an artifact to a healthy worker, run validation, quarantine failed devices, retry on another device, and emit reports.
- Runtime artifact validation: read traces and reports from `heterogeneous-inference-runtime` and convert them into LLM latency, scheduler, KV-cache, backend-placement, SLO, statistical, and serving-framework validation reports.
- Compiler/runtime consistency validation: check that runtime result dictionaries preserve or explicitly document decisions imported from compiler summaries, without treating structural consistency as measured performance.

The project is intentionally demo-scale. Some behavior is implemented as working local code, some behavior is simulated, and some inputs are expected to come from sibling repositories.

## Main Modules

### `src/ivp/models.py`

Defines Pydantic data contracts used by the control plane and reports:

- `ArtifactSpec`: compiler/runtime artifact metadata, required backends, latency budget, correctness requirement, and scheduling constraints.
- `SchedulingConstraints`: required/preferred labels, resource requests, preferred/avoided devices, preemption flag, and priority.
- `Device`: worker identity, backend, health status, queue depth, latency history, firmware/generation metadata, labels, and resource capacity.
- `ValidationResult`: job outcome, selected device/backend, correctness result, latency metrics, budget result, and retry count.
- `Heartbeat`, `PlatformEvent`, and LLM/report models for request timelines, scheduler analysis, KV-cache analysis, and SLO reports.

Implemented behavior: schema validation and serialization through Pydantic.

Simulated behavior: these models do not prove hardware state or correctness by themselves; they encode data reported by workers, scripts, or demo generators.

### `src/ivp/inventory.py`

Owns in-memory device state.

Responsibilities:

- Register devices.
- Filter healthy devices by backend.
- Mark devices busy, healthy, quarantined, or offline.
- Apply heartbeat updates.
- Produce fleet snapshots.

Implemented behavior: device status transitions happen in memory and are used by the scheduler.

Simulated behavior: offline detection is counter-based and only advances when `HeartbeatMonitor.miss()` is called. There is no background heartbeat loop.

### `src/ivp/heartbeat.py`

Thin wrapper over `DeviceInventory`.

Responsibilities:

- Receive heartbeats.
- Mark missed heartbeats.

Implemented behavior: delegates heartbeat state changes to inventory.

Simulated behavior: no network listener, timer, or automatic polling exists in this module.

### `src/ivp/scheduler.py`

Selects a device for an artifact.

Responsibilities:

- Filter candidates by healthy status, backend compatibility, excluded/avoided devices, required labels, and resource capacity.
- Rank candidates by preferred device, preferred-label misses, queue depth, and known or prior backend latency.

Implemented behavior: deterministic sorting over current in-memory candidates.

Simulated or incomplete behavior: `allow_preemption` and `priority` are accepted in the data model but not used in scheduling. Backend prior latencies are static defaults, not measured benchmark data.

### `src/ivp/worker.py`

Provides validation worker implementations.

Responsibilities:

- `MockWorker`: simulate validation for normal `execution_plan` artifacts.
- `ExternalRuntimeWorker`: validate `external_runtime_summary` and `external_runtime_benchmark` artifacts by reading or producing `heterogeneous-inference-runtime` summary data.

Implemented behavior:

- `MockWorker` returns a `ValidationResult`.
- `ExternalRuntimeWorker` reads a backend validation summary or invokes `backend_validation_runner.py`, selects the lowest-latency result, and maps it into a `ValidationResult`.

Simulated behavior:

- `MockWorker` generates latency with random jitter and always sets `correctness_passed=True`.
- Mock latency is not a benchmark number.
- External runtime correctness is currently assumed true when a summary row is selected.

### `src/ivp/validation.py`

Coordinates scheduling, worker execution, retry, quarantine, and event logging.

Responsibilities:

- Select a device for each attempt.
- Mark the device busy.
- Create the appropriate worker.
- Run validation.
- Mark the device healthy on success.
- Quarantine failed devices and retry on another candidate until retries are exhausted.

Implemented behavior: retry/quarantine loop for synchronous validation.

Simulated or incomplete behavior: execution is single-process and synchronous. There is no job queue, cancellation, lease timeout, or distributed worker runtime.

### `src/ivp/event_log.py`

Captures event timeline entries.

Responsibilities:

- Record events with timestamps, job/artifact/device IDs, messages, and details.
- Optionally persist events through a store.
- Return an in-memory snapshot.

Implemented behavior: local event capture and optional SQLite persistence.

### `src/ivp/report.py`

Writes control-plane validation reports.

Responsibilities:

- Emit JSON reports containing artifact, validation result, fleet snapshot, and event timeline.
- Emit Markdown reports for human review.

Implemented behavior: file generation for control-plane validation runs.

### `src/ivp/store.py`

SQLite persistence for API state.

Responsibilities:

- Create tables for devices, jobs, heartbeats, and events.
- Persist device state, heartbeats, jobs, validation results, and events.
- Build a control-plane metrics snapshot.

Implemented behavior: local SQLite storage guarded by a re-entrant lock.

Assumption: this is suitable for local/demo usage, not concurrent multi-process production deployment.

### `src/ivp/api.py` and `src/ivp/api_models.py`

FastAPI control plane.

Endpoints:

- `POST /workers/register`
- `POST /workers/heartbeat`
- `POST /jobs/submit`
- `GET /reports/{job_id}`
- `GET /devices`
- `GET /metrics`

Implemented behavior: request validation, in-memory scheduling state, SQLite persistence, report generation, and Prometheus text metrics.

Important runtime shape: global module-level `inventory`, `store`, and `heartbeat_monitor` hold API state.

### `src/ivp/metrics.py`

Prometheus text rendering for control-plane metrics.

### Compiler/Runtime Consistency

`src/ivp/compiler_runtime_consistency.py` validates structural consistency
between compiler summaries and runtime result dictionaries.

Implemented checks include:

- Backend selection matches the compiler plan or has a documented runtime
  override.
- Selected backend appears in the attempted backend chain.
- Runtime KV layout preserves the compiler memory layout decision.
- Replay/capture fields do not claim CUDA graph capture when this validation
  path only checks static replay eligibility.
- Scheduling priority remains conservative when compiler cost confidence is
  low.
- Execution statistics are present when a report wants to make measured
  runtime claims.

Truth boundary: this report validates compiler/runtime contract consistency. It
does not measure latency, memory, throughput, CUDA graph capture, or backend
kernel execution.

Implemented metrics:

- `ivp_jobs_current`
- `ivp_devices_current`
- `ivp_heartbeats_total`
- `ivp_events_total`
- `ivp_validation_results_total`

Boundary: these metrics describe the validation platform control plane, not live inference throughput or model-serving latency.

### `src/ivp/statistics.py`

Local statistics helpers.

Responsibilities:

- Nearest-rank percentile.
- Bootstrap percentile confidence interval.
- Mann-Whitney U test approximation.
- Threshold-based regression gate.

Implemented behavior: deterministic bootstrap with a default seed and test coverage for core paths.

Assumption: these helpers are lightweight validation utilities, not a replacement for a full statistical package.

### `src/ivp/llm_reports.py`

Generates demo LLM validation artifacts.

Implemented behavior: writes JSON and Markdown artifacts for a demo request timeline, scheduler analysis, KV-cache summary, SLO report, plan selection report, and memory validation report.

Simulated behavior: most values are hard-coded demo values. Treat them as demonstration artifacts unless replaced by real runtime traces.

### `scripts/run_demo.py`

Runs the control-plane simulation locally.

Implemented behavior:

- Registers CPU and mock accelerator workers.
- Applies heartbeats.
- Marks a stale CUDA worker offline after three missed heartbeats.
- Runs validation and writes a Markdown report.

Simulated behavior: worker execution is `MockWorker`; latency is random jitter, not measured hardware execution.

### `scripts/run_external_runtime_validation.py`

Runs a validation job against external runtime summary or benchmark artifacts.

Implemented behavior:

- Registers one `external_runtime` worker.
- Runs `ValidationPipeline`.
- Writes JSON and Markdown reports.

Boundary: depends on sibling `heterogeneous-inference-runtime` paths for live or summary data.

### `scripts/validate_runtime_artifacts.py`

Batch validator for runtime artifact directories.

Implemented behavior:

- Requires core files such as `prefill_decode_benchmark.json`, `kv_cache_trace.json`, `scheduler_trace.json`, `backend_trace.json`, `runtime_profile.json`, and `serving_trace.json`.
- Optionally reads scheduler decision, serving framework, cold start, trace adapter, technology gate, page prefetch, distributed serving, load balancing, worker health, fault tolerance, gRPC contract, and GPU PGO-like reports.
- Produces many JSON reports plus `runtime_validation_report.md` and `manifest.json`.

Boundary: this script validates evidence provided by `heterogeneous-inference-runtime`; it does not run a production serving system.

Known issue: the statistical-regression branch appears to reference `validation_report` and `slo_report` before those dictionaries are created.

## Repository Structure

- `src/ivp/`: Python package for core control-plane logic.
- `scripts/`: local demos and runtime artifact validators.
- `configs/`: sample artifact specs.
- `tests/`: pytest tests for metrics and statistical validation.
- `reports/`: generated report examples.
- `integration_artifacts/`: generated/demo integration artifacts.
- `observability/`: Prometheus and Grafana local demo configuration.
- `data/`: local SQLite database.

## Implemented vs Simulated Summary

Implemented:

- Pydantic artifact, device, heartbeat, event, and report schemas.
- In-memory device inventory and health state transitions.
- Health-aware device selection.
- Synchronous validation pipeline with retry and quarantine.
- Mock worker and external-runtime summary/benchmark worker.
- FastAPI control plane with SQLite persistence.
- JSON/Markdown report writers.
- Prometheus text-format control-plane metrics.
- Runtime artifact report generation from JSON traces.
- Statistical helper functions and selected tests.

Simulated or demo-only:

- Actual model execution for normal `execution_plan` artifacts.
- Correctness verification in `MockWorker`.
- Real hardware health monitoring.
- Continuous heartbeat timing.
- Distributed scheduling, preemption, and job queues.
- LLM demo artifacts from `src/ivp/llm_reports.py`.
- Many serving-framework validations when based on synthetic upstream artifacts.

## Assumptions

- Python 3.11 is the intended runtime for handoff work.
- Sibling repositories may exist at paths such as `../heterogeneous-inference-runtime` and `../ml-graph-compiler-runtime`.
- Reports already checked into `reports/` and `integration_artifacts/` are examples or generated artifacts, not necessarily fresh outputs.
- SQLite persistence is local and demo-oriented.
- Latency values from mock/demo paths are not benchmark numbers.
