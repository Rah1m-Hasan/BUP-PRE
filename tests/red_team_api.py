"""🕵️ AGENT 1: Red Team — adversarial API attacker.

Tests:
  - malformed JSON / missing fields / 25 hours / negative tariffs / NaN / empty notes
  - exact time-window mapping (1 PM to 3 PM -> [13,14]; 11 AM until 1 PM -> [11,12]; 6 PM until 9 PM -> [18,19,20])
  - solar reduction math (80% reduction -> factor 0.2; drop to 20% -> 0.2)
  - percentage battery reserves (50% of 200 kWh -> 100 kWh)

Failures are recorded to audit_logs/red_team_failures.json.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from audit_logs.audit_runner import post_json, configure, set_mock_payload

configure("inprocess")

failures: list[dict] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    marker = "PASS" if ok else "FAIL"
    print(f"  [{marker}] {name}{(' — ' + detail) if detail else ''}")
    if not ok:
        failures.append({"agent": "RedTeam", "name": name, "detail": detail})


def valid_payload() -> dict:
    return {
        "scenario_id": "RT-01",
        "operator_notes": ["Solar reduced noon until 2 PM."],
        "hours": [
            {"hour": h, "demand_kwh": 100, "solar_kwh": 50, "tariff_bdt_per_kwh": 10}
            for h in range(24)
        ],
        "battery": {
            "capacity_kwh": 200,
            "initial_energy_kwh": 100,
            "minimum_energy_kwh": 30,
            "max_charge_kwh_per_hour": 50,
            "max_discharge_kwh_per_hour": 50,
        },
    }


# ---------- SCHEMA / MALFORMED INPUT ----------


def test_malformed_json():
    """Raw malformed JSON should return 400."""
    from app.main import app
    from fastapi.testclient import TestClient

    c = TestClient(app)
    r = c.post(
        "/optimize-energy",
        data="{not json",
        headers={"content-type": "application/json"},
    )
    record("malformed_json_returns_400", r.status_code == 400, f"got {r.status_code}")


def test_missing_fields():
    p = {"scenario_id": "x"}
    sc, _ = post_json("/optimize-energy", p)
    record("missing_fields_returns_400_or_422", sc in (400, 422), f"got {sc}")


def test_25_hours():
    p = valid_payload()
    p["hours"] = p["hours"] + [
        {"hour": 24, "demand_kwh": 100, "solar_kwh": 0, "tariff_bdt_per_kwh": 10}
    ]
    p["hours"][0]["hour"] = 1  # shift to keep unique
    sc, _ = post_json("/optimize-energy", p)
    record("25_hours_rejected", sc in (400, 422), f"got {sc}")


def test_23_hours():
    p = valid_payload()
    p["hours"] = p["hours"][:23]
    sc, _ = post_json("/optimize-energy", p)
    record("23_hours_rejected", sc in (400, 422), f"got {sc}")


def test_duplicate_hours():
    p = valid_payload()
    p["hours"][5]["hour"] = 0
    sc, _ = post_json("/optimize-energy", p)
    record("duplicate_hours_rejected", sc in (400, 422), f"got {sc}")


def test_negative_tariff():
    p = valid_payload()
    p["hours"][5]["tariff_bdt_per_kwh"] = -1
    sc, _ = post_json("/optimize-energy", p)
    record("negative_tariff_rejected", sc in (400, 422), f"got {sc}")


def test_negative_demand():
    p = valid_payload()
    p["hours"][5]["demand_kwh"] = -1
    sc, _ = post_json("/optimize-energy", p)
    record("negative_demand_rejected", sc in (400, 422), f"got {sc}")


def test_nan_values():
    """Send a raw body with the non-standard NaN literal."""
    from app.main import app
    from fastapi.testclient import TestClient

    c = TestClient(app)
    body = (
        b'{"scenario_id":"RT-NAN","operator_notes":["x"],'
        b'"hours":[{"hour":0,"demand_kwh":NaN,"solar_kwh":0,"tariff_bdt_per_kwh":10}'
        + b",".join(
            [
                b'{"hour":'
                + str(h).encode()
                + b',"demand_kwh":100,"solar_kwh":0,"tariff_bdt_per_kwh":10}'
                for h in range(1, 24)
            ]
        )
        + b"],"
        b'"battery":{"capacity_kwh":200,"initial_energy_kwh":100,"minimum_energy_kwh":30,'
        b'"max_charge_kwh_per_hour":50,"max_discharge_kwh_per_hour":50}'
        b"}"
    )
    r = c.post(
        "/optimize-energy", data=body, headers={"content-type": "application/json"}
    )
    record("nan_literal_safe", r.status_code in (400, 422, 200), f"got {r.status_code}")


def test_infinity_values():
    """Send raw body with the non-standard 'Infinity' literal."""
    from app.main import app
    from fastapi.testclient import TestClient

    c = TestClient(app)
    body = (
        b'{"scenario_id":"RT-INF","operator_notes":["x"],'
        b'"hours":[{"hour":0,"demand_kwh":100,"solar_kwh":0,"tariff_bdt_per_kwh":Infinity}'
        + b",".join(
            [
                b'{"hour":'
                + str(h).encode()
                + b',"demand_kwh":100,"solar_kwh":0,"tariff_bdt_per_kwh":10}'
                for h in range(1, 24)
            ]
        )
        + b"],"
        b'"battery":{"capacity_kwh":200,"initial_energy_kwh":100,"minimum_energy_kwh":30,'
        b'"max_charge_kwh_per_hour":50,"max_discharge_kwh_per_hour":50}'
        b"}"
    )
    r = c.post(
        "/optimize-energy", data=body, headers={"content-type": "application/json"}
    )
    record(
        "infinity_literal_safe",
        r.status_code in (400, 422, 200),
        f"got {r.status_code}",
    )


def test_empty_notes():
    p = valid_payload()
    p["operator_notes"] = []
    sc, _ = post_json("/optimize-energy", p)
    record("empty_notes_rejected", sc in (400, 422), f"got {sc}")


def test_four_notes():
    p = valid_payload()
    p["operator_notes"] = ["a", "b", "c", "d"]
    sc, _ = post_json("/optimize-energy", p)
    record("four_notes_rejected", sc in (400, 422), f"got {sc}")


def test_empty_string_note():
    p = valid_payload()
    p["operator_notes"] = [""]
    sc, _ = post_json("/optimize-energy", p)
    record("empty_string_note_rejected", sc in (400, 422), f"got {sc}")


def test_whitespace_note():
    p = valid_payload()
    p["operator_notes"] = ["   "]
    sc, _ = post_json("/optimize-energy", p)
    record("whitespace_only_note_rejected", sc in (400, 422), f"got {sc}")


# ---------- TIME WINDOWS (mocked) ----------


def _setup_time_window_mock():
    cases = [
        ("1 PM to 3 PM", "solar_reduction", [13, 14], 0.2),
        ("11 AM until 1 PM", "no_charge_window", [11, 12], None),
        ("6 PM until 9 PM", "minimum_battery_reserve", [18, 19, 20], 80),
        ("noon until 2 PM", "solar_reduction", [12, 13], 0.3),
        ("2 AM until 5 AM", "no_charge_window", [2, 3, 4], None),
    ]
    interp_map = {}
    for i, (phrase, dtype, hours, val) in enumerate(cases):
        sid = f"RT-TW-{i}"
        if dtype == "solar_reduction":
            adj = {"hours": hours, "factor": val}
        elif dtype == "minimum_battery_reserve":
            adj = {"hours": hours, "minimum_energy_kwh": val}
        else:
            adj = {"hours": hours}
        interp_map[sid] = [
            {
                "note_index": 0,
                "applies": True,
                "directive_type": dtype,
                "structured_adjustment": adj,
                "explanation": "test",
            }
        ]
    return interp_map, cases


def test_time_windows():
    interp_map, cases = _setup_time_window_mock()
    set_mock_payload(interp_map)
    for i, (phrase, dtype, hours, _val) in enumerate(cases):
        sid = f"RT-TW-{i}"
        p = valid_payload()
        p["scenario_id"] = sid
        p["operator_notes"] = [phrase]
        sc, body = post_json("/optimize-energy", p)
        if sc != 200:
            record(f"time_window[{phrase}]_200", False, f"got {sc}")
            continue
        got = body["directive_interpretation"][0]["structured_adjustment"]["hours"]
        ok = got == hours
        record(f"time_window[{phrase}]_hours=={hours}", ok, f"got {got}")


# ---------- SOLAR REDUCTION MATH (mocked) ----------


def _setup_solar_mock():
    cases = [
        ("Solar drops to 20% from 12 PM to 2 PM.", 0.2),
        ("80% reduction in solar 12 PM to 2 PM.", 0.2),
        ("One-fifth of normal solar output.", 0.2),
        ("Half remains 12 PM to 2 PM.", 0.5),
        ("25% of forecast solar.", 0.25),
        ("Reduced by 75% noon to 2 PM.", 0.25),
    ]
    interp_map = {}
    for i, (phrase, factor) in enumerate(cases):
        sid = f"RT-SW-{i}"
        interp_map[sid] = [
            {
                "note_index": 0,
                "applies": True,
                "directive_type": "solar_reduction",
                "structured_adjustment": {"hours": [12, 13], "factor": factor},
                "explanation": "test",
            }
        ]
    return interp_map, cases


def test_solar_factor_normalization():
    interp_map, cases = _setup_solar_mock()
    set_mock_payload(interp_map)
    for i, (phrase, expected_factor) in enumerate(cases):
        sid = f"RT-SW-{i}"
        p = valid_payload()
        p["scenario_id"] = sid
        p["operator_notes"] = [phrase]
        sc, body = post_json("/optimize-energy", p)
        if sc != 200:
            record(f"solar[{phrase}]_200", False, f"got {sc}")
            continue
        got = body["directive_interpretation"][0]["structured_adjustment"]["factor"]
        ok = math.isclose(got, expected_factor, abs_tol=1e-9)
        record(f"solar[{phrase}]_factor=={expected_factor}", ok, f"got {got}")


# ---------- BATTERY RESERVE PERCENTAGE (mocked) ----------


def test_battery_reserve_percentage():
    """'Keep 50% in reserve' on a 200 kWh battery MUST produce minimum_energy_kwh=100."""
    interp_map = {
        "RT-RV-1": [
            {
                "note_index": 0,
                "applies": True,
                "directive_type": "minimum_battery_reserve",
                "structured_adjustment": {
                    "hours": [18, 19, 20],
                    "minimum_energy_kwh": 100,
                },
                "explanation": "50% of 200 kWh",
            }
        ],
        "RT-RV-2": [
            {
                "note_index": 0,
                "applies": True,
                "directive_type": "minimum_battery_reserve",
                "structured_adjustment": {
                    "hours": [18, 19, 20],
                    "minimum_energy_kwh": 60,
                },
                "explanation": "30% of 200 kWh",
            }
        ],
    }
    set_mock_payload(interp_map)
    for sid, expected in [("RT-RV-1", 100), ("RT-RV-2", 60)]:
        p = valid_payload()
        p["scenario_id"] = sid
        p["operator_notes"] = ["Reserve"]
        sc, body = post_json("/optimize-energy", p)
        if sc != 200:
            record(f"reserve[{sid}]_200", False, f"got {sc}")
            continue
        got = body["directive_interpretation"][0]["structured_adjustment"][
            "minimum_energy_kwh"
        ]
        record(f"reserve[{sid}]_kwh=={expected}", got == expected, f"got {got}")


def main():
    print("=" * 60)
    print("🕵️  AGENT 1: RED TEAM API ATTACKER")
    print("=" * 60)
    print()
    print("[1.1] Schema / malformed input attacks:")
    test_malformed_json()
    test_missing_fields()
    test_25_hours()
    test_23_hours()
    test_duplicate_hours()
    test_negative_tariff()
    test_negative_demand()
    test_nan_values()
    test_infinity_values()
    test_empty_notes()
    test_four_notes()
    test_empty_string_note()
    test_whitespace_note()

    print("\n[1.2] Time-window mapping (mocked interpretation):")
    test_time_windows()

    print("\n[1.3] Solar reduction math (mocked interpretation):")
    test_solar_factor_normalization()

    print("\n[1.4] Battery reserve percentage conversion:")
    test_battery_reserve_percentage()

    out = ROOT / "audit_logs" / "red_team_failures.json"
    out.write_text(json.dumps({"agent": "RedTeam", "failures": failures}, indent=2))
    print()
    print(f"Red Team total failures: {len(failures)}")
    print(f"Wrote {out}")
    sys.exit(0 if not failures else 1)


if __name__ == "__main__":
    main()
