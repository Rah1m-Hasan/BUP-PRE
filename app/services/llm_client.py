"""LLM client wrapper using the official OpenAI Python library pointed at Groq.

Groq exposes an OpenAI-compatible endpoint at https://api.groq.com/openai/v1.
The same `openai` SDK works without code changes other than base_url and key.
The default model is `openai/gpt-oss-120b` (a reasoning model that emits
<think>...</think> tags). Reasoning parameters are passed via `extra_body`
because Groq-specific fields are not part of the standard OpenAI ChatCompletion
schema.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, List

from openai import OpenAI

from app.core.config import settings
from app.services.llm_prompting import (
    SYSTEM_PROMPT,
    build_repair_prompt,
    build_user_prompt,
)
from app.utils.json_utils import extract_json


@dataclass
class LLMCallResult:
    payload: Any
    raw_text: str
    attempts: int
    error: str | None = None


class LLMClient:
    """Wraps the OpenAI SDK pointed at Groq.

    Use llm_client.interpret(notes, scenario_id, battery) -> LLMCallResult.
    The result payload is the extracted JSON (a dict expected), or None with
    `error` set on failure.
    """

    def __init__(
        self,
        mock: bool | None = None,
        mock_payload: dict | None = None,
    ):
        self.mock = settings.llm_mock if mock is None else mock
        self.mock_payload = mock_payload or {}
        self._real: OpenAI | None = None
        if not self.mock:
            api_key = settings.groq_api_key or "missing"
            self._real = OpenAI(
                api_key=api_key,
                base_url=settings.groq_base_url,
                timeout=settings.llm_timeout_seconds,
                max_retries=0,  # we manage retries explicitly
            )

    def interpret(
        self, notes: List[str], scenario_id: str, battery: dict
    ) -> LLMCallResult:
        if self.mock:
            return LLMCallResult(
                payload=dict(self.mock_payload),
                raw_text="<mock>",
                attempts=1,
            )
        if self._real is None:
            return LLMCallResult(
                payload=None, raw_text="", attempts=0, error="no_client"
            )

        user_msg = build_user_prompt(scenario_id, notes, battery)
        attempts = 0
        last_err: str | None = None
        text = ""
        max_total = max(1, settings.llm_max_retries) + 1
        while attempts < max_total:
            attempts += 1
            prompt = (
                user_msg
                if attempts == 1
                else user_msg + "\n\n" + build_repair_prompt(last_err or "")
            )
            kwargs: dict = dict(
                model=settings.llm_model,
                temperature=settings.llm_temperature,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            )
            # Groq's reasoning models (gpt-oss) reject response_format when
            # reasoning_effort is set. Only attach response_format if we are
            # NOT also requesting reasoning.
            if not settings.llm_reasoning_effort:
                kwargs["response_format"] = {"type": "json_object"}
            else:
                # Pass reasoning_effort via extra_body so it survives the
                # OpenAI SDK schema validation.
                kwargs["extra_body"] = {
                    "reasoning_effort": settings.llm_reasoning_effort,
                }
            try:
                resp = self._real.chat.completions.create(**kwargs)
                text = resp.choices[0].message.content or ""
            except Exception as e:
                last_err = f"transport_error: {type(e).__name__}"
                continue
            parsed = extract_json(text)
            if parsed is not None:
                return LLMCallResult(payload=parsed, raw_text=text, attempts=attempts)
            last_err = "output was not valid JSON"
        return LLMCallResult(
            payload=None, raw_text=text, attempts=attempts, error=last_err or "unknown"
        )
