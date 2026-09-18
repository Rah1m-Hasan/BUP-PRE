"""FastAPI routes: GET /health and POST /optimize-energy."""

from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_interpretation_service
from app.schemas.request_models import OptimizeEnergyRequest
from app.services.cache import cache
from app.services.directive_compiler import compile_directives
from app.services.interpretation_service import (
    InterpretationError,
    InterpretationService,
)
from app.services.optimizer import OptimizerError, optimize
from app.services.plan_builder import build_plan, recompute_totals
from app.services.replay_validator import ReplayError, replay_validate
from app.services.summary_service import build_summary

router = APIRouter()


@router.get("/health")
def health():
    """Readiness endpoint. Must return HTTP 200 with status=ok."""
    return {"status": "ok"}


@router.post("/optimize-energy")
def optimize_energy(
    req: OptimizeEnergyRequest,
    svc: InterpretationService = Depends(get_interpretation_service),
):
    hours_dicts = [h.model_dump() for h in req.hours]
    battery_dict = req.battery.model_dump()
    payload = {
        "scenario_id": req.scenario_id,
        "operator_notes": req.operator_notes,
        "hours": hours_dicts,
        "battery": battery_dict,
    }
    k = cache.key(payload)
    cached = cache.get(k)
    if cached:
        return cached

    try:
        interpretation = svc.interpret(
            scenario_id=req.scenario_id,
            notes=req.operator_notes,
            battery=battery_dict,
        )
    except InterpretationError as e:
        raise HTTPException(status_code=400, detail=f"interpretation_failed: {e}")

    compiled = compile_directives(interpretation, battery_dict, hours_dicts)

    try:
        opt = optimize(compiled, battery_dict, hours_dicts, time_limit_seconds=10)
    except OptimizerError as e:
        raise HTTPException(status_code=500, detail=f"optimizer_failed: {e}")

    plan = build_plan(opt, hours_dicts)
    tg, tc, pk = recompute_totals(plan, hours_dicts)
    summary = build_summary(interpretation, opt)

    try:
        replay_validate(
            plan, hours_dicts, battery_dict, compiled, interpretation, req.scenario_id
        )
    except ReplayError as e:
        raise HTTPException(status_code=500, detail=f"replay_failed: {e}")

    body = {
        "scenario_id": req.scenario_id,
        "directive_interpretation": interpretation["interpretations"],
        "hourly_plan": plan,
        "total_grid_kwh": round(tg, 6),
        "total_cost_bdt": round(tc, 6),
        "peak_grid_kwh": round(pk, 6),
        "plan_summary": summary,
    }
    cache.put(k, body)
    return body
