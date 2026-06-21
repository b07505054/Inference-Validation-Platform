# Future Work

## Stabilize the Runtime Artifact Validator

Near-term:

- Fix the statistical-regression ordering bug in `scripts/validate_runtime_artifacts.py`.
- Add tests for sample-backed statistical regression failure.
- Split report builders into package modules while keeping the CLI entry point simple.

Expected benefit:

- Safer extension of optional artifact validations and clearer handoff to future maintainers.

## Expand Tests Around Core Control-Plane Logic

Recommended tests:

- Scheduler backend filtering.
- Required labels, preferred labels, preferred devices, and avoided devices.
- Resource capacity and queue depth behavior.
- Heartbeat healthy/unhealthy/offline transitions.
- Validation retry and quarantine flows.
- External runtime summary loading and best-result selection.
- API happy path and error paths.
- Report JSON/Markdown shape.

Expected benefit:

- Confidence to modify scheduler, inventory, and validation behavior without breaking demos.

## Make Simulation Boundaries Machine-Visible

Suggested improvements:

- Add `source_type` or `evidence_type` fields to reports, such as `simulated`, `demo_static`, `runtime_artifact`, or `live_benchmark`.
- Add metadata showing whether metrics are measured, estimated, aggregate-only, or sample-backed.
- Mark `MockWorker` correctness and latency as simulated in generated reports.

Expected benefit:

- Prevents demo values from being misread as real benchmark numbers.

## Add Real Correctness Validation Hooks

Potential approach:

- Extend `ArtifactSpec` with expected-output or golden-output metadata.
- Add a worker interface that returns correctness details rather than a bare boolean.
- Store max error, tolerance, sample count, and failure examples in `ValidationResult`.

Expected benefit:

- Turns correctness from a placeholder into an auditable validation result.

## Improve Worker Abstraction

Potential approach:

- Define a small worker protocol or registry keyed by `artifact_type`.
- Move artifact-type dispatch out of `ValidationPipeline`.
- Return structured failure categories from workers.

Expected benefit:

- Easier to add ONNX Runtime, TensorRT, ExecuTorch, CUDA, Metal, or remote workers without changing pipeline orchestration.

## Introduce Durable Job Lifecycle

Potential approach:

- Add job states such as `submitted`, `queued`, `running`, `passed`, `failed`, and `error`.
- Run validations in a background worker or task queue.
- Persist attempt-level records.
- Add cancellation and timeout handling.

Expected benefit:

- Makes the API usable for long-running external benchmarks and richer UI/observability workflows.

## Revisit Persistence and App State

Potential approach:

- Replace module-level API globals with an application factory.
- Treat SQLite as the source of truth for startup reconstruction, or explicitly mark it as history only.
- Add migrations if schemas evolve.

Expected benefit:

- Cleaner tests and safer deployment behavior.

## Improve Failure Attribution

Potential categories:

- Device health failure.
- Artifact invalid or incompatible.
- Correctness failure.
- Latency/SLO regression.
- External runtime process failure.
- Missing input artifact.
- Infrastructure error.

Expected benefit:

- Quarantine decisions become more accurate and reports become more actionable.

## Strengthen Statistical Validation

Potential approach:

- Keep aggregate-only reports clearly separated from sample-backed reports.
- Add sample count minimums for statistical claims.
- Consider using SciPy or another vetted package if stronger statistical accuracy becomes important.
- Include confidence interval and regression gate metadata in top-level report summaries.

Expected benefit:

- More defensible regression claims while preserving clear boundaries.

## Separate Examples From Generated Local State

Potential approach:

- Move canonical example reports to `examples/`.
- Keep local run outputs under ignored directories.
- Ignore or regenerate `data/ivp.sqlite3` unless the database is intentionally part of the demo.

Expected benefit:

- Cleaner repository state and less confusion during handoff.

## Add Real Runtime Integrations

Realistic next integrations:

- ONNX Runtime worker backed by `heterogeneous-inference-runtime`.
- TensorRT or CUDA worker when the host supports it.
- Artifact ingestion from `ml-graph-compiler-runtime`.
- Runtime trace adapter contracts for vLLM/SGLang/Triton-style traces.

Expected benefit:

- Moves the platform from control-plane simulation toward measured validation.

## Improve Observability

Potential additions:

- Attempt-level metrics.
- Validation duration metrics.
- External runtime failure counts.
- Device quarantine reason counts.
- Report links or IDs in event details.
- Separate dashboards for platform health and runtime performance evidence.

Expected benefit:

- Better debugging and cleaner separation between control-plane state and inference performance.

## Document Operational Commands

Potential additions:

- A concise developer setup guide.
- Commands for running the API, demos, runtime validator, tests, Prometheus, and Grafana.
- Expected sibling repo paths and how to override them.

Expected benefit:

- Faster onboarding for future agents and humans.
