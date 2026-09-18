def test_settings_defaults():
    from app.core.config import Settings

    s = Settings()
    assert s.groq_base_url == "https://api.groq.com/openai/v1"
    assert s.llm_model == "openai/gpt-oss-120b"
    assert s.llm_temperature == 0
    assert s.llm_timeout_seconds == 10
    assert s.llm_max_retries == 2
    assert s.llm_mock is False
    assert s.app_host == "0.0.0.0"
    assert s.app_port == 8000
    # reasoning_effort defaults to "low" for the default reasoning model.
    assert s.llm_reasoning_effort == "low"
