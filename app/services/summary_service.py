"""Deterministic plan_summary generator.

No LLM call is made here. Summary describes:
- which directives were applied
- which notes were ignored
- high-level battery strategy
- cost outcome
"""


def _fmt_hours(hours) -> str:
    if not hours:
        return "—"
    return ",".join(str(int(h)) for h in hours)


def build_summary(interpretation: dict, optimized: dict) -> str:
    applied: list[str] = []
    ignored: list[int] = []
    for it in interpretation.get("interpretations", []):
        if not it.get("applies") or it.get("directive_type") == "no_op":
            ignored.append(int(it.get("note_index", -1)))
            continue
        t = it["directive_type"]
        adj = it.get("structured_adjustment") or {}
        if t == "solar_reduction":
            applied.append(
                f"solar reduced to {adj.get('factor')} during hours {_fmt_hours(adj.get('hours', []))}"
            )
        elif t == "minimum_battery_reserve":
            applied.append(
                f"battery reserve >= {adj.get('minimum_energy_kwh')} kWh during hours {_fmt_hours(adj.get('hours', []))}"
            )
        elif t == "no_charge_window":
            applied.append(
                f"charging disabled during hours {_fmt_hours(adj.get('hours', []))}"
            )
        elif t == "no_discharge_window":
            applied.append(
                f"discharging disabled during hours {_fmt_hours(adj.get('hours', []))}"
            )
        elif t == "max_grid_window":
            applied.append(
                f"grid import capped at {adj.get('max_grid_kwh')} kWh during hours {_fmt_hours(adj.get('hours', []))}"
            )

    parts: list[str] = []
    if applied:
        parts.append("Applied: " + "; ".join(applied) + ".")
    if ignored:
        parts.append("Ignored note(s): " + ", ".join(f"#{i}" for i in ignored) + ".")
    parts.append(
        f"Total grid {optimized['total_grid_kwh']:.2f} kWh; "
        f"total cost {optimized['total_cost_bdt']:.2f} BDT. "
        "Battery pre-charged in low-tariff hours, discharged during expensive peaks, "
        "and returned to initial energy at hour 23."
    )
    return " ".join(parts)
