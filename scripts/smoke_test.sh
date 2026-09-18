#!/usr/bin/env bash
# Smoke test against a running service on http://127.0.0.1:8000
set -euo pipefail
URL="${URL:-http://127.0.0.1:8000}"
echo "[smoke] GET ${URL}/health"
curl -sf "${URL}/health" && echo
echo "[smoke] OK"