"""Secret redaction utilities. Never log or echo secrets."""

REDACT = "***REDACTED***"

# Common secret prefixes / shapes
_SECRET_PREFIXES = ("sk-", "sk_", "bearer ", "authorization:", "api-key:")


def is_secret_like(value: str) -> bool:
    if not value:
        return False
    s = str(value).strip().lower()
    return any(s.startswith(p) for p in _SECRET_PREFIXES)


def redact(value) -> str:
    """Return a redacted placeholder for any secret-like value."""
    if value is None:
        return ""
    s = str(value)
    if is_secret_like(s) or len(s) >= 32:
        return REDACT
    return s


def safe_headers(headers: dict | None) -> dict:
    """Return a copy of headers with secret-like keys/values redacted."""
    if not headers:
        return {}
    out = {}
    for k, v in headers.items():
        kl = k.lower()
        if kl in ("authorization", "api-key", "x-api-key", "cookie", "set-cookie"):
            out[k] = REDACT
        else:
            out[k] = redact(v)
    return out
