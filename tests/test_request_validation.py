import pytest
from pydantic import ValidationError

from app.schemas.request_models import OptimizeEnergyRequest


def _valid_payload():
    return {
        "scenario_id": "TEST-01",
        "operator_notes": ["Some note."],
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


def test_valid_payload_ok():
    OptimizeEnergyRequest.model_validate(_valid_payload())


def test_hours_must_be_24():
    payload = _valid_payload()
    payload["hours"] = payload["hours"][:23]
    with pytest.raises(ValidationError):
        OptimizeEnergyRequest.model_validate(payload)


def test_operator_notes_1_to_3():
    payload = _valid_payload()
    payload["operator_notes"] = []
    with pytest.raises(ValidationError):
        OptimizeEnergyRequest.model_validate(payload)


def test_operator_notes_max_3():
    payload = _valid_payload()
    payload["operator_notes"] = ["a", "b", "c", "d"]
    with pytest.raises(ValidationError):
        OptimizeEnergyRequest.model_validate(payload)


def test_duplicate_hour_rejected():
    payload = _valid_payload()
    payload["hours"][5] = {**payload["hours"][5], "hour": 0}
    with pytest.raises(ValidationError):
        OptimizeEnergyRequest.model_validate(payload)


def test_hour_out_of_range_rejected():
    payload = _valid_payload()
    payload["hours"][10] = {**payload["hours"][10], "hour": 24}
    with pytest.raises(ValidationError):
        OptimizeEnergyRequest.model_validate(payload)


def test_negative_demand_rejected():
    payload = _valid_payload()
    payload["hours"][10] = {**payload["hours"][10], "demand_kwh": -1}
    with pytest.raises(ValidationError):
        OptimizeEnergyRequest.model_validate(payload)


def test_empty_note_rejected():
    payload = _valid_payload()
    payload["operator_notes"] = [""]
    with pytest.raises(ValidationError):
        OptimizeEnergyRequest.model_validate(payload)


def test_initial_exceeds_capacity_rejected():
    payload = _valid_payload()
    payload["battery"]["initial_energy_kwh"] = 9999
    with pytest.raises(ValidationError):
        OptimizeEnergyRequest.model_validate(payload)


def test_extra_field_rejected():
    payload = _valid_payload()
    payload["rogue"] = "x"
    with pytest.raises(ValidationError):
        OptimizeEnergyRequest.model_validate(payload)
