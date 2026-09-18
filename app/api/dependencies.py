"""Dependency injection providers for FastAPI routes."""

from __future__ import annotations
from typing import Any

from app.core.config import settings
from app.services.llm_client import LLMClient
from app.services.interpretation_service import InterpretationService

# Module-level mock registry, set by tests or by LLM_MOCK=true
_mock_interpretations: dict[str, list[dict]] = {}


def set_mock_interpretations(mapping: dict[str, list[dict]]) -> None:
    """Replace the in-memory mock registry. Used by tests."""
    global _mock_interpretations
    _mock_interpretations = dict(mapping)


def get_mock_interpretations() -> dict[str, list[dict]]:
    return _mock_interpretations


class _RoutingMockClient:
    """Returns interpretations from a scenario_id-keyed mapping."""

    def __init__(self, mapping: dict[str, list[dict]]):
        self.mapping = mapping

    def interpret(self, notes, scenario_id, battery):
        class _R:
            payload = {"interpretations": list(self.mapping.get(scenario_id, []))}
            raw_text = "<routing-mock>"
            attempts = 1
            error = None

        return _R()


def get_interpretation_service() -> InterpretationService:
    """Build an InterpretationService configured by env / test overrides."""
    mock_map = get_mock_interpretations()
    if settings.llm_mock or mock_map:
        return InterpretationService(llm_client=_RoutingMockClient(mock_map))
    return InterpretationService()
