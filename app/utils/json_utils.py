"""Robust JSON extraction from LLM text output.

LLM responses sometimes include:
- Plain JSON
- Markdown fenced ```json ... ``` blocks
- Reasoning blocks `<think>...</think>` (from Groq gpt-oss models)
- Surrounding prose
- Trailing commas / minor noise

This utility finds and returns the first valid JSON object or array.
"""

import json
import re

_FENCED_JSON = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
# Strip reasoning blocks emitted by Groq's gpt-oss-120b (and similar).
# Non-greedy, multi-line, case-insensitive to be safe.
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _find_balanced_object(text: str, start: int) -> int | None:
    """Return the index of the matching closing brace for the object starting at `start`, or None."""
    if start >= len(text) or text[start] != "{":
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
    return None


def _try_load(s: str):
    try:
        return json.loads(s)
    except Exception:
        return None


def extract_json(text: str):
    """Return the first parseable JSON object or array in `text`, or None."""
    if not text:
        return None
    # Strip reasoning blocks BEFORE attempting any parsing.
    text = _THINK.sub("", text)
    # 1. Whole text
    parsed = _try_load(text)
    if parsed is not None:
        return parsed
    # 2. Markdown fenced block
    m = _FENCED_JSON.search(text)
    if m:
        parsed = _try_load(m.group(1))
        if parsed is not None:
            return parsed
    # 3. First balanced object starting at each "{"
    start = text.find("{")
    while start != -1:
        end = _find_balanced_object(text, start)
        if end is not None:
            parsed = _try_load(text[start : end + 1])
            if parsed is not None:
                return parsed
        start = text.find("{", start + 1)
    # 4. First balanced array
    start = text.find("[")
    if start != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            c = text[i]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
                continue
            if c == '"':
                in_str = True
            elif c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    parsed = _try_load(text[start : i + 1])
                    if parsed is not None:
                        return parsed
                    break
    return None
