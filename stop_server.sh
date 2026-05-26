#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-8765}"

pids="$(lsof -ti "tcp:${PORT}" 2>/dev/null || true)"

if [[ -z "${pids}" ]]; then
  pids="$(pgrep -f "python3 .*server.py|python .*server.py" 2>/dev/null || true)"
fi

if [[ -z "${pids}" ]]; then
  echo "TPDb Plex Poster Picker is not running."
  exit 0
fi

echo "Stopping TPDb Plex Poster Picker: ${pids}"
kill ${pids}
