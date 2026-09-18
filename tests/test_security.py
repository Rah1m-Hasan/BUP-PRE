def test_redact_secret_like():
    from app.core.security import redact, is_secret_like

    assert is_secret_like("sk-abcdefghijklmnopqrstuv")
    assert is_secret_like("Bearer xyz")
    assert redact("sk-abc") == "***REDACTED***"
    assert redact("short") == "short"


def test_safe_headers_redacts_auth():
    from app.core.security import safe_headers

    h = safe_headers({"Authorization": "Bearer abc", "X-Foo": "bar"})
    assert h["Authorization"] == "***REDACTED***"
    assert h["X-Foo"] == "bar"
