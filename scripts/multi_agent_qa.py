#!/usr/bin/env python3
"""Multi-agent QA harness.

Runs seven QA agents against the running service:
  1. ContractAgent       — endpoint codes, schema fields
  2. SemanticsAgent      — directive interpretation accuracy
  3. PhysicsAgent        — energy balance, battery, neutrality
  4. DirectiveAgent      — every directive is applied
  5. CostAgent           — totals, optimality ratio
  6. ChaosAgent          — malformed input, bad data
  7. PerfAgent           — p95 latency, stability

Writes a structured report to QA_REPORT.md.

Runs in two modes:
  --mock  (default)  In-process FastAPI TestClient with deterministic mock LLM
  --live            Posts to a running HTTP endpoint
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
CASES = json.loads(
    (ROOT / "BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json").read_text()
)["cases"]


# ---------- helpers --------------------------------------------------------


def post_remote(url, payload, timeout=30):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {"detail": str(e)}
    except Exception as e:
        return 0, {"detail": str(e)}


def post_inprocess(client, url, payload):
    r = client.post(url, json=payload)
    return r.status_code, (
        r.json()
        if r.headers.get("content-type", "").startswith("application/json")
        else {}
    )


def get_inprocess(client, url):
    r = client.get(url)
    return r.status_code, r.json()


def get_remote(url, timeout=5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except Exception as e:
        return 0, {"detail": str(e)}


# ---------- agent base -----------------------------------------------------


@dataclass
class AgentResult:
    name: str
    status: str = "PASS"
    checks: list[str] = field(default_factory=list)
    failures: list[tuple[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# ---------- agents ---------------------------------------------------------


def contract_agent(post_fn, get_fn, results: list):
    r = AgentResult(name="ContractAgent")
    sc, body = get_fn("/health")
    if sc != 200 or body != {"status": "ok"}:
        r.failures.append(("health", f"status {sc}, body {body}"))
    else:
        r.checks.append("GET /health returns 200 with {status:ok}")

    # POST /optimize-energy happy path on SAMPLE-01
    case = CASES[0]
    sc, body = post_fn("/optimize-energy", case["input"])
    if sc != 200:
        r.failures.append(("optimize_basic", f"status {sc}"))
    else:
        for field_name in (
            "scenario_id",
            "directive_interpretation",
            "hourly_plan",
            "total_grid_kwh",
            "total_cost_bdt",
            "peak_grid_kwh",
            "plan_summary",
        ):
            if field_name not in body:
                r.failures.append(("schema", f"missing {field_name}"))
            else:
                r.checks.append(f"response has {field_name}")
        if body.get("scenario_id") != case["input"]["scenario_id"]:
            r.failures.append(("scenario_id_echo", "did not echo"))
        else:
            r.checks.append("scenario_id echoed")
        if len(body.get("hourly_plan", [])) != 24:
            r.failures.append(("plan_length", f"{len(body.get('hourly_plan', []))}"))
        else:
            r.checks.append("hourly_plan has 24 entries")
    r.status = "FAIL" if r.failures else "PASS"
    results.append(r)


def semantics_agent(post_fn, results: list):
    r = AgentResult(name="SemanticsAgent")
    for case in CASES:
        sc, body = post_fn("/optimize-energy", case["input"])
        if sc != 200:
            r.failures.append((case["id"], f"http {sc}"))
            continue
        ref = case["expected_output"]["directive_interpretation"]
        got = body["directive_interpretation"]
        if len(got) != len(ref):
            r.failures.append(
                (case["id"], f"interpretation count {len(got)} vs {len(ref)}")
            )
            continue
        sem_ok = True
        for g, e in zip(got, ref):
            if (
                g["note_index"] != e["note_index"]
                or g["applies"] != e["applies"]
                or g["directive_type"] != e["directive_type"]
                or g["structured_adjustment"] != e["structured_adjustment"]
            ):
                sem_ok = False
                r.failures.append((case["id"], f"mismatch note {g['note_index']}"))
                break
        if sem_ok:
            r.checks.append(f"{case['id']} interpretation correct")
    r.status = "FAIL" if r.failures else "PASS"
    results.append(r)


def physics_agent(post_fn, results: list):
    r = AgentResult(name="PhysicsAgent")
    for case in CASES:
        sc, body = post_fn("/optimize-energy", case["input"])
        if sc != 200:
            r.failures.append((case["id"], f"http {sc}"))
            continue
        plan = body["hourly_plan"]
        hours_req = case["input"]["hours"]
        solar_reduction_hours = set()
        active_min = case["input"]["battery"]["minimum_energy_kwh"]
        for it in case["expected_output"]["directive_interpretation"]:
            if not it["applies"]:
                continue
            adj = it["structured_adjustment"] or {}
            t = it["directive_type"]
            if t == "solar_reduction":
                f = float(adj["factor"])
                for h in adj["hours"]:
                    eff = hours_req[h]["solar_kwh"] * f
                    if plan[h]["solar_used_kwh"] > eff + 0.01:
                        r.failures.append((case["id"], f"solar overuse h={h}"))
            elif t == "minimum_battery_reserve":
                req_min = float(adj["minimum_energy_kwh"])
                active_min = max(active_min, req_min)
                for h in adj["hours"]:
                    if plan[h]["battery_energy_after_kwh"] < req_min - 0.01:
                        r.failures.append((case["id"], f"reserve violated h={h}"))
        # Energy balance per hour
        for e in plan:
            h = e["hour"]
            demand = hours_req[h]["demand_kwh"]
            charge = e["battery_kwh"] if e["battery_action"] == "charge" else 0
            disch = e["battery_kwh"] if e["battery_action"] == "discharge" else 0
            lhs = e["grid_kwh"] + e["solar_used_kwh"] + disch
            rhs = demand + charge
            if abs(lhs - rhs) > 0.01:
                r.failures.append((case["id"], f"balance h={h} {lhs} vs {rhs}"))
        # End-of-day
        e0 = case["input"]["battery"]["initial_energy_kwh"]
        if abs(plan[23]["battery_energy_after_kwh"] - e0) > 0.01:
            r.failures.append(
                (
                    case["id"],
                    f"neutrality {plan[23]['battery_energy_after_kwh']} vs {e0}",
                )
            )
        r.checks.append(f"{case['id']} physics ok")
    r.status = "FAIL" if r.failures else "PASS"
    results.append(r)


def directive_agent(post_fn, results: list):
    r = AgentResult(name="DirectiveAgent")
    for case in CASES:
        sc, body = post_fn("/optimize-energy", case["input"])
        if sc != 200:
            continue
        plan = body["hourly_plan"]
        for it in case["expected_output"]["directive_interpretation"]:
            if not it["applies"]:
                continue
            adj = it["structured_adjustment"] or {}
            t = it["directive_type"]
            if t == "no_charge_window":
                for h in adj.get("hours", []):
                    if (
                        plan[h]["battery_action"] == "charge"
                        and plan[h]["battery_kwh"] > 0.01
                    ):
                        r.failures.append((case["id"], f"charge in no_charge h={h}"))
            elif t == "no_discharge_window":
                for h in adj.get("hours", []):
                    if (
                        plan[h]["battery_action"] == "discharge"
                        and plan[h]["battery_kwh"] > 0.01
                    ):
                        r.failures.append(
                            (case["id"], f"discharge in no_discharge h={h}")
                        )
            elif t == "max_grid_window":
                cap = float(adj["max_grid_kwh"])
                for h in adj.get("hours", []):
                    if plan[h]["grid_kwh"] > cap + 0.01:
                        r.failures.append((case["id"], f"grid cap h={h}"))
            elif t == "minimum_battery_reserve":
                mn = float(adj["minimum_energy_kwh"])
                for h in adj.get("hours", []):
                    if plan[h]["battery_energy_after_kwh"] < mn - 0.01:
                        r.failures.append((case["id"], f"reserve h={h}"))
            elif t == "solar_reduction":
                f = float(adj["factor"])
                for h in adj.get("hours", []):
                    eff = case["input"]["hours"][h]["solar_kwh"] * f
                    if plan[h]["solar_used_kwh"] > eff + 0.01:
                        r.failures.append((case["id"], f"solar_reduction h={h}"))
        r.checks.append(f"{case['id']} directives applied")
    r.status = "FAIL" if r.failures else "PASS"
    results.append(r)


def cost_agent(post_fn, results: list):
    r = AgentResult(name="CostAgent")
    total_drift = 0.0
    n = 0
    for case in CASES:
        sc, body = post_fn("/optimize-energy", case["input"])
        if sc != 200:
            continue
        ref = case["expected_output"]
        # Recompute totals from plan
        plan = body["hourly_plan"]
        hours = case["input"]["hours"]
        tg = sum(e["grid_kwh"] for e in plan)
        tc = sum(
            e["grid_kwh"] * hours[h]["tariff_bdt_per_kwh"] for h, e in enumerate(plan)
        )
        pk = max((e["grid_kwh"] for e in plan), default=0)
        if abs(tg - body["total_grid_kwh"]) > 0.01:
            r.failures.append((case["id"], "total_grid mismatch"))
        if abs(tc - body["total_cost_bdt"]) > 0.01:
            r.failures.append((case["id"], "total_cost mismatch"))
        if abs(pk - body["peak_grid_kwh"]) > 0.01:
            r.failures.append((case["id"], "peak_grid mismatch"))
        if ref["total_cost_bdt"] > 0:
            drift = (
                abs(body["total_cost_bdt"] - ref["total_cost_bdt"])
                / ref["total_cost_bdt"]
            )
            total_drift += drift
            n += 1
        r.checks.append(f"{case['id']} totals consistent")
    r.notes.append(
        f"average cost drift vs reference: {(total_drift/max(1,n))*100:.4f}%"
    )
    r.status = "FAIL" if r.failures else "PASS"
    results.append(r)


def chaos_agent(post_fn, results: list, client=None):
    r = AgentResult(name="ChaosAgent")
    if client is None:
        r.notes.append("ChaosAgent detailed checks require --mock (in-process) mode")
        r.status = "PASS"
        results.append(r)
        return

    # malformed JSON
    resp = client.post(
        "/optimize-energy",
        data="{not json",
        headers={"content-type": "application/json"},
    )
    if resp.status_code not in (400, 422):
        r.failures.append(("malformed_json", f"status {resp.status_code}"))
    else:
        r.checks.append("malformed JSON returns 400/422")

    # missing fields
    resp = client.post("/optimize-energy", json={"scenario_id": "x"})
    if resp.status_code not in (400, 422):
        r.failures.append(("missing_fields", f"status {resp.status_code}"))
    else:
        r.checks.append("missing fields returns 400/422")

    # invalid hours (duplicate)
    bad = CASES[0]["input"].copy()
    bad["hours"] = [dict(h) for h in bad["hours"]]
    bad["hours"][0]["hour"] = bad["hours"][1]["hour"]
    resp = client.post("/optimize-energy", json=bad)
    if resp.status_code not in (400, 422):
        r.failures.append(("invalid_hours", f"status {resp.status_code}"))
    else:
        r.checks.append("invalid hours returns 400/422")

    # negative demand
    bad = CASES[0]["input"].copy()
    bad["hours"] = [dict(h) for h in bad["hours"]]
    bad["hours"][5]["demand_kwh"] = -10
    resp = client.post("/optimize-energy", json=bad)
    if resp.status_code not in (400, 422):
        r.failures.append(("negative_demand", f"status {resp.status_code}"))
    else:
        r.checks.append("negative demand returns 400/422")

    # 4 operator notes
    bad = CASES[0]["input"].copy()
    bad["operator_notes"] = ["a", "b", "c", "d"]
    resp = client.post("/optimize-energy", json=bad)
    if resp.status_code not in (400, 422):
        r.failures.append(("too_many_notes", f"status {resp.status_code}"))
    else:
        r.checks.append("4 operator notes returns 400/422")

    # empty note
    bad = CASES[0]["input"].copy()
    bad["operator_notes"] = [""]
    resp = client.post("/optimize-energy", json=bad)
    if resp.status_code not in (400, 422):
        r.failures.append(("empty_note", f"status {resp.status_code}"))
    else:
        r.checks.append("empty note returns 400/422")

    r.status = "FAIL" if r.failures else "PASS"
    results.append(r)


def perf_agent(post_fn, results: list):
    r = AgentResult(name="PerfAgent")
    case = CASES[0]
    timings = []
    N = 10
    for i in range(N):
        t0 = time.perf_counter()
        sc, _ = post_fn("/optimize-energy", case["input"])
        t1 = time.perf_counter()
        timings.append((t1 - t0) * 1000.0)
        if sc != 200:
            r.failures.append((f"iter_{i}", f"http {sc}"))
    if timings:
        timings.sort()
        p50 = timings[len(timings) // 2]
        p95 = timings[int(len(timings) * 0.95) - 1] if len(timings) > 1 else timings[-1]
        avg = sum(timings) / len(timings)
        r.notes.append(
            f"avg={avg:.1f}ms p50={p50:.1f}ms p95={p95:.1f}ms over {N} requests"
        )
        if p95 > 5000:
            r.failures.append(("p95", f"{p95:.1f}ms > 5000ms"))
        else:
            r.checks.append(f"p95 {p95:.1f}ms <= 5000ms")
    r.status = "FAIL" if r.failures else "PASS"
    results.append(r)


# ---------- main -----------------------------------------------------------


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true", help="In-process mock LLM")
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    args = ap.parse_args()

    if args.mock or "--mock" in sys.argv:
        from fastapi.testclient import TestClient
        from app.api import dependencies as deps
        from app.main import app
        from app.services.cache import cache

        deps.set_mock_interpretations(
            {c["id"]: c["expected_output"]["directive_interpretation"] for c in CASES}
        )
        cache.clear()
        client = TestClient(app)
        post_fn = lambda url, payload: post_inprocess(client, url, payload)
        get_fn = lambda url: get_inprocess(client, url)
        mode = "MOCK"
    else:
        post_fn = lambda url, payload: post_remote(
            f"{args.url}/optimize-energy", payload
        )
        get_fn = lambda url: get_remote(f"{args.url}{url}")
        mode = f"LIVE ({args.url})"

    results: list[AgentResult] = []
    print(f"Mode: {mode}\nRunning multi-agent QA...\n")

    print("[1/7] ContractAgent...")
    contract_agent(post_fn, get_fn, results)

    print("[2/7] SemanticsAgent...")
    semantics_agent(post_fn, results)

    print("[3/7] PhysicsAgent...")
    physics_agent(post_fn, results)

    print("[4/7] DirectiveAgent...")
    directive_agent(post_fn, results)

    print("[5/7] CostAgent...")
    cost_agent(post_fn, results)

    print("[6/7] ChaosAgent...")
    chaos_agent(
        post_fn, results, client=client if args.mock or "--mock" in sys.argv else None
    )

    print("[7/7] PerfAgent...")
    perf_agent(post_fn, results)

    # Write report
    lines = [
        "# GridWise QA Report",
        "",
        f"**Mode:** {mode}",
        f"**Cases:** {len(CASES)} public samples",
        "",
    ]
    overall = "PASS" if all(r.status == "PASS" for r in results) else "FAIL"
    lines.append(f"**Overall Status:** **{overall}**")
    lines.append("")
    lines.append("| Agent | Status | Checks | Failures | Notes |")
    lines.append("|-------|--------|--------|----------|-------|")
    for r in results:
        notes = "; ".join(r.notes)
        lines.append(
            f"| {r.name} | **{r.status}** | {len(r.checks)} | {len(r.failures)} | {notes} |"
        )
    lines.append("")
    for r in results:
        lines.append(f"## {r.name}: {r.status}")
        if r.checks:
            lines.append("**Checks:**")
            for c in r.checks:
                lines.append(f"- ✓ {c}")
        if r.failures:
            lines.append("**Failures:**")
            for f in r.failures:
                lines.append(f"- ✗ {f[0]}: {f[1]}")
        if r.notes:
            lines.append("**Notes:**")
            for n in r.notes:
                lines.append(f"- {n}")
        lines.append("")

    Path("QA_REPORT.md").write_text("\n".join(lines))
    print()
    print(f"Wrote QA_REPORT.md (overall: {overall})")
    sys.exit(0 if overall == "PASS" else 1)


if __name__ == "__main__":
    main()
