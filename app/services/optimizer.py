"""MILP optimizer for the GridWise 24-hour energy scheduling problem.

Uses PuLP with the bundled CBC solver. Decision variables:
  grid[h]        >= 0           grid energy purchased (kWh)
  solar[h]       in [0, eff_h]  solar used (kWh)
  charge[h]      >= 0           battery charge energy (kWh)
  disch[h]       >= 0           battery discharge energy (kWh)
  e_after[h]     in [min_h, C] battery energy after hour h (kWh)
  y_chg[h]       binary         1 if charging in hour h
  y_dis[h]       binary         1 if discharging in hour h

Objective: sum_h grid[h] * tariff[h]

Constraints:
  Energy balance: grid + solar + disch == demand + charge
  Battery transition: e_after[h] = e_after[h-1] + charge - disch; e_after[-1] = e0
  Rate caps: charge[h] <= max_chg; disch[h] <= max_dis
  Window caps: charge[h] = 0 in no_charge_hours; disch[h] = 0 in no_discharge_hours
  Grid caps: grid[h] <= max_grid[h]
  Mutual exclusion: y_chg[h] + y_dis[h] <= 1

Solver: PuLP's bundled CBC. If status is not Optimal, OptimizerError is raised.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from pulp import (
    LpProblem,
    LpMinimize,
    LpVariable,
    lpSum,
    LpStatus,
    PULP_CBC_CMD,
    value,
)


class OptimizerError(Exception):
    pass


@dataclass
class OptimizerResult:
    grid: list[float]
    solar_used: list[float]
    charge: list[float]
    discharge: list[float]
    energy_after: list[float]
    total_grid_kwh: float
    total_cost_bdt: float


def _val(x: Any) -> float:
    v = value(x)
    return 0.0 if v is None else float(v)


def optimize(
    compiled,
    battery: dict,
    hours: list[dict],
    time_limit_seconds: int = 10,
) -> dict:
    H = list(range(24))
    prob = LpProblem("gridwise", LpMinimize)

    grid = {h: LpVariable(f"grid_{h}", lowBound=0) for h in H}
    eff_solar = compiled.effective_solar
    solar = {
        h: LpVariable(f"solar_{h}", lowBound=0, upBound=max(0.0, eff_solar[h]))
        for h in H
    }
    charge = {h: LpVariable(f"chg_{h}", lowBound=0) for h in H}
    disch = {h: LpVariable(f"dis_{h}", lowBound=0) for h in H}
    active_min = compiled.active_minimum
    cap = float(battery["capacity_kwh"])
    e_after = {
        h: LpVariable(
            f"e_{h}",
            lowBound=max(0.0, active_min[h]),
            upBound=cap,
        )
        for h in H
    }
    y_chg = {h: LpVariable(f"y_chg_{h}", cat="Binary") for h in H}
    y_dis = {h: LpVariable(f"y_dis_{h}", cat="Binary") for h in H}

    e0 = float(battery["initial_energy_kwh"])
    max_chg = float(battery["max_charge_kwh_per_hour"])
    max_dis = float(battery["max_discharge_kwh_per_hour"])

    # Objective: minimize total grid cost
    prob += lpSum(grid[h] * float(hours[h]["tariff_bdt_per_kwh"]) for h in H)

    # Energy balance
    for h in H:
        prob += (
            grid[h] + solar[h] + disch[h] == float(hours[h]["demand_kwh"]) + charge[h]
        )

    # Battery transitions
    for h in H:
        prev = e0 if h == 0 else e_after[h - 1]
        prob += e_after[h] == prev + charge[h] - disch[h]

    # End-of-day neutrality
    prob += e_after[23] == e0

    # Rate caps
    for h in H:
        prob += charge[h] <= max_chg
        prob += disch[h] <= max_dis

    # Window caps
    for h in compiled.no_charge_hours:
        prob += charge[h] == 0
    for h in compiled.no_discharge_hours:
        prob += disch[h] == 0

    # Grid caps
    for h, cap_h in compiled.max_grid.items():
        prob += grid[h] <= cap_h

    # Mutual exclusion via binaries
    BIG = max_chg + max_dis + 1
    for h in H:
        prob += charge[h] <= BIG * y_chg[h]
        prob += disch[h] <= BIG * y_dis[h]
        prob += y_chg[h] + y_dis[h] <= 1

    solver = PULP_CBC_CMD(msg=False, timeLimit=time_limit_seconds)
    status = prob.solve(solver)
    if LpStatus[status] != "Optimal":
        raise OptimizerError(f"solver status: {LpStatus[status]}")

    grid_v = [_val(grid[h]) for h in H]
    solar_v = [_val(solar[h]) for h in H]
    charge_v = [_val(charge[h]) for h in H]
    disch_v = [_val(disch[h]) for h in H]
    eafter_v = [_val(e_after[h]) for h in H]

    # Numerical cleanup
    eps = 1e-6
    grid_v = [0.0 if g < eps else g for g in grid_v]
    solar_v = [0.0 if s < eps else s for s in solar_v]
    charge_v = [0.0 if c < eps else c for c in charge_v]
    disch_v = [0.0 if d < eps else d for d in disch_v]

    total_grid = sum(grid_v)
    total_cost = sum(grid_v[h] * float(hours[h]["tariff_bdt_per_kwh"]) for h in H)

    return {
        "grid": grid_v,
        "solar_used": solar_v,
        "charge": charge_v,
        "discharge": disch_v,
        "energy_after": eafter_v,
        "total_grid_kwh": total_grid,
        "total_cost_bdt": total_cost,
    }
