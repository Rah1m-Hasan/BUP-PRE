"""Build the response hourly_plan entries from optimized variables."""

from __future__ import annotations
from typing import List, Tuple

EPS = 1e-6


def _decide_action(charge: float, disch: float) -> Tuple[str, float]:
    if charge > EPS and disch > EPS:
        # MILP mutual exclusion prevents this; if it ever happens, treat as idle
        return "idle", 0.0
    if charge > EPS:
        return "charge", charge
    if disch > EPS:
        return "discharge", disch
    return "idle", 0.0


def build_plan(optimized: dict, hours: list[dict]) -> List[dict]:
    """Convert optimizer variables into response plan entries (hours 0..23)."""
    out: List[dict] = []
    for h in range(24):
        c = optimized["charge"][h]
        d = optimized["discharge"][h]
        action, mag = _decide_action(c, d)
        out.append(
            {
                "hour": h,
                "grid_kwh": round(float(optimized["grid"][h]), 6),
                "solar_used_kwh": round(float(optimized["solar_used"][h]), 6),
                "battery_action": action,
                "battery_kwh": round(float(mag), 6),
                "battery_energy_after_kwh": round(
                    float(optimized["energy_after"][h]), 6
                ),
            }
        )
    return out


def recompute_totals(plan: List[dict], hours: list[dict]) -> Tuple[float, float, float]:
    """Recalculate total_grid_kwh, total_cost_bdt, peak_grid_kwh from plan."""
    total_grid = sum(e["grid_kwh"] for e in plan)
    total_cost = sum(
        e["grid_kwh"] * float(hours[h]["tariff_bdt_per_kwh"])
        for h, e in enumerate(plan)
    )
    peak = max((e["grid_kwh"] for e in plan), default=0.0)
    return total_grid, total_cost, peak
