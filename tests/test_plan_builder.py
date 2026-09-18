from app.services.plan_builder import build_plan, recompute_totals
from app.services.summary_service import build_summary

OPT = {
    "grid": [100.0] * 24,
    "solar_used": [0.0] * 24,
    "charge": [0.0] * 24,
    "discharge": [0.0] * 24,
    "energy_after": [100.0] * 24,
    "total_grid_kwh": 2400.0,
    "total_cost_bdt": 24000.0,
}
HOURS = [
    {"hour": h, "demand_kwh": 100, "solar_kwh": 0, "tariff_bdt_per_kwh": 10}
    for h in range(24)
]
INTERP = {
    "interpretations": [
        {
            "note_index": 0,
            "applies": False,
            "directive_type": "no_op",
            "structured_adjustment": None,
            "explanation": "ignored",
        }
    ]
}


def test_build_plan_basic():
    plan = build_plan(OPT, HOURS)
    assert len(plan) == 24
    assert plan[0]["hour"] == 0
    assert plan[23]["hour"] == 23
    for e in plan:
        assert e["battery_action"] in ("charge", "discharge", "idle")
        assert e["battery_kwh"] >= 0


def test_recompute_totals():
    plan = build_plan(OPT, HOURS)
    tg, tc, pk = recompute_totals(plan, HOURS)
    assert tg == 2400.0
    assert tc == 24000.0
    assert pk == 100.0


def test_summary_includes_no_op_note():
    s = build_summary(INTERP, OPT)
    assert "Ignored" in s or "ignored" in s or "no_op" in s


def test_summary_describes_solar_reduction():
    p = {
        "interpretations": [
            {
                "note_index": 0,
                "applies": True,
                "directive_type": "solar_reduction",
                "structured_adjustment": {"hours": [12, 13], "factor": 0.2},
                "explanation": "x",
            }
        ]
    }
    s = build_summary(p, OPT)
    assert "solar" in s.lower()
    assert "0.2" in s


def test_summary_describes_reserve():
    p = {
        "interpretations": [
            {
                "note_index": 0,
                "applies": True,
                "directive_type": "minimum_battery_reserve",
                "structured_adjustment": {
                    "hours": [18, 19, 20],
                    "minimum_energy_kwh": 120,
                },
                "explanation": "x",
            }
        ]
    }
    s = build_summary(p, OPT)
    assert "reserve" in s.lower() or "battery" in s.lower()
    assert "120" in s
