import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ivp.llm_reports import generate_llm_demo_artifacts


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate LLM runtime validation demo artifacts."
    )
    parser.add_argument(
        "--job-id",
        default="llm-runtime-demo-001",
    )
    parser.add_argument(
        "--latency-budget-ms",
        type=float,
        default=20.0,
    )
    parser.add_argument(
        "--output-dir",
        default="reports",
        help="Output directory relative to project root.",
    )
    args = parser.parse_args()

    paths = generate_llm_demo_artifacts(
        output_dir=ROOT / args.output_dir,
        job_id=args.job_id,
        latency_budget_ms=args.latency_budget_ms,
    )

    print(json.dumps({
        name: str(path)
        for name, path in paths.items()
    }, indent=2))


if __name__ == "__main__":
    main()
