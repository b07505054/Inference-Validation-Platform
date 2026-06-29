"""Integration runner: distributed runtime artifact → OptimizationImpactValidator → reports.

Pipeline:
  distributed_runtime_plan.json
    → load_artifact_from_path()
    → extract_prefix_cache_fields()
    → validate_optimization_impact()
    → optimization_impact_report.json
    → optimization_impact_report.md

The runner never raises. A missing or malformed artifact produces a warn-level report.
Does not require the sibling repo to be present at the call site; pass artifact_path
explicitly, or rely on the default relative path which handles absence gracefully.
"""

from __future__ import annotations

from pathlib import Path

from src.ivp.optimization_impact import validate_optimization_impact
from src.ivp.runtime_artifact_adapter import (
    extract_prefix_cache_fields,
    load_artifact_from_path,
)

_JSON_FILENAME = "optimization_impact_report.json"
_MD_FILENAME = "optimization_impact_report.md"

# Default artifact path, relative to the IVP repo root, pointing at the sibling repo.
_SIBLING_RELATIVE_PARTS = (
    "..",
    "heterogeneous-inference-runtime",
    "results",
    "llm_runtime_artifacts",
    "distributed_runtime_plan.json",
)


def run_optimization_impact_integration(
    *,
    artifact_path: Path | None = None,
    output_dir: Path | None = None,
    artifact_dir: Path | None = None,
) -> tuple[Path, Path]:
    """Run the optimization impact integration pipeline.

    Loads the distributed runtime plan artifact, extracts prefix-cache fields,
    validates them, and writes JSON + Markdown reports to output_dir.
    Never raises. Missing or malformed artifacts produce warn-level reports.

    Args:
        artifact_path: Explicit path to distributed_runtime_plan.json.
                       Takes precedence over artifact_dir and the default.
        artifact_dir: Directory to search for distributed_runtime_plan.json.
                      Used when artifact_path is None.
        output_dir: Directory to write reports into.
                    Defaults to reports/runtime_artifact_validation/ in the IVP repo root.

    Returns:
        (json_path, md_path) — paths of the two written report files.
    """
    if output_dir is None:
        _repo_root = Path(__file__).resolve().parents[2]
        output_dir = _repo_root / "reports" / "runtime_artifact_validation"

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / _JSON_FILENAME
    md_path = output_dir / _MD_FILENAME

    resolved = _resolve_artifact_path(artifact_path, artifact_dir)
    raw = load_artifact_from_path(resolved)
    extracted = extract_prefix_cache_fields(raw)
    report = validate_optimization_impact(extracted)

    json_path.write_text(report.to_json(), encoding="utf-8")
    md_path.write_text(report.to_markdown(), encoding="utf-8")

    return json_path, md_path


def _resolve_artifact_path(
    artifact_path: Path | None,
    artifact_dir: Path | None,
) -> Path:
    if artifact_path is not None:
        return artifact_path
    if artifact_dir is not None:
        return artifact_dir / "distributed_runtime_plan.json"
    _repo_root = Path(__file__).resolve().parents[2]
    return Path(_repo_root, *_SIBLING_RELATIVE_PARTS).resolve()
