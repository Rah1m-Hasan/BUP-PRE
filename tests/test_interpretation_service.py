from app.services.interpretation_service import (
    InterpretationService,
    InterpretationError,
)


class _StubClient:
    def __init__(self, sequence):
        self.sequence = sequence
        self.calls = 0

    def interpret(self, notes, scenario_id, battery):
        r = self.sequence[self.calls]
        self.calls += 1

        class _R:
            pass

        o = _R()
        o.payload = r.get("payload")
        o.raw_text = ""
        o.attempts = 1
        o.error = r.get("error")
        return o


def test_happy_path_no_retry():
    svc = InterpretationService(
        llm_client=_StubClient(
            [
                {
                    "payload": {
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
                }
            ]
        )
    )
    out = svc.interpret(
        scenario_id="x",
        notes=["menu"],
        battery={
            "capacity_kwh": 100,
            "initial_energy_kwh": 0,
            "minimum_energy_kwh": 0,
            "max_charge_kwh_per_hour": 1,
            "max_discharge_kwh_per_hour": 1,
        },
    )
    assert len(out["interpretations"]) == 1


def test_repair_retry_on_guardrail_failure():
    svc = InterpretationService(
        llm_client=_StubClient(
            [
                {
                    "payload": {
                        "interpretations": [
                            {
                                "note_index": 0,
                                "applies": True,
                                "directive_type": "no_op",
                                "structured_adjustment": {"hours": [0]},
                                "explanation": "bad",
                            }
                        ]
                    }
                },
                {
                    "payload": {
                        "interpretations": [
                            {
                                "note_index": 0,
                                "applies": False,
                                "directive_type": "no_op",
                                "structured_adjustment": None,
                                "explanation": "ok",
                            }
                        ]
                    }
                },
            ]
        )
    )
    out = svc.interpret(
        scenario_id="x",
        notes=["x"],
        battery={
            "capacity_kwh": 100,
            "initial_energy_kwh": 0,
            "minimum_energy_kwh": 0,
            "max_charge_kwh_per_hour": 1,
            "max_discharge_kwh_per_hour": 1,
        },
    )
    assert out["interpretations"][0]["directive_type"] == "no_op"


def test_exhausts_retries_then_raises():
    svc = InterpretationService(
        llm_client=_StubClient(
            [
                {"payload": {"interpretations": []}, "error": "boom"},
                {"payload": {"interpretations": []}, "error": "boom"},
                {"payload": {"interpretations": []}, "error": "boom"},
                {"payload": {"interpretations": []}, "error": "boom"},
            ]
        ),
        max_attempts=3,
    )
    try:
        svc.interpret(
            scenario_id="x",
            notes=["x"],
            battery={
                "capacity_kwh": 100,
                "initial_energy_kwh": 0,
                "minimum_energy_kwh": 0,
                "max_charge_kwh_per_hour": 1,
                "max_discharge_kwh_per_hour": 1,
            },
        )
        assert False, "should have raised"
    except InterpretationError as e:
        assert "failed" in str(e)
