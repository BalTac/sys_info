#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Activate venv if present
if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
fi

python main_flet.py
