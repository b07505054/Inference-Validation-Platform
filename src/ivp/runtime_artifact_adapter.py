"""Adapter to extract prefix-cache impact fields from distributed runtime plan artifacts.

Bridges heterogeneous-inference-runtime distributed planning artifacts to
OptimizationImpactValidator. Does not require the sibling repo to be present;
pass an explicit path or call with an empty dict to receive a warn-level report.

Key transformation:
  distributed_runtime_plan.json  (nested dataclass JSON)
    → extract_prefix_cache_fields()
    → flat dict accepted by validate_optimization_impact()

Baseline TTFT is reconstructed by reversing the prefix-cache effect:
  baseline_ttft = optimized_ttft + saved_prefill_ms - remote_transfer_cost_ms

This holds because the planner applies:
  prefill_service_ms -= saved_prefill_ms
  kv_transfer_ms     += remote_transfer_cost_ms
So the net TTFT change = -(saved_prefill_ms - remote_transfer_cost_ms).
"""

from __future__ import annotations

import json
from pathlib import Path

_DEFAULT_ARTIFACT_FILENAME = "distributed_runtime_plan.json"


def extract_prefix_cache_fields(artifact: dict, artifact_name: str = "") -> dict:
    """Extract the 12 fields expected by validate_optimization_impact.

    Handles missing, null, or partial artifacts gracefully (never raises).
    Fields that cannot be extracted are returned as None; the validator will
    produce warnings for them rather than crashing.
    """
    model_name: str = artifact.get("model_name") or ""
    if not artifact_name:
        artifact_name = (
            f"distributed_runtime_plan_{model_name}"
            if model_name else "distributed_runtime_plan"
        )

    decision: dict = artifact.get("decision_comparison") or {}
    selected_policy: str = (
        decision.get("selected_policy")
        or artifact.get("selected_policy")
        or ""
    )

    pd_breakdown: dict = decision.get("pd_split") or {}
    col_breakdown: dict = decision.get("colocated") or {}

    if selected_policy == "pd_split":
        optimized_ttft: float | None = pd_breakdown.get("ttft_ms")
        optimized_tpot: float | None = pd_breakdown.get("tpot_ms")
    elif selected_policy == "colocated":
        optimized_ttft = col_breakdown.get("ttft_ms")
        optimized_tpot = col_breakdown.get("tpot_ms")
    else:
        optimized_ttft = None
        optimized_tpot = None

    pca: dict = artifact.get("prefix_cache_adjustment") or {}
    if pca:
        hit_type: str | None = pca.get("hit_type")
    else:
        # No prefix_cache_adjustment in the artifact — treat as a cache miss.
        hit_type = "miss"

    hit_tokens: int = pca.get("hit_tokens") or 0
    saved_prefill_ms: float = pca.get("saved_prefill_ms") or 0.0
    remote_transfer_bytes: float = pca.get("remote_transfer_bytes") or 0.0
    remote_transfer_cost_ms: float = pca.get("remote_transfer_cost_ms") or 0.0
    truth_boundary: str = (
        pca.get("truth_boundary")
        or artifact.get("truth_boundary")
        or ""
    )

    # Reconstruct baseline by undoing the cache effect.
    if optimized_ttft is not None:
        baseline_ttft: float | None = (
            optimized_ttft + saved_prefill_ms - remote_transfer_cost_ms
        )
    else:
        baseline_ttft = None

    # Prefix cache does not affect decode service time → TPOT unchanged.
    baseline_tpot: float | None = optimized_tpot

    return {
        "artifact_name": artifact_name,
        "model_name": model_name,
        "selected_policy": selected_policy,
        "truth_boundary": truth_boundary,
        "prefix_cache_hit_type": hit_type,
        "prefix_cache_hit_tokens": hit_tokens,
        "prefix_cache_saved_prefill_ms": saved_prefill_ms,
        "prefix_cache_remote_transfer_bytes": remote_transfer_bytes,
        "baseline_ttft_ms": baseline_ttft,
        "optimized_ttft_ms": optimized_ttft,
        "baseline_tpot_ms": baseline_tpot,
        "optimized_tpot_ms": optimized_tpot,
    }


def load_artifact_from_path(path: Path) -> dict:
    """Load a JSON artifact from path.

    Returns {} if the file is absent or cannot be parsed.
    Never raises.
    """
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
