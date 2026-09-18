"""🧠 AGENT 3: LLM & Guardrail Hacker.

Mocks the LLM with malicious payloads to verify the guardrails catch
or repair every bad input without crashing.

Payloads:
  A. Fake directive_type "super_charge_window"
  B. no_op with applies=true
  C. solar_reduction factor=1.5
  D. Unsorted hours [14, 13]
  E. Raw markdown-fenced JSON
  F. Empty JSON object
  G. Truncated text
  H. Wrong count of interpretations
  I. Duplicate note_index
  J. Reserve above capacity
  K. Negative reserve
  L. Negative grid cap
  M. no_op with non-null adjustment
  N. Non-no_op with null adjustment

The service MUST return 400 (interpreter failure) or 200 (after repair
on subsequent attempt) — never 500 with internal info leak.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from audit_logs.audit_runner import (
    configure,
    post_json,
    set_mock_payload,
)

configure("inprocess")

failures: list[dict] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    marker = "PASS" if ok else "FAIL"
    print(f"  [{marker}] {name}{(' — ' + detail) if detail else ''}")
    if not ok:
        failures.append({"agent": "LLMHacker", "name": name, "detail": detail})


def valid_payload() -> dict:
    return {
        "scenario_id": "HACK-01",
        "operator_notes": ["Direct note."],
        "hours": [
            {"hour": h, "demand_kwh": 100, "solar_kwh": 50, "tariff_bdt_per_kwh": 10}
            for h in range(24)
        ],
        "battery": {
            "capacity_kwh": 200,
            "initial_energy_kwh": 100,
            "minimum_energy_kwh": 30,
            "max_charge_kwh_per_hour": 50,
            "max_discharge_kwh_per_hour": 50,
        },
    }


def base_payload(sid: str) -> dict:
    p = valid_payload()
    p["scenario_id"] = sid
    return p


# Each test injects a malicious interpretation, then verifies that
# the response is 400 (rejected) or 200 after repair — NEVER 500.


def t_invented_directive_type():
    """Payload A: invented directive type."""
    p = base_payload("HACK-A")
    set_mock_payload(
        {
            "HACK-A": [
                {
                    "note_index": 0,
                    "applies": True,
                    "directive_type": "super_charge_window",
                    "structured_adjustment": {"hours": [10, 11]},
                    "explanation": "hallucinated",
                }
            ]
        }
    )
    sc, _ = post_json("/optimize-energy", p)
    record("invented_directive_type_rejected_or_safe", sc in (400, 200), f"got {sc}")


def t_no_op_with_applies_true():
    """Payload B: no_op with applies=true."""
    p = base_payload("HACK-B")
    set_mock_payload(
        {
            "HACK-B": [
                {
                    "note_index": 0,
                    "applies": True,
                    "directive_type": "no_op",
                    "structured_adjustment": None,
                    "explanation": "tried to lie",
                }
            ]
        }
    )
    sc, _ = post_json("/optimize-energy", p)
    record("no_op_applies_true_rejected", sc == 400, f"got {sc}")


def t_factor_out_of_range():
    """Payload C: solar_reduction factor=1.5."""
    p = base_payload("HACK-C")
    set_mock_payload(
        {
            "HACK-C": [
                {
                    "note_index": 0,
                    "applies": True,
                    "directive_type": "solar_reduction",
                    "structured_adjustment": {"hours": [10, 11], "factor": 1.5},
                    "explanation": "too much",
                }
            ]
        }
    )
    sc, _ = post_json("/optimize-energy", p)
    record("factor_out_of_range_rejected", sc == 400, f"got {sc}")


def t_unsorted_hours():
    """Payload D: unsorted hours [14, 13]."""
    p = base_payload("HACK-D")
    set_mock_payload(
        {
            "HACK-D": [
                {
                    "note_index": 0,
                    "applies": True,
                    "directive_type": "no_charge_window",
                    "structured_adjustment": {"hours": [14, 13]},
                    "explanation": "unsorted",
                }
            ]
        }
    )
    sc, _ = post_json("/optimize-energy", p)
    record("unsorted_hours_rejected", sc == 400, f"got {sc}")


def t_markdown_fenced_json():
    """Payload E: JSON wrapped in ```json ... ```.
    The LLMClient would not produce this — extract_json handles it.
    Here we simulate the LLM returning text that includes markdown."""
    p = base_payload("HACK-E")
    # Use a callable provider that returns the wrapped text as raw text,
    # but a dict payload for our mock; this just verifies the parser
    # inside extract_json handles markdown — we exercise it indirectly
    # via test_json_utils.py. Here we just confirm the service does not crash.
    set_mock_payload(
        {
            "HACK-E": [
                {
                    "note_index": 0,
                    "applies": True,
                    "directive_type": "solar_reduction",
                    "structured_adjustment": {"hours": [10, 11], "factor": 0.5},
                    "explanation": "ok",
                }
            ]
        }
    )
    sc, body = post_json("/optimize-energy", p)
    record("markdown_safe_integration", sc == 200, f"got {sc}")


def t_empty_interpretations():
    """Payload F: empty interpretations list."""
    p = base_payload("HACK-F")
    set_mock_payload({"HACK-F": []})
    sc, _ = post_json("/optimize-energy", p)
    record("empty_interpretations_rejected", sc == 400, f"got {sc}")


def t_wrong_count():
    """Payload G: too few interpretations for the notes."""
    p = base_payload("HACK-G")
    p["operator_notes"] = ["a", "b"]
    set_mock_payload(
        {
            "HACK-G": [
                {
                    "note_index": 0,
                    "applies": True,
                    "directive_type": "no_op",
                    "structured_adjustment": None,
                    "explanation": "only one",
                }
            ]
        }
    )
    sc, _ = post_json("/optimize-energy", p)
    record("wrong_count_rejected", sc == 400, f"got {sc}")


def t_duplicate_note_index():
    """Payload H: duplicate note_index."""
    p = base_payload("HACK-H")
    p["operator_notes"] = ["a", "b"]
    set_mock_payload(
        {
            "HACK-H": [
                {
                    "note_index": 0,
                    "applies": True,
                    "directive_type": "no_op",
                    "structured_adjustment": None,
                    "explanation": "x",
                },
                {
                    "note_index": 0,
                    "applies": True,
                    "directive_type": "no_op",
                    "structured_adjustment": None,
                    "explanation": "dup",
                },
            ]
        }
    )
    sc, _ = post_json("/optimize-energy", p)
    record("duplicate_note_index_rejected", sc == 400, f"got {sc}")


def t_reserve_above_capacity():
    """Payload I: reserve above capacity."""
    p = base_payload("HACK-I")
    set_mock_payload(
        {
            "HACK-I": [
                {
                    "note_index": 0,
                    "applies": True,
                    "directive_type": "minimum_battery_reserve",
                    "structured_adjustment": {
                        "hours": [18],
                        "minimum_energy_kwh": 9999,
                    },
                    "explanation": "x",
                }
            ]
        }
    )
    sc, _ = post_json("/optimize-energy", p)
    record("reserve_above_capacity_rejected", sc == 400, f"got {sc}")


def t_negative_reserve():
    """Payload J: negative reserve."""
    p = base_payload("HACK-J")
    set_mock_payload(
        {
            "HACK-J": [
                {
                    "note_index": 0,
                    "applies": True,
                    "directive_type": "minimum_battery_reserve",
                    "structured_adjustment": {"hours": [18], "minimum_energy_kwh": -10},
                    "explanation": "x",
                }
            ]
        }
    )
    sc, _ = post_json("/optimize-energy", p)
    record("negative_reserve_rejected", sc == 400, f"got {sc}")


def t_negative_grid_cap():
    """Payload K: negative max_grid_kwh."""
    p = base_payload("HACK-K")
    set_mock_payload(
        {
            "HACK-K": [
                {
                    "note_index": 0,
                    "applies": True,
                    "directive_type": "max_grid_window",
                    "structured_adjustment": {"hours": [18], "max_grid_kwh": -5},
                    "explanation": "x",
                }
            ]
        }
    )
    sc, _ = post_json("/optimize-energy", p)
    record("negative_grid_cap_rejected", sc == 400, f"got {sc}")


def t_no_op_with_adjustment():
    """Payload L: no_op with non-null adjustment."""
    p = base_payload("HACK-L")
    set_mock_payload(
        {
            "HACK-L": [
                {
                    "note_index": 0,
                    "applies": False,
                    "directive_type": "no_op",
                    "structured_adjustment": {"hours": [10]},
                    "explanation": "x",
                }
            ]
        }
    )
    sc, _ = post_json("/optimize-energy", p)
    record("no_op_with_adjustment_rejected", sc == 400, f"got {sc}")


def t_non_no_op_with_null_adjustment():
    """Payload M: non-no_op with null adjustment."""
    p = base_payload("HACK-M")
    set_mock_payload(
        {
            "HACK-M": [
                {
                    "note_index": 0,
                    "applies": True,
                    "directive_type": "solar_reduction",
                    "structured_adjustment": None,
                    "explanation": "x",
                }
            ]
        }
    )
    sc, _ = post_json("/optimize-energy", p)
    record("non_no_op_null_adj_rejected", sc == 400, f"got {sc}")


def t_hours_out_of_range():
    """Payload N: hour 25."""
    p = base_payload("HACK-N")
    set_mock_payload(
        {
            "HACK-N": [
                {
                    "note_index": 0,
                    "applies": True,
                    "directive_type": "no_charge_window",
                    "structured_adjustment": {"hours": [25]},
                    "explanation": "x",
                }
            ]
        }
    )
    sc, _ = post_json("/optimize-energy", p)
    record("hour_25_rejected", sc == 400, f"got {sc}")


def t_missing_note_index():
    """Payload O: missing note_index field."""
    p = base_payload("HACK-O")
    set_mock_payload(
        {
            "HACK-O": [
                {
                    "applies": True,
                    "directive_type": "no_op",
                    "structured_adjustment": None,
                    "explanation": "x",
                }
            ]
        }
    )
    sc, _ = post_json("/optimize-energy", p)
    record("missing_note_index_rejected", sc == 400, f"got {sc}")


def t_payload_not_dict():
    """Payload P: top-level payload is a list, not a dict."""
    p = base_payload("HACK-P")

    # Provide a callable provider that returns a list
    def provider(sid, notes):
        return [{"interpretations": []}]

    set_mock_payload(provider)
    sc, _ = post_json("/optimize-energy", p)
    record("payload_not_dict_rejected", sc == 400, f"got {sc}")


def t_no_internal_leak_in_400():
    """Verify that 400 responses do not leak internal info."""
    p = base_payload("HACK-Q")
    set_mock_payload(
        {
            "HACK-Q": [
                {
                    "note_index": 0,
                    "applies": True,
                    "directive_type": "fake_thing",
                    "structured_adjustment": {"hours": [10]},
                    "explanation": "x",
                }
            ]
        }
    )
    sc, body = post_json("/optimize-energy", p)
    detail = json.dumps(body)
    leak_words = ["traceback", "openai", "groq", "api_key", "sk-", "gsk_", "Traceback"]
    leak = any(w.lower() in detail.lower() for w in leak_words)
    record("no_internal_leak_in_400", sc == 400 and not leak, f"sc={sc} leaked={leak}")


def main():
    print("=" * 60)
    print("🧠  AGENT 3: LLM & GUARDRAIL HACKER")
    print("=" * 60)
    print()
    print("[3.1] Malicious LLM payloads:")
    t_invented_directive_type()
    t_no_op_with_applies_true()
    t_factor_out_of_range()
    t_unsorted_hours()
    t_markdown_fenced_json()
    t_empty_interpretations()
    t_wrong_count()
    t_duplicate_note_index()
    t_reserve_above_capacity()
    t_negative_reserve()
    t_negative_grid_cap()
    t_no_op_with_adjustment()
    t_non_no_op_with_null_adjustment()
    t_hours_out_of_range()
    t_missing_note_index()
    t_payload_not_dict()
    t_no_internal_leak_in_400()

    out = ROOT / "audit_logs" / "llm_hacker_failures.json"
    out.write_text(json.dumps({"agent": "LLMHacker", "failures": failures}, indent=2))
    print()
    print(f"LLM Hacker total failures: {len(failures)}")
    if failures:
        for f in failures:
            print(f"  - {f['name']}: {f['detail']}")
    print(f"Wrote {out}")
    sys.exit(0 if not failures else 1)


if __name__ == "__main__":
    main()
