# Design Decisions

## Keep the Core Platform Small and Explicit

The code uses simple modules for inventory, scheduling, validation, workers, reporting, persistence, and metrics instead of a larger framework.

Tradeoff:

- Benefit: easy to read, demo, test, and hand off.
- Cost: some production concerns are absent, including async job queues, distributed worker leases, background heartbeat timers, and multi-process state coordination.

Assumption: clarity and interview/demo value are more important here than production control-plane completeness.

## Use Pydantic Models for Contracts

`src/ivp/models.py` and `src/ivp/api_models.py` use Pydantic models for artifacts, devices, heartbeats, validation results, and API requests.

Tradeoff:

- Benefit: validation and JSON serialization are concise.
- Cost: the data layer also serializes some model output as JSON strings in SQLite, so schema evolution must be handled carefully.

Assumption: artifact and report schemas will continue changing, so explicit models are useful even in a small repo.

## Separate Scheduling From Validation Execution

The scheduler only chooses a device. The validation pipeline owns attempt logic, quarantine, retry, and worker creation.

Tradeoff:

- Benefit: device ranking logic is isolated from validation result handling.
- Cost: `ValidationPipeline._create_worker()` still encodes artifact-type-to-worker dispatch, so new worker types require changing pipeline code.

Assumption: a small dispatch method is acceptable until there are enough worker types to justify a registry or plugin interface.

## In-Memory Inventory Plus SQLite Persistence

The API keeps active scheduling state in a module-level `DeviceInventory` and persists jobs/devices/events/heartbeats to SQLite.

Tradeoff:

- Benefit: simple local server setup and easy tests through monkeypatching.
- Cost: SQLite is not the scheduling source of truth during a process lifetime, and module globals make multi-process deployment risky.

Assumption: this is a local/demo control plane, not a horizontally scaled service.

## Synchronous Validation Pipeline

Job submission runs validation inline and returns after completion.

Tradeoff:

- Benefit: simple control flow and deterministic report generation.
- Cost: API requests can block while external benchmarks run, and there is no queued job lifecycle.

Assumption: synchronous behavior is acceptable for demos and local validation tasks.

## Simulate Normal Execution Plans, Ingest External Runtime Evidence Separately

Normal `execution_plan` artifacts use `MockWorker`, while `external_runtime_summary` and `external_runtime_benchmark` use `ExternalRuntimeWorker`.

Tradeoff:

- Benefit: the control-plane mechanics can be demonstrated without hardware or sibling repos, while external runtime integration can consume real artifacts when available.
- Cost: mock results can be mistaken for measured inference performance unless the simulation boundary is documented.

Assumption: the platform validates and summarizes lower-layer artifacts; it does not need to own all benchmarking code.

## Health-Aware Scheduling With Simple Ranking

Scheduling uses health status, backend compatibility, labels, resource capacity, queue depth, preferred devices, and latency history.

Tradeoff:

- Benefit: captures the shape of production scheduling without heavy machinery.
- Cost: preemption and priority are modeled but not implemented; resource accounting is limited; latency priors are static.

Assumption: explicit scheduling rules are more useful at this stage than a complex optimizer.

## Quarantine on Validation Failure

The pipeline quarantines a device whenever correctness or latency budget validation fails.

Tradeoff:

- Benefit: demonstrates self-healing and retry behavior clearly.
- Cost: all failures are treated as device problems, even though an artifact or workload could be the real cause.

Assumption: the repo is modeling hardware-in-the-loop validation patterns, where failed validation should remove the worker from the candidate pool until inspected.

## Reports as First-Class Artifacts

The project writes JSON and Markdown reports for validation runs, and many generated examples are checked into the repo.

Tradeoff:

- Benefit: easy to audit and show behavior without running every path.
- Cost: generated artifacts can become stale and may be confused with source.

Assumption: report artifacts are a core handoff and demo surface.

## Runtime Artifact Validator Is Script-Oriented

`scripts/validate_runtime_artifacts.py` is a large script with many helper functions rather than a package of small modules.

Tradeoff:

- Benefit: a single command can validate many artifact types and emit all expected reports.
- Cost: the script is long, contains duplicated report patterns, and has at least one likely ordering bug.

Assumption: the validator grew as an integration bridge and should be modularized only after the desired artifact contracts stabilize.

## Lightweight Statistics Without External Scientific Dependencies

Statistical validation uses local helpers for percentile, bootstrap CI, Mann-Whitney U, and regression gates.

Tradeoff:

- Benefit: no SciPy dependency and deterministic tests.
- Cost: statistical methods are simplified and should be reviewed before high-stakes claims.

Assumption: the goal is to identify likely runtime regressions in artifact reports, not publish rigorous statistical benchmarks.

## Observability Focuses on the Control Plane

Prometheus metrics count jobs, devices, heartbeats, events, and validation outcomes.

Tradeoff:

- Benefit: clear separation between platform health and model-serving performance.
- Cost: dashboard users may expect inference metrics that this repo intentionally does not expose.

Assumption: live inference metrics belong in the runtime/serving system and should be ingested or linked separately.
