import pytest

from app.services.directive_compiler import compile_directives
from app.services.plan_builder import build_plan
from app.services.replay_validator import replay_validate, ReplayError

HOURS = [
    {"hour": h, "demand_kwh": 100, "solar_kwh": 50, "tariff_bdt_per_kwh": 10}
    for h in range(24)
]
BATTERY = {
    "capacity_kwh": 200,
    "initial_energy_kwh": 100,
    "minimum_energy_kwh": 30,
    "max_charge_kwh_per_hour": 50,
    "max_discharge_kwh_per_hour": 50,
}
INTERP = {
    "interpretations": [
        {
            "note_index": 0,
            "applies": True,
            "directive_type": "solar_reduction",
            "structured_adjustment": {"hours": [12, 13], "factor": 0.2},
            "explanation": "x",
        },
        {
            "note_index": 1,
            "applies": False,
            "directive_type": "no_op",
            "structured_adjustment": None,
            "explanation": "x",
        },
    ]
}

# Note: solar_reduction directive makes effective_solar[12]=10, so use 10 across the board
OPT = {
    "grid": [90.0] * 24,
    "solar_used": [10.0] * 24,
    "charge": [0.0] * 24,
    "discharge": [0.0] * 24,
    "energy_after": [100.0] * 24,
    "total_grid_kwh": 2160.0,
    "total_cost_bdt": 21600.0,
}
PLAN = build_plan(OPT, HOURS)
COMPILED = compile_directives(INTERP, BATTERY, HOURS)


def test_basic_passes():
    replay_validate(PLAN, HOURS, BATTERY, COMPILED, INTERP, "x")


def test_balance_violation_detected():
    bad = [dict(p) for p in PLAN]
    bad[0] = {**bad[0], "grid_kwh": bad[0]["grid_kwh"] + 5}
    with pytest.raises(ReplayError):
        replay_validate(bad, HOURS, BATTERY, COMPILED, INTERP, "x")


def test_final_neutrality_violation_detected():
    bad = [dict(p) for p in PLAN]
    bad[23] = {**bad[23], "battery_energy_after_kwh": 150}
    with pytest.raises(ReplayError):
        replay_validate(bad, HOURS, BATTERY, COMPILED, INTERP, "x")


def test_idle_must_have_zero_kwh():
    bad = [dict(p) for p in PLAN]
    bad[0] = {**bad[0], "battery_action": "idle", "battery_kwh": 1.0}
    with pytest.raises(ReplayError):
        replay_validate(bad, HOURS, BATTERY, COMPILED, INTERP, "x")


def test_plan_length_violation():
    with pytest.raises(ReplayError):
        replay_validate(PLAN[:10], HOURS, BATTERY, COMPILED, INTERP, "x")
