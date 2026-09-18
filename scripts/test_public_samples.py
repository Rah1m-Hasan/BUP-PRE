#!/usr/bin/env python3
"""Run all public sample cases against /optimize-energy.

Two modes:
  --mock   (default for CI) Runs in-process via FastAPI TestClient with a
           deterministic mock LLM returning the expected interpretations.
  --live   Posts to a running HTTP endpoint (default http://127.0.0.1:8000).

Exit code 0 = all cases pass. Non-zero = at least one failure.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CASES_PATH = ROOT / "BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json"
CASES = json.loads(CASES_PATH.read_text())["cases"]


def _client_post_inprocess(url: str, payload: dict):
    from fastapi.testclient import TestClient

    from app.api import dependencies as deps
    from app.main import app
    from app.services.cache import cache

    deps.set_mock_interpretations(
        {c["id"]: c["expected_output"]["directive_interpretation"] for c in CASES}
    )
    cache.clear()
    client = TestClient(app)
    resp = client.post("/optimize-energy", json=payload)
    return resp.status_code, resp.json()


def _client_post_remote(url: str, payload: dict):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {"detail": str(e)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true", help="In-process mock LLM (CI mode)")
    ap.add_argument(
        "--url",
        default="http://127.0.0.1:8000/optimize-energy",
        help="Remote endpoint URL (when --mock not set)",
    )
    args = ap.parse_args()

    use_mock = args.mock or "--mock" in sys.argv
    poster = _client_post_inprocess if use_mock else _client_post_remote
    target_url = "/optimize-energy" if use_mock else args.url

    print(f"Mode: {'MOCK (in-process)' if use_mock else f'REMOTE ({args.url})'}")
    print(f"Running {len(CASES)} public sample cases...\n")

    failures = []
    for case in CASES:
        status, body = poster(target_url, case["input"])
        if status != 200:
            failures.append((case["id"], f"http {status}", body))
            print(f"  [{case['id']}] FAIL http {status}: {str(body)[:120]}")
            continue
        ref = case["expected_output"]
        # Cost tolerance: within 1% of reference
        cost_drift_pct = abs(body["total_cost_bdt"] - ref["total_cost_bdt"]) / max(
            1.0, ref["total_cost_bdt"]
        )
        grid_drift_pct = abs(body["total_grid_kwh"] - ref["total_grid_kwh"]) / max(
            1.0, ref["total_grid_kwh"]
        )
        sem_ok = True
        for got, exp in zip(
            body["directive_interpretation"], ref["directive_interpretation"]
        ):
            if (
                got["note_index"] != exp["note_index"]
                or got["applies"] != exp["applies"]
                or got["directive_type"] != exp["directive_type"]
                or got["structured_adjustment"] != exp["structured_adjustment"]
            ):
                sem_ok = False
                break
        ok = sem_ok and cost_drift_pct <= 0.01 and grid_drift_pct <= 0.01
        flag = "PASS" if ok else "FAIL"
        print(
            f"  [{case['id']:<10}] {flag}  cost={body['total_cost_bdt']:>10.2f} "
            f"(ref {ref['total_cost_bdt']:.2f}, {cost_drift_pct*100:>6.3f}%)  "
            f"grid={body['total_grid_kwh']:>8.2f} peak={body['peak_grid_kwh']:>6.2f}"
        )
        if not ok:
            failures.append(
                (
                    case["id"],
                    f"sem={sem_ok} cost_drift={cost_drift_pct*100:.3f}% grid_drift={grid_drift_pct*100:.3f}%",
                    body,
                )
            )

    print()
    if failures:
        print(f"FAILED {len(failures)} of {len(CASES)}:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print(f"All {len(CASES)} public sample cases PASSED.")


if __name__ == "__main__":
    main()
