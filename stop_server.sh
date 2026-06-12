#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${PORT:-8765}"

if command -v python3 >/dev/null 2>&1; then
  exec python3 "${SCRIPT_DIR}/stop_server.py" --port "${PORT}"
fi

exec python "${SCRIPT_DIR}/stop_server.py" --port "${PORT}"
