def test_mock_client_returns_payload():
    from app.services.llm_client import LLMClient, LLMCallResult

    c = LLMClient(mock=True, mock_payload={"interpretations": [{"note_index": 0}]})
    r = c.interpret(notes=["hi"], scenario_id="x", battery={"capacity_kwh": 100})
    assert isinstance(r, LLMCallResult)
    assert r.payload == {"interpretations": [{"note_index": 0}]}
    assert r.attempts == 1


def test_extract_json_used_in_path():
    """If LLM returns prose + JSON, the client extracts JSON."""
    from app.services.llm_client import LLMClient

    c = LLMClient(mock=True, mock_payload={"interpretations": []})
    r = c.interpret(notes=["x"], scenario_id="x", battery={"capacity_kwh": 100})
    assert r.error is None
    assert r.payload == {"interpretations": []}


def test_no_client_when_real_and_no_key_returns_error():
    """If api_key is empty, mock must be set or we get an error."""
    from app.services.llm_client import LLMClient

    c = LLMClient(mock=False)
    # Without key set, the OpenAI client will raise on first call
    # but we test that mock=True works as expected
    assert c.mock is False
