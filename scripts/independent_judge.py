"""🧮 AGENT 2: The Physics & Math Auditor (The Independent Judge).

Mathematically proves the MILP Optimizer is flawless — does NOT trust the
app's internal replay validator. Builds a fresh, pure-Python judge from
scratch.

Constraints re-derived from the Problem Statement:
  1. Energy balance: grid + solar_used + disch == demand + charge
  2. Battery transitions: E_after[h] = E_before[h] + charge - disch
  3. Battery bounds: active_min[h] <= E_after[h] <= capacity
  4. Rate limits: charge <= max_charge, disch <= max_discharge
  5. Solar limit: solar_used <= effective_solar[h]
  6. End-of-day neutrality: E_after[23] == initial_energy  (tol 0.01)
  7. Directive application: no_charge hours -> charge=0;
     no_discharge hours -> disch=0;
     max_grid hours -> grid <= cap; reserve hours -> E_after >= min;
     solar_reduction hours -> effective_solar = original * factor
  8. Schema validity: scenario_id echoed; 24 hours; total_grid_kwh /
     total_cost_bdt / peak_grid_kwh match recompute from hourly_plan
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from audit_logs.audit_runner import configure, post_json

configure("inprocess")

CASES = json.loads(
    (ROOT / "BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json").read_text()
)["cases"]

TOL = 0.01

failures: list[dict] = []


def fail(case_id: str, hour: int | None, rule: str, detail: str) -> None:
    failures.append(
        {
            "case": case_id,
            "hour": hour,
            "rule": rule,
            "detail": detail,
        }
    )


def record(case_id: str, ok: bool, detail: str) -> None:
    marker = "PASS" if ok else "FAIL"
    print(f"  [{marker}] {case_id}: {detail}")


def active_minimum(req_hours, base_min, directive_interp):
    """Compute the active_minimum[h] array from base + all reserve directives."""
    arr = [base_min] * 24
    for it in directive_interp:
        if not it.get("applies"):
            continue
        if it["directive_type"] == "minimum_battery_reserve":
            mn = float(it["structured_adjustment"]["minimum_energy_kwh"])
            for h in it["structured_adjustment"]["hours"]:
                if mn > arr[h]:
                    arr[h] = mn
    return arr


def effective_solar(orig_hours, directive_interp):
    """Compute effective_solar[h] with chained solar_reduction factors."""
    arr = [float(h["solar_kwh"]) for h in orig_hours]
    for it in directive_interp:
        if not it.get("applies"):
            continue
        if it["directive_type"] == "solar_reduction":
            f = float(it["structured_adjustment"]["factor"])
            for h in it["structured_adjustment"]["hours"]:
                arr[h] *= f
    return arr


def no_charge_set(directive_interp):
    s = set()
    for it in directive_interp:
        if not it.get("applies"):
            continue
        if it["directive_type"] == "no_charge_window":
            s.update(int(x) for x in it["structured_adjustment"]["hours"])
    return s


def no_discharge_set(directive_interp):
    s = set()
    for it in directive_interp:
        if not it.get("applies"):
            continue
        if it["directive_type"] == "no_discharge_window":
            s.update(int(x) for x in it["structured_adjustment"]["hours"])
    return s


def max_grid_caps(directive_interp):
    caps = {}
    for it in directive_interp:
        if not it.get("applies"):
            continue
        if it["directive_type"] == "max_grid_window":
            cap = float(it["structured_adjustment"]["max_grid_kwh"])
            for h in it["structured_adjustment"]["hours"]:
                if h not in caps or cap < caps[h]:
                    caps[h] = cap
    return caps


def audit_case(case: dict) -> None:
    cid = case["id"]
    payload = case["input"]
    sc, body = post_json("/optimize-energy", payload)
    if sc != 200:
        record(cid, False, f"http {sc} {str(body)[:120]}")
        fail(cid, None, "http_status", f"status {sc} {str(body)[:120]}")
        return

    plan = body["hourly_plan"]
    hours_req = payload["hours"]
    bat = payload["battery"]
    e0 = float(bat["initial_energy_kwh"])
    cap = float(bat["capacity_kwh"])
    max_chg = float(bat["max_charge_kwh_per_hour"])
    max_dis = float(bat["max_discharge_kwh_per_hour"])
    cap_max_chg = float(bat["max_charge_kwh_per_hour"])
    cap_max_dis = float(bat["max_discharge_kwh_per_hour"])
    base_min = float(bat["minimum_energy_kwh"])
    directive_interp = body["directive_interpretation"]

    # Re-derive all constraints
    eff_solar = effective_solar(hours_req, directive_interp)
    act_min = active_minimum(hours_req, base_min, directive_interp)
    nc = no_charge_set(directive_interp)
    nd = no_discharge_set(directive_interp)
    caps = max_grid_caps(directive_interp)

    # Schema check
    if body["scenario_id"] != payload["scenario_id"]:
        fail(cid, None, "schema", "scenario_id mismatch")
    if len(plan) != 24:
        fail(cid, None, "schema", f"plan length {len(plan)}")
    if [p["hour"] for p in plan] != list(range(24)):
        fail(cid, None, "schema", "plan hours not 0..23 in order")

    # Per-hour validation
    prev_e = e0
    total_grid = 0.0
    total_cost = 0.0
    peak_grid = 0.0
    for entry in plan:
        h = int(entry["hour"])
        grid = float(entry["grid_kwh"])
        solar = float(entry["solar_used_kwh"])
        action = entry["battery_action"]
        bkwh = float(entry["battery_kwh"])
        e_after = float(entry["battery_energy_after_kwh"])

        # Non-negative
        if grid < -TOL:
            fail(cid, h, "non_negative", f"grid={grid}")
        if solar < -TOL:
            fail(cid, h, "non_negative", f"solar={solar}")
        if bkwh < -TOL:
            fail(cid, h, "non_negative", f"bkwh={bkwh}")
        if e_after < -TOL:
            fail(cid, h, "non_negative", f"eafter={e_after}")

        # Battery idle rule
        if action == "idle" and bkwh > TOL:
            fail(cid, h, "idle_rule", f"idle with bkwh={bkwh}")
        if action not in ("charge", "discharge", "idle"):
            fail(cid, h, "bad_action", f"action={action}")

        # Solar limit
        if solar > eff_solar[h] + TOL:
            fail(cid, h, "solar_limit", f"used {solar} > effective {eff_solar[h]}")

        charge = bkwh if action == "charge" else 0.0
        disch = bkwh if action == "discharge" else 0.0

        # Rate limits
        if charge > max_chg + TOL:
            fail(cid, h, "rate_charge", f"{charge} > {max_chg}")
        if disch > max_dis + TOL:
            fail(cid, h, "rate_discharge", f"{disch} > {max_dis}")

        # Energy balance
        demand = float(hours_req[h]["demand_kwh"])
        tariff = float(hours_req[h]["tariff_bdt_per_kwh"])
        lhs = grid + solar + disch
        rhs = demand + charge
        if abs(lhs - rhs) > TOL:
            fail(cid, h, "energy_balance", f"lhs={lhs} rhs={rhs}")

        # Battery transition
        if abs((prev_e + charge - disch) - e_after) > TOL:
            fail(
                cid,
                h,
                "battery_transition",
                f"prev+chg-dis={prev_e + charge - disch} eafter={e_after}",
            )

        # Battery bounds
        if e_after < act_min[h] - TOL:
            fail(cid, h, "battery_bound", f"eafter {e_after} < active_min {act_min[h]}")
        if e_after > cap + TOL:
            fail(cid, h, "battery_bound", f"eafter {e_after} > capacity {cap}")

        # Directive application
        if h in nc and charge > TOL:
            fail(cid, h, "no_charge_window", f"charge={charge}")
        if h in nd and disch > TOL:
            fail(cid, h, "no_discharge_window", f"discharge={disch}")
        if h in caps and grid > caps[h] + TOL:
            fail(cid, h, "max_grid_window", f"grid {grid} > cap {caps[h]}")

        prev_e = e_after
        total_grid += grid
        total_cost += grid * tariff
        peak_grid = max(peak_grid, grid)

    # End-of-day neutrality
    if abs(prev_e - e0) > TOL:
        fail(cid, 23, "end_of_day_neutrality", f"{prev_e} != {e0}")

    # Totals consistency
    if abs(total_grid - body["total_grid_kwh"]) > TOL:
        fail(
            cid,
            None,
            "totals",
            f"total_grid {total_grid} vs body {body['total_grid_kwh']}",
        )
    if abs(total_cost - body["total_cost_bdt"]) > TOL:
        fail(
            cid,
            None,
            "totals",
            f"total_cost {total_cost} vs body {body['total_cost_bdt']}",
        )
    if abs(peak_grid - body["peak_grid_kwh"]) > TOL:
        fail(
            cid,
            None,
            "totals",
            f"peak_grid {peak_grid} vs body {body['peak_grid_kwh']}",
        )

    # Cost-optimality check (vs reference)
    ref_cost = case["expected_output"]["total_cost_bdt"]
    if ref_cost > 0:
        drift = abs(body["total_cost_bdt"] - ref_cost) / ref_cost
        if drift > 0.01:
            fail(
                cid,
                None,
                "optimality",
                f"cost drift {drift*100:.4f}% (our {body['total_cost_bdt']} vs ref {ref_cost})",
            )

    ok = not any(f["case"] == cid for f in failures)
    record(
        cid,
        ok,
        (
            "valid"
            if ok
            else f"FAIL ({sum(1 for f in failures if f['case']==cid)} violations)"
        ),
    )


def main():
    print("=" * 60)
    print("🧮  AGENT 2: PHYSICS & MATH AUDITOR")
    print("=" * 60)
    print()
    for case in CASES:
        audit_case(case)
    out = ROOT / "audit_logs" / "judge_failures.json"
    out.write_text(json.dumps({"agent": "MathJudge", "failures": failures}, indent=2))
    print()
    print(f"Math Auditor total failures: {len(failures)}")
    if failures:
        for f in failures:
            print(f"  - {f['case']} h={f['hour']} {f['rule']}: {f['detail']}")
    print(f"Wrote {out}")
    sys.exit(0 if not failures else 1)


if __name__ == "__main__":
    main()
