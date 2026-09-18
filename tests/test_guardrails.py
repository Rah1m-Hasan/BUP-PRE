import pytest

from app.services.guardrails import GuardrailError, validate_interpretation

NOTES = [
    "Do not charge the battery between 2 PM and 4 PM.",
    "The cafeteria menu changes tomorrow.",
]
BATTERY = {
    "capacity_kwh": 200,
    "initial_energy_kwh": 100,
    "minimum_energy_kwh": 30,
    "max_charge_kwh_per_hour": 50,
    "max_discharge_kwh_per_hour": 50,
}


def _good():
    return {
        "interpretations": [
            {
                "note_index": 0,
                "applies": True,
                "directive_type": "no_charge_window",
                "structured_adjustment": {"hours": [14, 15]},
                "explanation": "Maintenance",
            },
            {
                "note_index": 1,
                "applies": False,
                "directive_type": "no_op",
                "structured_adjustment": None,
                "explanation": "irrelevant",
            },
        ]
    }


def test_valid_payload_passes():
    validate_interpretation(_good(), NOTES, BATTERY)


def test_wrong_count_rejected():
    bad = _good()
    bad["interpretations"] = bad["interpretations"][:1]
    with pytest.raises(GuardrailError):
        validate_interpretation(bad, NOTES, BATTERY)


def test_duplicate_note_index_rejected():
    bad = _good()
    bad["interpretations"][1]["note_index"] = 0
    with pytest.raises(GuardrailError):
        validate_interpretation(bad, NOTES, BATTERY)


def test_no_op_with_applies_true_rejected():
    bad = _good()
    bad["interpretations"][1]["applies"] = True
    with pytest.raises(GuardrailError):
        validate_interpretation(bad, NOTES, BATTERY)


def test_no_op_must_have_null_adjustment():
    bad = _good()
    bad["interpretations"][1]["structured_adjustment"] = {"hours": [0]}
    with pytest.raises(GuardrailError):
        validate_interpretation(bad, NOTES, BATTERY)


def test_non_no_op_requires_adjustment():
    bad = _good()
    bad["interpretations"][0]["structured_adjustment"] = None
    with pytest.raises(GuardrailError):
        validate_interpretation(bad, NOTES, BATTERY)


def test_invalid_directive_type_rejected():
    bad = _good()
    bad["interpretations"][0]["directive_type"] = "freeze_battery"
    with pytest.raises(GuardrailError):
        validate_interpretation(bad, NOTES, BATTERY)


def test_hours_unsorted_rejected():
    bad = _good()
    bad["interpretations"][0]["structured_adjustment"]["hours"] = [15, 14]
    with pytest.raises(GuardrailError):
        validate_interpretation(bad, NOTES, BATTERY)


def test_hours_out_of_range_rejected():
    bad = _good()
    bad["interpretations"][0]["structured_adjustment"]["hours"] = [25]
    with pytest.raises(GuardrailError):
        validate_interpretation(bad, NOTES, BATTERY)


def test_solar_factor_out_of_range_rejected():
    p = {
        "interpretations": [
            {
                "note_index": 0,
                "applies": True,
                "directive_type": "solar_reduction",
                "structured_adjustment": {"hours": [13, 14], "factor": 1.2},
                "explanation": "x",
            }
        ]
    }
    with pytest.raises(GuardrailError):
        validate_interpretation(p, ["x"], BATTERY)


def test_reserve_above_capacity_rejected():
    p = {
        "interpretations": [
            {
                "note_index": 0,
                "applies": True,
                "directive_type": "minimum_battery_reserve",
                "structured_adjustment": {"hours": [18], "minimum_energy_kwh": 300},
                "explanation": "x",
            }
        ]
    }
    with pytest.raises(GuardrailError):
        validate_interpretation(p, ["x"], BATTERY)


def test_max_grid_negative_rejected():
    p = {
        "interpretations": [
            {
                "note_index": 0,
                "applies": True,
                "directive_type": "max_grid_window",
                "structured_adjustment": {"hours": [18], "max_grid_kwh": -1},
                "explanation": "x",
            }
        ]
    }
    with pytest.raises(GuardrailError):
        validate_interpretation(p, ["x"], BATTERY)


def test_empty_explanation_rejected():
    bad = _good()
    bad["interpretations"][0]["explanation"] = ""
    with pytest.raises(GuardrailError):
        validate_interpretation(bad, NOTES, BATTERY)


def test_minimum_reserve_negative_rejected():
    p = {
        "interpretations": [
            {
                "note_index": 0,
                "applies": True,
                "directive_type": "minimum_battery_reserve",
                "structured_adjustment": {"hours": [18], "minimum_energy_kwh": -5},
                "explanation": "x",
            }
        ]
    }
    with pytest.raises(GuardrailError):
        validate_interpretation(p, ["x"], BATTERY)


def test_duplicate_hours_rejected():
    p = {
        "interpretations": [
            {
                "note_index": 0,
                "applies": True,
                "directive_type": "no_charge_window",
                "structured_adjustment": {"hours": [10, 10, 11]},
                "explanation": "x",
            }
        ]
    }
    with pytest.raises(GuardrailError):
        validate_interpretation(p, ["x"], BATTERY)
