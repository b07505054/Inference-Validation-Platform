"""Optimization impact validation for distributed runtime planning artifacts.

OptimizationImpactValidator.validate() (or the standalone
validate_optimization_impact()) takes an artifact dict and produces an
OptimizationImpactReport that explains which runtime optimization caused
which metric improvement or regression.

Initially supports: prefix_cache

Input fields consumed from the artifact dict:
  artifact_name, model_name, selected_policy, truth_boundary
  prefix_cache_hit_type           ("miss" | "local_hit" | "remote_hit")
  prefix_cache_hit_tokens         (int)
  prefix_cache_saved_prefill_ms   (float)
  prefix_cache_remote_transfer_bytes (float)
  baseline_ttft_ms, optimized_ttft_ms
  baseline_tpot_ms, optimized_tpot_ms

Validation rules (prefix_cache):
  miss      — saved_prefill_ms must be 0; TTFT unchanged.
  local_hit — TTFT improves ≈ saved_prefill_ms; remote_transfer_bytes == 0.
  remote_hit — TTFT improves (net positive); remote_transfer_bytes > 0.
  TPOT must not materially improve solely from prefix cache.
  All optimization claims must include before/after metric values.
  truth_boundary in artifact must be non-empty.
  Missing required evidence produces warn, never a crash.

Truth boundary:
  "optimization_impact_validation_simulated_not_measured_cluster_performance"
"""

from __future__ import annotations

import json
from dataclasses import dataclass

_TB_REPORT = (
    "optimization_impact_validation_simulated_not_measured_cluster_performance"
)

# TPOT should not change materially from prefix cache alone.
_TPOT_CHANGE_THRESHOLD_MS: float = 0.5

# Deltas within this band are considered neutral for latency metrics.
_NEUTRAL_DELTA_THRESHOLD_MS: float = 0.1

# Local-hit TTFT improvement must match saved_prefill_ms within this tolerance.
_LOCAL_HIT_TTFT_ABS_TOLERANCE_MS: float = 0.5
_LOCAL_HIT_TTFT_REL_TOLERANCE_PCT: float = 0.05


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class OptimizationMetricDelta:
    """Before/after measurement for a single metric affected by an optimization.

    delta_value = optimized_value - baseline_value.
    For latency metrics lower delta is better; for byte metrics higher delta
    represents more transfer cost (a tradeoff).
    direction is "improvement", "regression", or "neutral".
    """

    metric_name: str
    baseline_value: float
    optimized_value: float
    delta_value: float
    delta_pct: float
    direction: str
    unit: str

    def to_dict(self) -> dict:
        return {
            "metric_name": self.metric_name,
            "baseline_value": self.baseline_value,
            "optimized_value": self.optimized_value,
            "delta_value": self.delta_value,
            "delta_pct": self.delta_pct,
            "direction": self.direction,
            "unit": self.unit,
        }


@dataclass
class OptimizationEvidence:
    """Validation evidence for a single named optimization.

    affected_metrics  — metrics that improved (lower latency, etc.).
    tradeoff_metrics  — metrics that worsened as a side effect (transfer bytes).
    evidence_status   — "pass", "warn", or "fail".
    explanation       — human-readable summary; includes warnings when present.
    truth_boundary    — taken from the artifact; must be non-empty.
    """

    optimization_name: str
    decision_name: str
    affected_metrics: list[OptimizationMetricDelta]
    tradeoff_metrics: list[OptimizationMetricDelta]
    truth_boundary: str
    evidence_status: str
    explanation: str

    def to_dict(self) -> dict:
        return {
            "optimization_name": self.optimization_name,
            "decision_name": self.decision_name,
            "affected_metrics": [m.to_dict() for m in self.affected_metrics],
            "tradeoff_metrics": [m.to_dict() for m in self.tradeoff_metrics],
            "truth_boundary": self.truth_boundary,
            "evidence_status": self.evidence_status,
            "explanation": self.explanation,
        }


@dataclass
class OptimizationImpactReport:
    """Top-level optimization impact report for one artifact.

    optimization_evidence is a list of OptimizationEvidence, one per
    recognized optimization found in the artifact.
    overall_status is the worst evidence_status across all evidences.
    truth_boundary is always _TB_REPORT (the validator's own boundary).
    """

    artifact_name: str
    model_name: str
    selected_policy: str
    optimization_evidence: list[OptimizationEvidence]
    overall_status: str
    truth_boundary: str

    def to_dict(self) -> dict:
        return {
            "artifact_name": self.artifact_name,
            "model_name": self.model_name,
            "selected_policy": self.selected_policy,
            "optimization_evidence": [e.to_dict() for e in self.optimization_evidence],
            "overall_status": self.overall_status,
            "truth_boundary": self.truth_boundary,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def to_markdown(self) -> str:
        lines: list[str] = [
            f"## Optimization Impact Report: {self.artifact_name}",
            "",
            f"**Model**: {self.model_name}  ",
            f"**Policy**: {self.selected_policy}  ",
            f"**Overall Status**: {self.overall_status}  ",
            f"**Truth Boundary**: {self.truth_boundary}",
            "",
        ]
        for ev in self.optimization_evidence:
            lines += [
                "---",
                "",
                f"### {ev.optimization_name} — {ev.decision_name}",
                "",
                f"**Evidence Status**: {ev.evidence_status}  ",
                f"**Explanation**: {ev.explanation}",
                "",
            ]
            if ev.affected_metrics:
                lines += [
                    "**Affected Metrics**:",
                    "| Metric | Before | After | Delta | % | Direction |",
                    "|--------|--------|-------|-------|---|-----------|",
                ]
                for m in ev.affected_metrics:
                    lines.append(
                        f"| {m.metric_name} "
                        f"| {m.baseline_value:.3f} {m.unit} "
                        f"| {m.optimized_value:.3f} {m.unit} "
                        f"| {m.delta_value:+.3f} {m.unit} "
                        f"| {m.delta_pct:+.2f}% "
                        f"| {m.direction} |"
                    )
                lines.append("")
            else:
                lines += ["**Affected Metrics**: none", ""]

            if ev.tradeoff_metrics:
                lines += [
                    "**Tradeoff Metrics**:",
                    "| Metric | Before | After | Delta | % | Direction |",
                    "|--------|--------|-------|-------|---|-----------|",
                ]
                for m in ev.tradeoff_metrics:
                    lines.append(
                        f"| {m.metric_name} "
                        f"| {m.baseline_value:.2f} {m.unit} "
                        f"| {m.optimized_value:.2f} {m.unit} "
                        f"| {m.delta_value:+.2f} {m.unit} "
                        f"| {m.delta_pct:+.2f}% "
                        f"| {m.direction} |"
                    )
                lines.append("")
            else:
                lines += ["**Tradeoff Metrics**: none", ""]

            lines += [
                f"**Truth Boundary**: {ev.truth_boundary}",
                "",
            ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _latency_delta(
    metric_name: str,
    baseline: float,
    optimized: float,
    unit: str = "ms",
) -> OptimizationMetricDelta:
    """Build a metric delta for a latency metric (lower = improvement)."""
    delta = optimized - baseline
    delta_pct = round((delta / baseline) * 100, 4) if baseline != 0.0 else 0.0
    if delta < -_NEUTRAL_DELTA_THRESHOLD_MS:
        direction = "improvement"
    elif delta > _NEUTRAL_DELTA_THRESHOLD_MS:
        direction = "regression"
    else:
        direction = "neutral"
    return OptimizationMetricDelta(
        metric_name=metric_name,
        baseline_value=baseline,
        optimized_value=optimized,
        delta_value=round(delta, 6),
        delta_pct=delta_pct,
        direction=direction,
        unit=unit,
    )


def _bytes_delta(
    metric_name: str,
    baseline: float,
    optimized: float,
) -> OptimizationMetricDelta:
    """Build a metric delta for a byte-count metric (higher = more cost = regression)."""
    delta = optimized - baseline
    # Percentage is not meaningful when baseline is 0 (pre-optimization baseline = 0 bytes).
    delta_pct = round((delta / baseline) * 100, 4) if baseline != 0.0 else 0.0
    direction = "regression" if delta > 0 else ("improvement" if delta < 0 else "neutral")
    return OptimizationMetricDelta(
        metric_name=metric_name,
        baseline_value=baseline,
        optimized_value=optimized,
        delta_value=round(delta, 2),
        delta_pct=delta_pct,
        direction=direction,
        unit="bytes",
    )


def _overall_status(evidences: list[OptimizationEvidence]) -> str:
    statuses = {e.evidence_status for e in evidences}
    if "fail" in statuses:
        return "fail"
    if "warn" in statuses:
        return "warn"
    return "pass"


# ---------------------------------------------------------------------------
# Prefix cache evidence builder
# ---------------------------------------------------------------------------

def _validate_prefix_cache(artifact: dict) -> OptimizationEvidence:
    hit_type: str | None = artifact.get("prefix_cache_hit_type")
    saved_ms: float | None = artifact.get("prefix_cache_saved_prefill_ms")
    remote_bytes: float | None = artifact.get("prefix_cache_remote_transfer_bytes")
    baseline_ttft: float | None = artifact.get("baseline_ttft_ms")
    optimized_ttft: float | None = artifact.get("optimized_ttft_ms")
    baseline_tpot: float | None = artifact.get("baseline_tpot_ms")
    optimized_tpot: float | None = artifact.get("optimized_tpot_ms")
    truth_boundary: str = artifact.get("truth_boundary") or ""

    warnings: list[str] = []

    # truth_boundary must be present.
    if not truth_boundary:
        warnings.append(
            "truth_boundary is missing or empty; all optimization claims "
            "must carry an explicit truth boundary"
        )

    # Before/after metric fields must be present.
    metric_fields = {
        "baseline_ttft_ms": baseline_ttft,
        "optimized_ttft_ms": optimized_ttft,
        "baseline_tpot_ms": baseline_tpot,
        "optimized_tpot_ms": optimized_tpot,
    }
    missing = [k for k, v in metric_fields.items() if v is None]
    if missing:
        warnings.append(
            f"missing before/after metric fields: {', '.join(missing)}; "
            "optimization claims require explicit before and after values"
        )

    # Build metric deltas where data is available.
    affected_metrics: list[OptimizationMetricDelta] = []
    tradeoff_metrics: list[OptimizationMetricDelta] = []

    if baseline_ttft is not None and optimized_ttft is not None:
        ttft_delta = _latency_delta("ttft_ms", baseline_ttft, optimized_ttft)
        affected_metrics.append(ttft_delta)

    if baseline_tpot is not None and optimized_tpot is not None:
        tpot_delta = _latency_delta("tpot_ms", baseline_tpot, optimized_tpot)
        if tpot_delta.delta_value < -_TPOT_CHANGE_THRESHOLD_MS:
            warnings.append(
                f"TPOT improved by {abs(tpot_delta.delta_value):.3f} ms; "
                "prefix cache only affects prefill service time and should not "
                "materially reduce TPOT (decode service time is unchanged)"
            )

    if remote_bytes is not None and remote_bytes > 0.0:
        tradeoff_metrics.append(_bytes_delta("remote_transfer_bytes", 0.0, remote_bytes))

    # Prefix-cache-specific rules.
    if hit_type == "miss":
        if saved_ms is not None and saved_ms > 0.0:
            warnings.append(
                f"hit_type is 'miss' but prefix_cache_saved_prefill_ms={saved_ms:.3f}; "
                "a cache miss must not report any prefill time savings"
            )

    elif hit_type == "local_hit":
        if remote_bytes is not None and remote_bytes > 0.0:
            warnings.append(
                f"hit_type is 'local_hit' but remote_transfer_bytes={remote_bytes:.2f}; "
                "a local cache hit should not incur remote transfer cost"
            )
        if baseline_ttft is not None and optimized_ttft is not None:
            actual_improvement = baseline_ttft - optimized_ttft
            if actual_improvement <= _NEUTRAL_DELTA_THRESHOLD_MS:
                warnings.append(
                    f"hit_type is 'local_hit' but TTFT did not improve "
                    f"(baseline={baseline_ttft:.3f} ms, optimized={optimized_ttft:.3f} ms); "
                    "a local hit must reduce prefill service time"
                )
            elif saved_ms is not None:
                tol = max(
                    _LOCAL_HIT_TTFT_ABS_TOLERANCE_MS,
                    _LOCAL_HIT_TTFT_REL_TOLERANCE_PCT * saved_ms,
                )
                if abs(actual_improvement - saved_ms) > tol:
                    warnings.append(
                        f"TTFT improvement ({actual_improvement:.3f} ms) deviates from "
                        f"saved_prefill_ms ({saved_ms:.3f} ms) by more than tolerance "
                        f"({tol:.3f} ms); local hit savings should propagate directly to TTFT"
                    )

    elif hit_type == "remote_hit":
        if remote_bytes is None or remote_bytes <= 0.0:
            warnings.append(
                "hit_type is 'remote_hit' but remote_transfer_bytes is 0 or absent; "
                "a remote cache hit must transfer KV bytes from the cache worker"
            )
        if baseline_ttft is not None and optimized_ttft is not None:
            actual_improvement = baseline_ttft - optimized_ttft
            if actual_improvement <= _NEUTRAL_DELTA_THRESHOLD_MS:
                warnings.append(
                    f"hit_type is 'remote_hit' but TTFT did not improve "
                    f"(baseline={baseline_ttft:.3f} ms, optimized={optimized_ttft:.3f} ms); "
                    "remote transfer cost may have exceeded the prefill savings"
                )

    elif hit_type is not None:
        warnings.append(
            f"unrecognized prefix_cache_hit_type={hit_type!r}; "
            "expected 'miss', 'local_hit', or 'remote_hit'"
        )
    else:
        warnings.append("prefix_cache_hit_type is missing")

    # Compose explanation.
    if hit_type == "miss":
        base_explanation = "Cache miss: no prefill time saved, TTFT and TPOT unchanged."
    elif hit_type == "local_hit":
        _sm = f"{saved_ms:.3f}" if saved_ms is not None else "?"
        base_explanation = (
            f"Local cache hit: prefill time reduced by {_sm} ms; "
            "no remote transfer required."
        )
    elif hit_type == "remote_hit":
        _sm = f"{saved_ms:.3f}" if saved_ms is not None else "?"
        _rb = f"{remote_bytes:.0f}" if remote_bytes is not None else "?"
        base_explanation = (
            f"Remote cache hit: prefill time reduced by {_sm} ms; "
            f"remote transfer of {_rb} bytes incurred as tradeoff."
        )
    else:
        base_explanation = f"Unknown or missing hit_type: {hit_type!r}."

    if warnings:
        explanation = base_explanation + " Warnings: " + " | ".join(warnings)
    else:
        explanation = base_explanation

    evidence_status = "warn" if warnings else "pass"

    return OptimizationEvidence(
        optimization_name="prefix_cache",
        decision_name=str(hit_type) if hit_type is not None else "unknown",
        affected_metrics=affected_metrics,
        tradeoff_metrics=tradeoff_metrics,
        truth_boundary=truth_boundary,
        evidence_status=evidence_status,
        explanation=explanation,
    )


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def validate_optimization_impact(artifact: dict) -> OptimizationImpactReport:
    """Validate a runtime artifact dict and return an OptimizationImpactReport.

    Never raises. Missing fields produce warn evidence entries.
    Currently validates: prefix_cache.
    """
    artifact_name: str = artifact.get("artifact_name") or ""
    model_name: str = artifact.get("model_name") or ""
    selected_policy: str = artifact.get("selected_policy") or ""

    evidences: list[OptimizationEvidence] = []

    # prefix_cache evidence is always emitted when the key is present or the
    # input is an artifact we're asked to validate (even if hit_type is missing,
    # we emit a warn rather than silently skip).
    evidences.append(_validate_prefix_cache(artifact))

    overall = _overall_status(evidences)

    return OptimizationImpactReport(
        artifact_name=artifact_name,
        model_name=model_name,
        selected_policy=selected_policy,
        optimization_evidence=evidences,
        overall_status=overall,
        truth_boundary=_TB_REPORT,
    )


class OptimizationImpactValidator:
    """Thin stateless class wrapper around validate_optimization_impact.

    Provided for callers that prefer an object interface over a bare function.
    """

    def validate(self, artifact: dict) -> OptimizationImpactReport:
        return validate_optimization_impact(artifact)
