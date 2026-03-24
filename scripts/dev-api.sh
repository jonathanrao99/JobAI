#!/usr/bin/env bash
# Run FastAPI with the same interpreter that has backend/requirements.txt installed.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# If a stale local uvicorn from this repo is still bound to 8000, clear it.
existing_pid="$(lsof -ti tcp:8000 -sTCP:LISTEN 2>/dev/null || true)"
if [[ -n "${existing_pid}" ]]; then
  existing_cmd="$(ps -p "${existing_pid}" -o command= 2>/dev/null || true)"
  if [[ "${existing_cmd}" == *"uvicorn backend.main:app"* ]]; then
    echo "Found stale JobAI API on :8000 (pid ${existing_pid}), restarting it..."
    kill "${existing_pid}" 2>/dev/null || true
    pkill -f "uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000" 2>/dev/null || true
    pkill -f "uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000" 2>/dev/null || true
    pkill -f "python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000" 2>/dev/null || true
    sleep 1
    # Uvicorn --reload can briefly survive SIGTERM via watcher parent/child.
    if lsof -ti tcp:8000 -sTCP:LISTEN >/dev/null 2>&1; then
      stubborn_pid="$(lsof -ti tcp:8000 -sTCP:LISTEN 2>/dev/null | head -n1)"
      kill -9 "${stubborn_pid}" 2>/dev/null || true
      sleep 0.5
    fi
  fi
fi

# Fail fast with useful context if something else still owns port 8000.
if lsof -ti tcp:8000 -sTCP:LISTEN >/dev/null 2>&1; then
  owner_pid="$(lsof -ti tcp:8000 -sTCP:LISTEN 2>/dev/null | head -n1)"
  owner_cmd="$(ps -p "${owner_pid}" -o command= 2>/dev/null || true)"
  echo "Port 8000 is already in use by PID ${owner_pid}: ${owner_cmd}" >&2
  echo "Stop that process or free port 8000, then re-run npm run dev." >&2
  exit 1
fi

# Only watch backend/ — default reload watches the whole repo and restarts when Next.js
# writes to frontend/.next, which races with Turbopack and causes ENOENT manifest errors.
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  exec "$ROOT/.venv/bin/python" -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000 \
    --reload-dir "$ROOT/backend"
fi
if command -v conda &>/dev/null && conda run -n job-agent python -c "import loguru" &>/dev/null; then
  exec conda run -n job-agent --no-capture-output python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000 \
    --reload-dir "$ROOT/backend"
fi
echo "No usable env: create .venv (python3.11 -m venv .venv && pip install -r backend/requirements.txt)" >&2
echo "or conda env job-agent with those deps, then re-run npm run dev." >&2
exit 1
