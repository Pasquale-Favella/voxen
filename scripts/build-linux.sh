#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -x .venv/bin/python ]]; then
  "${PYTHON:-python3}" -m venv .venv
fi
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python scripts/build.py
