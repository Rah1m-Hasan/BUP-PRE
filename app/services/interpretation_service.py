"""Interpretation orchestration: LLM call → guardrail → retry-on-failure.

Wraps LLMClient and the deterministic guardrails. Retries with a repair
prompt when the LLM output fails validation, up to max_attempts times.
"""

from typing import List

from app.services.guardrails import GuardrailError, validate_interpretation
from app.services.llm_client import LLMClient


class InterpretationError(Exception):
    """Raised when interpretation cannot be produced after retries."""


class InterpretationService:
    def __init__(
        self,
        llm_client: LLMClient | None = None,
        max_attempts: int = 3,
    ):
        self.llm = llm_client or LLMClient()
        self.max_attempts = max_attempts

    def interpret(self, scenario_id: str, notes: List[str], battery: dict) -> dict:
        last_err = "no_attempt"
        for attempt in range(1, self.max_attempts + 1):
            res = self.llm.interpret(
                notes=notes, scenario_id=scenario_id, battery=battery
            )
            if res.error:
                last_err = res.error
                continue
            try:
                return validate_interpretation(res.payload, notes, battery)
            except GuardrailError as e:
                last_err = f"{e.path}: {e.message}" if e.path else e.message
        raise InterpretationError(
            f"interpretation failed after {self.max_attempts} attempts: {last_err}"
        )
