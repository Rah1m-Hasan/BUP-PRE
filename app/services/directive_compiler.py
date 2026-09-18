"""Compile validated directive interpretations into per-hour optimizer constraints."""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class CompiledDirectives:
    effective_solar: list[float]
    active_minimum: list[float]
    no_charge_hours: set[int] = field(default_factory=set)
    no_discharge_hours: set[int] = field(default_factory=set)
    max_grid: dict[int, float] = field(default_factory=dict)


def compile_directives(
    interpretation: dict, battery: dict, hours: list[dict]
) -> CompiledDirectives:
    """Translate validated interpretations into per-hour constraint data.

    - effective_solar[h] = original_solar[h] multiplied by all applicable
      solar_reduction factors (chain: factor1 * factor2 * ...).
    - active_minimum[h] = max(base minimum_energy_kwh, all applicable
      minimum_battery_reserve values for h).
    - no_charge_hours / no_discharge_hours from windows.
    - max_grid[h] = tightest cap among all applicable max_grid_window directives.
    """
    eff_solar = [float(h["solar_kwh"]) for h in hours]
    act_min = [float(battery["minimum_energy_kwh"]) for _ in hours]
    no_charge: set[int] = set()
    no_discharge: set[int] = set()
    max_grid: dict[int, float] = {}

    for it in interpretation.get("interpretations", []):
        if not it.get("applies"):
            continue
        adj = it.get("structured_adjustment") or {}
        t = it["directive_type"]

        if t == "solar_reduction":
            factor = float(adj["factor"])
            for h in adj["hours"]:
                eff_solar[h] *= factor
        elif t == "minimum_battery_reserve":
            req = float(adj["minimum_energy_kwh"])
            for h in adj["hours"]:
                if req > act_min[h]:
                    act_min[h] = req
        elif t == "no_charge_window":
            no_charge.update(int(x) for x in adj.get("hours", []))
        elif t == "no_discharge_window":
            no_discharge.update(int(x) for x in adj.get("hours", []))
        elif t == "max_grid_window":
            cap = float(adj["max_grid_kwh"])
            for h in adj.get("hours", []):
                h = int(h)
                if h not in max_grid or cap < max_grid[h]:
                    max_grid[h] = cap

    return CompiledDirectives(
        effective_solar=eff_solar,
        active_minimum=act_min,
        no_charge_hours=no_charge,
        no_discharge_hours=no_discharge,
        max_grid=max_grid,
    )
