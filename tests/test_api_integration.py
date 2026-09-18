import json
from pathlib import Path

from fastapi.testclient import TestClient

CASES = json.loads(
    Path("BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json").read_text()
)["cases"]


def _setup_mocks():
    from app.api import dependencies as deps
    from app.main import app
    from app.services.cache import cache

    deps.set_mock_interpretations(
        {c["id"]: c["expected_output"]["directive_interpretation"] for c in CASES}
    )
    cache.clear()
    return TestClient(app)


def test_health():
    c = _setup_mocks()
    r = c.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_malformed_json_returns_400():
    c = _setup_mocks()
    r = c.post(
        "/optimize-energy",
        data="{not json",
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 400


def test_missing_fields_returns_400_or_422():
    c = _setup_mocks()
    r = c.post("/optimize-energy", json={"scenario_id": "x"})
    assert r.status_code in (400, 422)


def test_all_public_samples_pass_mock():
    c = _setup_mocks()
    for case in CASES:
        r = c.post("/optimize-energy", json=case["input"])
        assert r.status_code == 200, f"{case['id']}: {r.status_code} {r.text[:200]}"
        body = r.json()
        # Schema
        assert body["scenario_id"] == case["input"]["scenario_id"]
        assert len(body["directive_interpretation"]) == len(
            case["input"]["operator_notes"]
        )
        assert len(body["hourly_plan"]) == 24
        # Interpretation matches
        ref = case["expected_output"]["directive_interpretation"]
        for got, exp in zip(body["directive_interpretation"], ref):
            assert got["note_index"] == exp["note_index"]
            assert got["applies"] == exp["applies"]
            assert got["directive_type"] == exp["directive_type"]
            assert got["structured_adjustment"] == exp["structured_adjustment"]
        # Cost close to reference (within 1%)
        ref_cost = case["expected_output"]["total_cost_bdt"]
        if ref_cost > 0:
            assert (
                abs(body["total_cost_bdt"] - ref_cost) / ref_cost <= 0.02
            ), f"{case['id']}: cost {body['total_cost_bdt']} vs ref {ref_cost}"


def test_directive_interpretation_in_note_index_order():
    c = _setup_mocks()
    case = CASES[5]  # SAMPLE-06 with 3 notes
    r = c.post("/optimize-energy", json=case["input"])
    assert r.status_code == 200
    body = r.json()
    for i, e in enumerate(body["directive_interpretation"]):
        assert e["note_index"] == i


def test_repeated_request_is_stable():
    c = _setup_mocks()
    case = CASES[0]
    r1 = c.post("/optimize-energy", json=case["input"])
    r2 = c.post("/optimize-energy", json=case["input"])
    assert r1.status_code == 200
    assert r2.status_code == 200
    b1 = r1.json()
    b2 = r2.json()
    # Plans may differ in detail but cost should match within tolerance
    assert abs(b1["total_cost_bdt"] - b2["total_cost_bdt"]) < 0.5
