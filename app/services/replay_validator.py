"""Independent replay validator.

Replays the final plan against the original directive ground truth, effective
solar, battery rules, energy balance, and end-of-day neutrality. Used as the
final guard before returning a response. Raises ReplayError on any violation.

Tolerance: 0.01 kWh or 0.01 BDT, per Problem Statement Section 11.5.
"""

from __future__ import annotations
from typing import List

TOL = 0.01


class ReplayError(Exception):
    pass


def _hours_set(plan: List[dict]) -> List[int]:
    return sorted(int(e["hour"]) for e in plan)


def replay_validate(
    plan: List[dict],
    hours: List[dict],
    battery: dict,
    compiled,
    interpretation: dict,
    scenario_id: str,
) -> None:
    """Validate the returned plan. Raises ReplayError on any rule violation."""
    if len(plan) != 24:
        raise ReplayError(f"plan length must be 24, got {len(plan)}")
    if _hours_set(plan) != list(range(24)):
        raise ReplayError("plan hours must be unique 0..23 in order")

    e0 = float(battery["initial_energy_kwh"])
    cap = float(battery["capacity_kwh"])
    max_chg = float(battery["max_charge_kwh_per_hour"])
    max_dis = float(battery["max_discharge_kwh_per_hour"])
    prev = e0

    total_grid = 0.0
    total_cost = 0.0
    peak = 0.0

    for e in plan:
        h = int(e["hour"])
        grid = float(e["grid_kwh"])
        solar = float(e["solar_used_kwh"])
        action = e["battery_action"]
        bkwh = float(e["battery_kwh"])
        eafter = float(e["battery_energy_after_kwh"])

        if grid < -TOL or solar < -TOL or bkwh < -TOL or eafter < -TOL:
            raise ReplayError(f"negative value at hour {h}")

        if solar > compiled.effective_solar[h] + TOL:
            raise ReplayError(
                f"solar overuse at hour {h}: used {solar:.4f}, available {compiled.effective_solar[h]:.4f}"
            )

        if action not in ("charge", "discharge", "idle"):
            raise ReplayError(f"bad battery_action '{action}' at hour {h}")
        if action == "idle" and bkwh > TOL:
            raise ReplayError(f"idle must have zero battery_kwh at hour {h}")

        charge = bkwh if action == "charge" else 0.0
        disch = bkwh if action == "discharge" else 0.0

        demand = float(hours[h]["demand_kwh"])
        tariff = float(hours[h]["tariff_bdt_per_kwh"])
        lhs = grid + solar + disch
        rhs = demand + charge
        if abs(lhs - rhs) > TOL:
            raise ReplayError(
                f"energy balance off at hour {h}: lhs={lhs:.4f}, rhs={rhs:.4f}"
            )

        if abs((prev + charge - disch) - eafter) > TOL:
            raise ReplayError(
                f"battery transition off at hour {h}: prev+chg-dis={prev + charge - disch:.4f}, eafter={eafter:.4f}"
            )

        if eafter < compiled.active_minimum[h] - TOL:
            raise ReplayError(
                f"reserve violated at hour {h}: eafter={eafter:.4f}, min={compiled.active_minimum[h]:.4f}"
            )
        if eafter > cap + TOL:
            raise ReplayError(
                f"capacity violated at hour {h}: eafter={eafter:.4f}, cap={cap:.4f}"
            )

        if charge > max_chg + TOL:
            raise ReplayError(f"charge rate exceeded at hour {h}")
        if disch > max_dis + TOL:
            raise ReplayError(f"discharge rate exceeded at hour {h}")

        prev = eafter
        total_grid += grid
        total_cost += grid * tariff
        peak = max(peak, grid)

    if abs(prev - e0) > TOL:
        raise ReplayError(
            f"end-of-day battery neutrality violated: {prev:.4f} vs initial {e0:.4f}"
        )

    if abs(total_grid - sum(float(e["grid_kwh"]) for e in plan)) > TOL:
        raise ReplayError("total_grid_kwh mismatch")
    if (
        abs(
            total_cost
            - sum(
                float(e["grid_kwh"]) * float(hours[h]["tariff_bdt_per_kwh"])
                for h, e in enumerate(plan)
            )
        )
        > TOL
    ):
        raise ReplayError("total_cost_bdt mismatch")

    # Directive-specific constraints
    for it in interpretation.get("interpretations", []):
        if not it.get("applies"):
            continue
        adj = it.get("structured_adjustment") or {}
        t = it["directive_type"]
        if t == "no_charge_window":
            for hh in adj.get("hours", []):
                for e in plan:
                    if int(e["hour"]) == int(hh):
                        if (
                            e["battery_action"] == "charge"
                            and float(e["battery_kwh"]) > TOL
                        ):
                            raise ReplayError(
                                f"charge occurred in no_charge_window hour {hh}"
                            )
                        break
        elif t == "no_discharge_window":
            for hh in adj.get("hours", []):
                for e in plan:
                    if int(e["hour"]) == int(hh):
                        if (
                            e["battery_action"] == "discharge"
                            and float(e["battery_kwh"]) > TOL
                        ):
                            raise ReplayError(
                                f"discharge occurred in no_discharge_window hour {hh}"
                            )
                        break
        elif t == "max_grid_window":
            cap_h = float(adj["max_grid_kwh"])
            for hh in adj.get("hours", []):
                for e in plan:
                    if int(e["hour"]) == int(hh):
                        if float(e["grid_kwh"]) > cap_h + TOL:
                            raise ReplayError(
                                f"grid cap exceeded at hour {hh}: {e['grid_kwh']} > {cap_h}"
                            )
                        break
