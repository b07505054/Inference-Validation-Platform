#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

PYTHON=".venv/bin/python"

if [ ! -x "$PYTHON" ]; then
  echo "error: $PYTHON not found." >&2
  echo "Create the project-local virtualenv and install dependencies first:" >&2
  echo "  python3.11 -m venv .venv" >&2
  echo "  .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

if ! "$PYTHON" -m pytest --version >/dev/null 2>&1; then
  echo "error: pytest is not installed in .venv." >&2
  echo "Install dependencies first:" >&2
  echo "  .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

"$PYTHON" -m pytest
