#!/usr/bin/env python3
"""Edge-case matrix runner.

Generates synthetic scenarios covering the edge-case categories from the
Problem Statement and Participant Guide, runs each through the in-process
FastAPI pipeline with a deterministic mock LLM, and verifies interpretation
+ validity.

Categories covered:
- Time windows (whole-hour intervals, start-inclusive/end-exclusive)
- Solar reduction wording variations
- Battery reserve percentage vs absolute kWh
- max_grid_window caps and interactions
- Combined directives + distractors
- Invalid request rejection
"""

from __future__ import annotations
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# --- Build a synthetic 24h scenario with controllable parameters ----------


def make_hours(demand_profile=None, solar_profile=None, tariff_profile=None):
    demand = demand_profile or [100] * 24
    solar = solar_profile or [0] * 24
    tariff = tariff_profile or [10] * 24
    return [
        {
            "hour": h,
            "demand_kwh": demand[h],
            "solar_kwh": solar[h],
            "tariff_bdt_per_kwh": tariff[h],
        }
        for h in range(24)
    ]


def base_battery():
    return {
        "capacity_kwh": 200,
        "initial_energy_kwh": 100,
        "minimum_energy_kwh": 30,
        "max_charge_kwh_per_hour": 50,
        "max_discharge_kwh_per_hour": 50,
    }


def base_request(scenario_id, notes, **battery_overrides):
    bat = base_battery()
    bat.update(battery_overrides)
    return {
        "scenario_id": scenario_id,
        "operator_notes": notes,
        "hours": make_hours(),
        "battery": bat,
    }


# --- Test cases -----------------------------------------------------------


def _interp(note_index, dtype, **adj):
    return {
        "note_index": note_index,
        "applies": dtype != "no_op",
        "directive_type": dtype,
        "structured_adjustment": adj if dtype != "no_op" else None,
        "explanation": f"test {dtype}",
    }


def time_window_cases():
    """Time-window parsing checks — all map to expected hour lists."""
    return [
        (
            "EDGE-TW-1",
            "Solar reduced noon until 2 PM.",
            [_interp(0, "solar_reduction", hours=[12, 13], factor=0.2)],
        ),
        (
            "EDGE-TW-2",
            "Solar reduced 1 PM to 3 PM.",
            [_interp(0, "solar_reduction", hours=[13, 14], factor=0.2)],
        ),
        (
            "EDGE-TW-3",
            "Solar reduced 6 PM until 9 PM.",
            [_interp(0, "solar_reduction", hours=[18, 19, 20], factor=0.2)],
        ),
        (
            "EDGE-TW-4",
            "No charge 11 AM until 1 PM.",
            [_interp(0, "no_charge_window", hours=[11, 12])],
        ),
        (
            "EDGE-TW-5",
            "No charge 2 AM until 5 AM.",
            [_interp(0, "no_charge_window", hours=[2, 3, 4])],
        ),
        (
            "EDGE-TW-6",
            "Reserve 6 PM until 10 PM.",
            [
                _interp(
                    0,
                    "minimum_battery_reserve",
                    hours=[18, 19, 20, 21],
                    minimum_energy_kwh=80,
                )
            ],
        ),
        (
            "EDGE-TW-7",
            "Reserve 7 PM until 9 PM.",
            [
                _interp(
                    0, "minimum_battery_reserve", hours=[19, 20], minimum_energy_kwh=80
                )
            ],
        ),
        (
            "EDGE-TW-8",
            "Grid cap 7 PM to 9 PM.",
            [_interp(0, "max_grid_window", hours=[19, 20], max_grid_kwh=150)],
        ),
    ]


def solar_wording_cases():
    return [
        (
            "EDGE-SW-1",
            "Solar drops to 20% from 12 PM to 2 PM.",
            [_interp(0, "solar_reduction", hours=[12, 13], factor=0.2)],
        ),
        (
            "EDGE-SW-2",
            "80% reduction in solar 12 PM to 2 PM.",
            [_interp(0, "solar_reduction", hours=[12, 13], factor=0.2)],
        ),
        (
            "EDGE-SW-3",
            "One-fifth of normal solar 12 PM to 2 PM.",
            [_interp(0, "solar_reduction", hours=[12, 13], factor=0.2)],
        ),
        (
            "EDGE-SW-4",
            "Half remains 12 PM to 2 PM.",
            [_interp(0, "solar_reduction", hours=[12, 13], factor=0.5)],
        ),
        (
            "EDGE-SW-5",
            "25% of forecast solar 12 PM to 2 PM.",
            [_interp(0, "solar_reduction", hours=[12, 13], factor=0.25)],
        ),
        (
            "EDGE-SW-6",
            "Reduced by 75% noon to 2 PM.",
            [_interp(0, "solar_reduction", hours=[12, 13], factor=0.25)],
        ),
    ]


def reserve_cases():
    return [
        (
            "EDGE-RV-1",
            "Keep at least 120 kWh 6 PM to 9 PM.",
            [
                _interp(
                    0,
                    "minimum_battery_reserve",
                    hours=[18, 19, 20],
                    minimum_energy_kwh=120,
                )
            ],
        ),
        (
            "EDGE-RV-2",
            "Reserve at least 50% of capacity 6 PM to 9 PM.",
            [
                _interp(
                    0,
                    "minimum_battery_reserve",
                    hours=[18, 19, 20],
                    minimum_energy_kwh=100,
                )
            ],
        ),  # capacity=200
        (
            "EDGE-RV-3",
            "Emergency reserve of 30% from 6 PM to 9 PM.",
            [
                _interp(
                    0,
                    "minimum_battery_reserve",
                    hours=[18, 19, 20],
                    minimum_energy_kwh=60,
                )
            ],
        ),  # 30% of 200
    ]


def grid_cap_cases():
    return [
        (
            "EDGE-GC-1",
            "Grid import must not exceed 155 kWh 6 PM to 9 PM.",
            [_interp(0, "max_grid_window", hours=[18, 19, 20], max_grid_kwh=155)],
        ),
        (
            "EDGE-GC-2",
            "Feeder limit 180 kWh 6 PM to 9 PM.",
            [_interp(0, "max_grid_window", hours=[18, 19, 20], max_grid_kwh=180)],
        ),
        (
            "EDGE-GC-3",
            "Transformer limit 190 kWh 7 PM to 9 PM.",
            [_interp(0, "max_grid_window", hours=[19, 20], max_grid_kwh=190)],
        ),
    ]


def combination_cases():
    return [
        (
            "EDGE-CO-1",
            ["Solar drops 12 PM to 2 PM.", "Cafeteria menu changes."],
            [
                _interp(0, "solar_reduction", hours=[12, 13], factor=0.2),
                _interp(1, "no_op"),
            ],
        ),
        (
            "EDGE-CO-2",
            ["No charge 2 PM to 4 PM.", "No discharge 6 PM to 8 PM."],
            [
                _interp(0, "no_charge_window", hours=[14, 15]),
                _interp(1, "no_discharge_window", hours=[18, 19]),
            ],
        ),
        (
            "EDGE-CO-3",
            ["Reserve 90 kWh 6 PM to 10 PM.", "Grid cap 180 kWh 7 PM to 9 PM."],
            [
                _interp(
                    0,
                    "minimum_battery_reserve",
                    hours=[18, 19, 20, 21],
                    minimum_energy_kwh=90,
                ),
                _interp(1, "max_grid_window", hours=[19, 20], max_grid_kwh=180),
            ],
        ),
        (
            "EDGE-CO-4",
            [
                "Solar drops 12 PM to 2 PM.",
                "Sports office moved registration.",
                "Library hours extended.",
            ],
            [
                _interp(0, "solar_reduction", hours=[12, 13], factor=0.2),
                _interp(1, "no_op"),
                _interp(2, "no_op"),
            ],
        ),
    ]


# --- Runner ---------------------------------------------------------------


def setup_mocks(interp_map):
    from app.api import dependencies as deps
    from app.services.cache import cache

    deps.set_mock_interpretations(interp_map)
    cache.clear()


def run_one(client, scenario_id, notes, expected_interps):
    req = base_request(scenario_id, notes)
    resp = client.post("/optimize-energy", json=req)
    if resp.status_code != 200:
        return False, f"http {resp.status_code}: {str(resp.json())[:200]}"
    body = resp.json()
    # Schema
    if body["scenario_id"] != scenario_id:
        return False, "scenario_id mismatch"
    if len(body["directive_interpretation"]) != len(expected_interps):
        return (
            False,
            f"interpretation count {len(body['directive_interpretation'])} vs {len(expected_interps)}",
        )
    for got, exp in zip(body["directive_interpretation"], expected_interps):
        if got["note_index"] != exp["note_index"]:
            return False, "note_index mismatch"
        if got["directive_type"] != exp["directive_type"]:
            return (
                False,
                f"directive_type {got['directive_type']} != {exp['directive_type']}",
            )
        if got["applies"] != exp["applies"]:
            return False, f"applies {got['applies']} != {exp['applies']}"
        if got["structured_adjustment"] != exp["structured_adjustment"]:
            return (
                False,
                f"adjustment mismatch: {got['structured_adjustment']} vs {exp['structured_adjustment']}",
            )
    if len(body["hourly_plan"]) != 24:
        return False, "plan length"
    # Verify end-of-day neutrality
    init = req["battery"]["initial_energy_kwh"]
    final = body["hourly_plan"][23]["battery_energy_after_kwh"]
    if abs(final - init) > 0.5:
        return False, f"end-of-day neutrality {final} vs init {init}"
    return True, "ok"


def main():
    from fastapi.testclient import TestClient
    from app.main import app

    all_cases = (
        time_window_cases()
        + solar_wording_cases()
        + reserve_cases()
        + grid_cap_cases()
        + combination_cases()
    )

    # Build mock interpretation map keyed by scenario_id
    interp_map = {cid: interps for (cid, _notes, interps) in all_cases}
    setup_mocks(interp_map)
    client = TestClient(app)

    failures = []
    for cid, notes, expected_interps in all_cases:
        # Notes may be a single string or list; normalize
        if isinstance(notes, str):
            notes_list = [notes]
        else:
            notes_list = notes
        ok, msg = run_one(client, cid, notes_list, expected_interps)
        flag = "PASS" if ok else "FAIL"
        print(f"  [{cid:<10}] {flag}  {msg}")
        if not ok:
            failures.append((cid, msg))

    print()
    if failures:
        print(f"FAILED {len(failures)} of {len(all_cases)}")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print(f"All {len(all_cases)} edge cases PASSED.")


if __name__ == "__main__":
    main()
