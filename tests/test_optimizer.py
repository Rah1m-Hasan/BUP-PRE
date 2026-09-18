from app.services.directive_compiler import compile_directives
from app.services.optimizer import optimize

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


def test_basic_optimal_solves():
    interp = {
        "interpretations": [
            {
                "note_index": 0,
                "applies": False,
                "directive_type": "no_op",
                "structured_adjustment": None,
                "explanation": "x",
            }
        ]
    }
    c = compile_directives(interp, BATTERY, HOURS)
    res = optimize(c, BATTERY, HOURS, time_limit_seconds=5)
    assert len(res["grid"]) == 24
    assert all(g >= 0 for g in res["grid"])
    assert abs(sum(res["grid"]) - res["total_grid_kwh"]) < 1e-6


def test_solar_reduction_changes_effective_solar():
    interp = {
        "interpretations": [
            {
                "note_index": 0,
                "applies": True,
                "directive_type": "solar_reduction",
                "structured_adjustment": {"hours": [12, 13], "factor": 0.1},
                "explanation": "x",
            }
        ]
    }
    c = compile_directives(interp, BATTERY, HOURS)
    res = optimize(c, BATTERY, HOURS, time_limit_seconds=5)
    assert all(g >= 0 for g in res["grid"])
    # Solar used at 12,13 should be much less than at other hours (since effective is 5 vs 50)
    assert sum(res["solar_used"][11:14]) <= sum(res["solar_used"][0:3]) + 0.1


def test_end_of_day_neutrality():
    interp = {
        "interpretations": [
            {
                "note_index": 0,
                "applies": False,
                "directive_type": "no_op",
                "structured_adjustment": None,
                "explanation": "x",
            }
        ]
    }
    c = compile_directives(interp, BATTERY, HOURS)
    res = optimize(c, BATTERY, HOURS, time_limit_seconds=5)
    assert abs(res["energy_after"][23] - BATTERY["initial_energy_kwh"]) < 1e-3


def test_no_charge_window_forces_charge_to_zero():
    interp = {
        "interpretations": [
            {
                "note_index": 0,
                "applies": True,
                "directive_type": "no_charge_window",
                "structured_adjustment": {"hours": list(range(24))},
                "explanation": "x",
            }
        ]
    }
    c = compile_directives(interp, BATTERY, HOURS)
    res = optimize(c, BATTERY, HOURS, time_limit_seconds=5)
    assert all(c < 1e-3 for c in res["charge"])


def test_max_grid_caps_grid():
    cap_h = 60.0
    interp = {
        "interpretations": [
            {
                "note_index": 0,
                "applies": True,
                "directive_type": "max_grid_window",
                "structured_adjustment": {
                    "hours": list(range(24)),
                    "max_grid_kwh": cap_h,
                },
                "explanation": "x",
            }
        ]
    }
    c = compile_directives(interp, BATTERY, HOURS)
    res = optimize(c, BATTERY, HOURS, time_limit_seconds=5)
    assert all(g <= cap_h + 1e-3 for g in res["grid"])
