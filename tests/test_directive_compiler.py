from app.services.directive_compiler import compile_directives

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
            "applies": True,
            "directive_type": "minimum_battery_reserve",
            "structured_adjustment": {"hours": [18, 19, 20], "minimum_energy_kwh": 120},
            "explanation": "x",
        },
        {
            "note_index": 2,
            "applies": True,
            "directive_type": "no_charge_window",
            "structured_adjustment": {"hours": [14, 15]},
            "explanation": "x",
        },
        {
            "note_index": 3,
            "applies": True,
            "directive_type": "no_discharge_window",
            "structured_adjustment": {"hours": [17, 18]},
            "explanation": "x",
        },
        {
            "note_index": 4,
            "applies": True,
            "directive_type": "max_grid_window",
            "structured_adjustment": {"hours": [19, 20], "max_grid_kwh": 150},
            "explanation": "x",
        },
        {
            "note_index": 5,
            "applies": False,
            "directive_type": "no_op",
            "structured_adjustment": None,
            "explanation": "x",
        },
    ]
}


def test_compile_all():
    c = compile_directives(INTERP, BATTERY, HOURS)
    assert c.effective_solar[12] == 50 * 0.2
    assert c.effective_solar[13] == 50 * 0.2
    assert c.effective_solar[0] == 50
    assert c.active_minimum[18] == 120
    assert c.active_minimum[0] == 30
    assert 14 in c.no_charge_hours and 15 in c.no_charge_hours
    assert 17 in c.no_discharge_hours and 18 in c.no_discharge_hours
    assert c.max_grid[19] == 150 and c.max_grid[20] == 150


def test_max_grid_takes_tightest_cap():
    p = {
        "interpretations": [
            {
                "note_index": 0,
                "applies": True,
                "directive_type": "max_grid_window",
                "structured_adjustment": {"hours": [18], "max_grid_kwh": 200},
                "explanation": "x",
            },
            {
                "note_index": 1,
                "applies": True,
                "directive_type": "max_grid_window",
                "structured_adjustment": {"hours": [18], "max_grid_kwh": 150},
                "explanation": "x",
            },
        ]
    }
    c = compile_directives(p, BATTERY, HOURS)
    assert c.max_grid[18] == 150
