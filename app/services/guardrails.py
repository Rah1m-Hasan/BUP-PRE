"""Deterministic guardrails for LLM-produced interpretation payloads.

Treats LLM output as untrusted structured data and validates:
- Exactly one interpretation per operator note
- note_index values 0..N-1 with no duplicates or gaps
- directive_type is one of the six allowed
- applies semantics: false only for no_op; true for everything else
- structured_adjustment shape per directive_type
- hours: unique ints 0..23 ascending
- solar factor in [0,1]
- battery reserve finite, non-negative, <= capacity
- max_grid_kwh finite, non-negative
- no invented fields/directive types

If validation fails, raises GuardrailError with a precise message that the
InterpretationService uses to construct a repair prompt for the LLM.
"""

from typing import Any, List

ALLOWED_TYPES = {
    "solar_reduction",
    "minimum_battery_reserve",
    "no_charge_window",
    "no_discharge_window",
    "max_grid_window",
    "no_op",
}


class GuardrailError(Exception):
    def __init__(self, message: str, path: str = ""):
        super().__init__(message)
        self.message = message
        self.path = path


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_number(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _check_hours(hours: Any, where: str) -> None:
    if not isinstance(hours, list) or not hours:
        raise GuardrailError("hours must be a non-empty list", where)
    if not all(_is_int(h) for h in hours):
        raise GuardrailError("hours must be integers", where)
    if any(h < 0 or h > 23 for h in hours):
        raise GuardrailError("hours must be in range 0..23", where)
    if len(set(hours)) != len(hours):
        raise GuardrailError("hours must be unique", where)
    if hours != sorted(hours):
        raise GuardrailError("hours must be in ascending order", where)


def _check_factor(v: Any, where: str) -> None:
    if not _is_number(v):
        raise GuardrailError("factor must be a number", where)
    if not (0.0 <= v <= 1.0):
        raise GuardrailError("factor must be within [0,1]", where)


def _check_finite_nonneg(v: Any, name: str, where: str) -> None:
    if not _is_number(v):
        raise GuardrailError(f"{name} must be a number", where)
    # NaN/inf check
    if isinstance(v, float) and (v != v or v in (float("inf"), float("-inf"))):
        raise GuardrailError(f"{name} must be finite", where)
    if v < 0:
        raise GuardrailError(f"{name} must be non-negative", where)


def _check_adjustment(directive_type: str, adj: Any, battery: dict) -> None:
    if not isinstance(adj, dict):
        raise GuardrailError("structured_adjustment must be an object", directive_type)

    if directive_type == "solar_reduction":
        _check_hours(adj.get("hours"), f"{directive_type}.hours")
        _check_factor(adj.get("factor"), f"{directive_type}.factor")
    elif directive_type == "minimum_battery_reserve":
        _check_hours(adj.get("hours"), f"{directive_type}.hours")
        _check_finite_nonneg(
            adj.get("minimum_energy_kwh"),
            "minimum_energy_kwh",
            directive_type,
        )
        if adj["minimum_energy_kwh"] > battery["capacity_kwh"]:
            raise GuardrailError(
                "minimum_energy_kwh exceeds battery capacity", directive_type
            )
    elif directive_type in ("no_charge_window", "no_discharge_window"):
        _check_hours(adj.get("hours"), f"{directive_type}.hours")
    elif directive_type == "max_grid_window":
        _check_hours(adj.get("hours"), f"{directive_type}.hours")
        _check_finite_nonneg(adj.get("max_grid_kwh"), "max_grid_kwh", directive_type)
    # no_op has already been handled separately; never reaches here


def validate_interpretation(payload: Any, notes: List[str], battery: dict) -> dict:
    """Validate the LLM interpretation payload. Returns the payload on success.

    Raises GuardrailError on any violation. The error message is precise and
    safe to feed back to the LLM as repair context.
    """
    n = len(notes)
    if not isinstance(payload, dict):
        raise GuardrailError("payload must be a JSON object")
    if "interpretations" not in payload:
        raise GuardrailError("missing 'interpretations' field")
    interps = payload["interpretations"]
    if not isinstance(interps, list):
        raise GuardrailError("'interpretations' must be a list")
    if len(interps) != n:
        raise GuardrailError(f"expected {n} interpretations, got {len(interps)}")

    seen_idx: set[int] = set()
    for i, item in enumerate(interps):
        if not isinstance(item, dict):
            raise GuardrailError(f"interpretation[{i}] must be an object")
        ni = item.get("note_index")
        if not _is_int(ni):
            raise GuardrailError(f"interpretation[{i}].note_index must be int")
        if ni in seen_idx:
            raise GuardrailError(f"duplicate note_index {ni}")
        if ni < 0 or ni >= n:
            raise GuardrailError(f"note_index {ni} out of range 0..{n - 1}")
        seen_idx.add(ni)

        dtype = item.get("directive_type")
        if dtype not in ALLOWED_TYPES:
            raise GuardrailError(f"unsupported directive_type '{dtype}' at index {i}")

        applies = item.get("applies")
        adj = item.get("structured_adjustment")
        expl = item.get("explanation")

        if dtype == "no_op":
            if applies is not False:
                raise GuardrailError(
                    "no_op must have applies=false", f"interpretation[{i}]"
                )
            if adj is not None:
                raise GuardrailError(
                    "no_op must have structured_adjustment=null",
                    f"interpretation[{i}]",
                )
        else:
            if applies is not True:
                raise GuardrailError(
                    f"{dtype} must have applies=true", f"interpretation[{i}]"
                )
            _check_adjustment(dtype, adj, battery)

        if not isinstance(expl, str) or not expl.strip():
            raise GuardrailError(
                "explanation must be a non-empty string",
                f"interpretation[{i}]",
            )
        if len(expl) > 500:
            raise GuardrailError(
                "explanation must be <= 500 chars",
                f"interpretation[{i}]",
            )

    expected = set(range(n))
    if seen_idx != expected:
        missing = sorted(expected - seen_idx)
        raise GuardrailError(f"missing note_index values: {missing}")

    return payload
