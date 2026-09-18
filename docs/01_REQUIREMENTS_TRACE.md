# Requirements Traceability

Mapping every important rule from the Problem Statement and Participant
Guide to the file(s) that implement it, the validation that enforces it,
and the test that covers it.

## 1. API contract

| Rule | Implementation | Validation | Test |
|---|---|---|---|
| `GET /health` returns `{"status":"ok"}` | `app/api/routes.py::health` | direct | `tests/test_health.py::test_health_ok` |
| `POST /optimize-energy` accepts exact schema | `app/api/routes.py::optimize_energy` | Pydantic models | `tests/test_request_validation.py` |
| HTTP 200 for success | `app/api/routes.py` | direct | `tests/test_api_integration.py::test_all_public_samples_pass_mock` |
| HTTP 400 for malformed JSON | `app/api/error_handlers.py::_validation` | `structurally_valid` flag | `tests/test_api_integration.py::test_malformed_json_returns_400` |
| HTTP 422 for structural validation | `app/api/error_handlers.py::_validation` | `exc.errors()` | `tests/test_api_integration.py::test_missing_fields_returns_400_or_422` |
| HTTP 500 for internal error; no secrets | `app/api/error_handlers.py::_internal` + `app/core/security.py::redact` | manual review | implicit (no raw stack in responses) |

## 2. Operator-note interpretation

| Rule | Implementation | Validation | Test |
|---|---|---|---|
| 1–3 notes | `app/schemas/request_models.py::OptimizeEnergyRequest.operator_notes` | Pydantic field constraint | `tests/test_request_validation.py::test_operator_notes_1_to_3`, `::test_operator_notes_max_3` |
| Exactly one interpretation per note | `app/services/guardrails.py::validate_interpretation` | count check | `tests/test_guardrails.py::test_wrong_count_rejected` |
| `note_index` 0..N-1 unique | `app/services/guardrails.py::validate_interpretation` | set comparison | `tests/test_guardrails.py::test_duplicate_note_index_rejected` |
| `applies=false` only for `no_op` | `app/services/guardrails.py::validate_interpretation` | branch | `tests/test_guardrails.py::test_no_op_with_applies_true_rejected` |
| `no_op` requires `structured_adjustment=null` | `app/services/guardrails.py` | branch | `tests/test_guardrails.py::test_no_op_must_have_null_adjustment` |
| Non-`no_op` requires `applies=true` | `app/services/guardrails.py` | branch | `tests/test_guardrails.py::test_non_no_op_requires_adjustment` |
| Allowed directive types only | `app/services/guardrails.py::ALLOWED_TYPES` | membership | `tests/test_guardrails.py::test_invalid_directive_type_rejected` |
| Hours unique integers 0–23 ascending | `app/services/guardrails.py::_check_hours` | checks | `tests/test_guardrails.py::test_hours_unsorted_rejected`, `::test_hours_out_of_range_rejected`, `::test_duplicate_hours_rejected` |
| `solar_reduction.factor` ∈ [0,1] | `app/services/guardrails.py::_check_factor` | range | `tests/test_guardrails.py::test_solar_factor_out_of_range_rejected` |
| Battery reserve ≤ capacity | `app/services/guardrails.py::_check_adjustment` | comparison | `tests/test_guardrails.py::test_reserve_above_capacity_rejected` |
| `max_grid_kwh` ≥ 0 | `app/services/guardrails.py::_check_finite_nonneg` | sign | `tests/test_guardrails.py::test_max_grid_negative_rejected` |
| Paraphrase robustness | `app/services/llm_prompting.py::SYSTEM_PROMPT` (extensive examples) | live LLM smoke | implicit (no LLM in CI; manual verification) |
| Hidden language variation | prompt covers "drop to 20%", "80% reduction", "half remains", etc. | live LLM | manual |

## 3. Time rules

| Rule | Implementation | Validation | Test |
|---|---|---|---|
| 1 PM to 3 PM → [13, 14] | `SYSTEM_PROMPT` examples | live LLM | `scripts/edge_case_matrix.py::EDGE-TW-2` |
| 6 PM until 9 PM → [18, 19, 20] | `SYSTEM_PROMPT` examples | live LLM | `::EDGE-TW-3`, `::EDGE-GC-1` |
| 11 AM until 1 PM → [11, 12] | prompt example | live LLM | `::EDGE-TW-4` |
| Start inclusive, end exclusive | prompt enforces + guardrails enforce sorted unique ints | deterministic | implicit in all solar_reduction / window tests |
| Whole-hour intervals | guardrails reject non-integer hours | deterministic | `tests/test_guardrails.py::test_hours_out_of_range_rejected` |

## 4. Solar reduction rules

| Rule | Implementation | Validation | Test |
|---|---|---|---|
| Factor is usable fraction remaining | `app/services/llm_prompting.py::SYSTEM_PROMPT` | prompt | `scripts/edge_case_matrix.py::EDGE-SW-*` |
| 80% reduction → factor 0.2 | prompt example | live LLM | `::EDGE-SW-2` |
| "Drop to 20%" → 0.2 | prompt example | live LLM | `::EDGE-SW-1` |
| `effective_solar[h] = original * factor` | `app/services/directive_compiler.py::compile_directives` | replay | `tests/test_directive_compiler.py::test_compile_all`, replay in `tests/test_replay_validator.py` |

## 5. Battery reserve rules

| Rule | Implementation | Validation | Test |
|---|---|---|---|
| Absolute kWh reserve | `app/services/directive_compiler.py` | replay | `tests/test_directive_compiler.py::test_compile_all` |
| Percentage reserve → kWh | `SYSTEM_PROMPT` instructs LLM | live LLM | `::EDGE-RV-2` |
| `active_min[h] = max(base, directive)` | `app/services/directive_compiler.py` | replay | `tests/test_directive_compiler.py::test_compile_all` |
| Reserve applies to `battery_energy_after_kwh` | MILP constraint + replay | replay | `tests/test_optimizer.py::test_basic_optimal_solves` + replay |

## 6. `no_charge_window`

| Rule | Implementation | Validation | Test |
|---|---|---|---|
| Charge = 0 in listed hours | MILP constraint + replay | replay | `tests/test_optimizer.py::test_no_charge_window_forces_charge_to_zero` |

## 7. `no_discharge_window`

| Rule | Implementation | Validation | Test |
|---|---|---|---|
| Discharge = 0 in listed hours | MILP constraint + replay | replay | implicit in optimizer tests + replay |

## 8. `max_grid_window`

| Rule | Implementation | Validation | Test |
|---|---|---|---|
| `grid_kwh[h] ≤ max_grid_kwh` | MILP constraint + replay | replay | `tests/test_optimizer.py::test_max_grid_caps_grid` |

## 9. `no_op`

| Rule | Implementation | Validation | Test |
|---|---|---|---|
| `applies=false` | guardrail | deterministic | `tests/test_guardrails.py::test_no_op_with_applies_true_rejected` |
| `directive_type=no_op` | guardrail | deterministic | implicit |
| `structured_adjustment=null` | guardrail | deterministic | `tests/test_guardrails.py::test_no_op_must_have_null_adjustment` |
| No effect on optimization | `directive_compiler.py` skips non-applies | compiler | `tests/test_directive_compiler.py` |

## 10. Battery rules

| Rule | Implementation | Validation | Test |
|---|---|---|---|
| Charge/discharge/idle transitions | `app/services/plan_builder.py::_decide_action` | direct | `tests/test_plan_builder.py::test_build_plan_basic` |
| Battery bounds | MILP `lowBound`/`upBound` on `e_after` | replay | `tests/test_replay_validator.py::test_basic_passes` |
| Charge/discharge rate limits | MILP `charge[h] ≤ max_chg` | replay | `tests/test_replay_validator.py` |
| End-of-day neutrality | MILP `e_after[23] == e0` + replay | replay | `tests/test_optimizer.py::test_end_of_day_neutrality`, `tests/test_replay_validator.py::test_final_neutrality_violation_detected` |

## 11. Energy rules

| Rule | Implementation | Validation | Test |
|---|---|---|---|
| Hourly energy balance | MILP `grid + solar + disch == demand + charge` | replay | `tests/test_replay_validator.py::test_balance_violation_detected` |
| `solar_used_kwh ≤ effective_solar_kwh` | MILP `upBound` + replay | replay | `tests/test_replay_validator.py` (via `test_basic_passes`) |
| Unused solar curtailed (no export) | MILP `upBound`, no negative grid | implicit | optimizer tests |
| Non-negative values | Pydantic + MILP `lowBound` | replay | `tests/test_replay_validator.py` (negative-value detection) |
| Finite values | Pydantic + solver | manual | implicit |

## 12. Optimization

| Rule | Implementation | Validation | Test |
|---|---|---|---|
| Minimize total grid cost | `app/services/optimizer.py` objective | solver status | `tests/test_optimizer.py::test_basic_optimal_solves` |
| Invalid schedule receives no optimization credit | 500 on solver failure / replay failure | error handler | `app/api/error_handlers.py` |
| Cost only matters after validity | replay validator before response | `app/services/replay_validator.py` | end-to-end |

## 13. Response schema

| Rule | Implementation | Validation | Test |
|---|---|---|---|
| `scenario_id` echo | `app/api/routes.py` | direct | `tests/test_api_integration.py::test_all_public_samples_pass_mock` |
| `directive_interpretation` | included | direct | same |
| `hourly_plan` (24 entries) | `app/services/plan_builder.py` | direct | same |
| `total_grid_kwh`, `total_cost_bdt`, `peak_grid_kwh` recomputed | `app/services/plan_builder.py::recompute_totals` | replay | `scripts/multi_agent_qa.py::cost_agent` |
| `plan_summary` | `app/services/summary_service.py` | deterministic | `tests/test_plan_builder.py::test_summary_includes_no_op_note` |

## 14. Guardrails

| Rule | Implementation | Validation | Test |
|---|---|---|---|
| LLM output untrusted | retry-on-failure path | `tests/test_interpretation_service.py::test_repair_retry_on_guardrail_failure` |
| Allowed directive types only | `ALLOWED_TYPES` | `tests/test_guardrails.py::test_invalid_directive_type_rejected` |
| Hours unique ints 0–23 ascending | `_check_hours` | dedicated tests |
| Solar factor 0..1 | `_check_factor` | dedicated test |
| Reserve finite non-negative ≤ capacity | `_check_finite_nonneg` + comparison | dedicated test |
| Grid cap finite non-negative | `_check_finite_nonneg` | dedicated test |
| No invention | `extra="forbid"` on Pydantic + guardrail whitelist | implicit |
| Safe failure on malformed LLM output | `InterpretationError` → 400 | manual |

## 15. Performance / reliability

| Rule | Implementation | Validation | Test |
|---|---|---|---|
| Health ready within 60s | startup is lightweight | manual + Docker healthcheck | Dockerfile HEALTHCHECK |
| Request timeout < 30s | optimizer `timeLimit=10s`, LLM `timeout=10s` | manual | `scripts/multi_agent_qa.py::perf_agent` |
| p95 ≤ 5s | mock path measured at ~1.6 ms | manual | `QA_REPORT.md` |
| Stable repeated requests | MILP deterministic + cache | direct | `tests/test_api_integration.py::test_repeated_request_is_stable` |
| Malformed input handled safely | 400/422 with generic body | direct | `tests/test_api_integration.py` |
| No secrets in logs / responses | `app/core/security.py::redact` + custom error handlers | manual |

## 16. Deployment / docs

| Rule | Implementation | Validation | Test |
|---|---|---|---|
| Public API | `uvicorn app.main:app --host 0.0.0.0` | direct | Dockerfile CMD |
| Docker fallback | `Dockerfile` + `docker-compose.yml` | direct | `docker compose up -d` |
| README quickstart | `README.md` | manual review | — |
| Environment variable names | `.env.example` | manual | — |
| Model / provider documentation | `README.md` section | manual | — |
| No secrets in repo | `.gitignore`, empty `.env.example` | manual | — |
| 3-min video tie-break | `docs/07_VIDEO_SCRIPT.md` | manual | — |