#!/usr/bin/env bash
# Run FastAPI with the same interpreter that has backend/requirements.txt installed.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  exec "$ROOT/.venv/bin/python" -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
fi
if command -v conda &>/dev/null && conda run -n job-agent python -c "import loguru" &>/dev/null; then
  exec conda run -n job-agent --no-capture-output python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
fi
echo "No usable env: create .venv (python3.11 -m venv .venv && pip install -r backend/requirements.txt)" >&2
echo "or conda env job-agent with those deps, then re-run npm run dev." >&2
exit 1
