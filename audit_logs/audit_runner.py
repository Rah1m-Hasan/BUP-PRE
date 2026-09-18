"""Audit harness: provides a fully-configured in-process API for the swarm.

Run from project root:
    python -m audit_logs.audit_runner [live_url]

If `live_url` is given (e.g. http://127.0.0.1:8000), the harness posts to it.
Otherwise it uses an in-process TestClient with mock interpretations
loaded from the public sample JSON.

Available helpers:
    - client()  -> TestClient or requests-like object
    - post_json(path, payload) -> (status, body)
    - get_json(path) -> (status, body)
    - set_mock_interpretations(mapping) -> route specific scenario_ids
    - set_mock_payload(callable_or_dict) -> return custom mock
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CASES = json.loads(
    (ROOT / "BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json").read_text()
)["cases"]

_MODE = "inprocess"
_LIVE_URL = None
_CLIENT = None


def configure(mode: str = "inprocess", live_url: str | None = None) -> None:
    global _MODE, _LIVE_URL, _CLIENT
    _MODE = mode
    _LIVE_URL = live_url
    if mode == "inprocess":
        from fastapi.testclient import TestClient
        from app.api import dependencies as deps
        from app.main import app
        from app.services.cache import cache

        deps.set_mock_interpretations(
            {c["id"]: c["expected_output"]["directive_interpretation"] for c in CASES}
        )
        cache.clear()
        _CLIENT = TestClient(app)


def client():
    if _MODE == "live":
        raise RuntimeError("live mode uses post_json; no client object")
    return _CLIENT


def post_json(path: str, payload: dict, timeout: int = 30):
    if _MODE == "inprocess":
        r = _CLIENT.post(path, json=payload)
        return r.status_code, (
            r.json()
            if r.headers.get("content-type", "").startswith("application/json")
            else {}
        )
    import urllib.request

    req = urllib.request.Request(
        f"{_LIVE_URL}{path}",
        data=json.dumps(payload).encode(),
        headers={"content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {"detail": str(e)}
    except Exception as e:
        return 0, {"detail": str(e)}


def get_json(path: str, timeout: int = 10):
    if _MODE == "inprocess":
        r = _CLIENT.get(path)
        return r.status_code, (
            r.json()
            if r.headers.get("content-type", "").startswith("application/json")
            else {}
        )
    import urllib.request

    try:
        with urllib.request.urlopen(f"{_LIVE_URL}{path}", timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {"detail": str(e)}
    except Exception as e:
        return 0, {"detail": str(e)}


def set_mock_payload(callable_or_dict):
    """Replace the mock with a custom provider using FastAPI's dependency_overrides.

    Two forms:
      - dict keyed by scenario_id: {sid: [interps]}  (each scenario returns its own)
      - callable(scenario_id, notes) -> dict payload (interpretations list inside)
    """
    from app.api.dependencies import get_interpretation_service
    from app.main import app
    from app.services.cache import cache
    from app.services.interpretation_service import InterpretationService

    if isinstance(callable_or_dict, dict):
        mapping = dict(callable_or_dict)

        class _MapClient:
            def interpret(self, notes, scenario_id, battery):
                interps = mapping.get(scenario_id, [])

                class _R:
                    pass

                o = _R()
                o.payload = {"interpretations": list(interps)}
                o.raw_text = "<map>"
                o.attempts = 1
                o.error = None
                return o

    else:
        provider = callable_or_dict

        class _CallableClient:
            def interpret(self, notes, scenario_id, battery):
                payload = provider(scenario_id, notes)

                class _R:
                    pass

                o = _R()
                o.payload = payload
                o.raw_text = "<callable>"
                o.attempts = 1
                o.error = None
                return o

    svc = InterpretationService(
        llm_client=(
            _MapClient() if isinstance(callable_or_dict, dict) else _CallableClient()
        )
    )

    # FastAPI's dependency_overrides replaces Depends(get_interpretation_service)
    # at request time, so this DOES override the route's captured function.
    app.dependency_overrides[get_interpretation_service] = lambda: svc
    cache.clear()


# Auto-configure on import
configure("inprocess")
