#!/usr/bin/env bash
# Quick local startup script.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

if [ ! -f ".env" ]; then
  echo "[run_local] No .env found; copying .env.example to .env"
  cp .env.example .env
  echo "[run_local] Edit .env to set GROQ_API_KEY before relying on the real LLM."
fi

echo "[run_local] Starting uvicorn on 0.0.0.0:8000"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000