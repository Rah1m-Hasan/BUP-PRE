# Deep Implementation Plan

This document is the engineering plan for the GridWise preliminary
solution. It complements `docs/01_REQUIREMENTS_TRACE.md` (which maps
every rule to code) by describing the architecture, design choices, and
risk mitigation in narrative form.

## 1. Architecture

The system is a stateless public HTTP service. Each request is fully
self-contained; nothing is persisted between requests (no database).

```
POST /optimize-energy
   │
   ▼
Pydantic request validation (400 on malformed, 422 on semantic)
   │
   ▼
Canonical request → SHA-256 cache key
   │
   ▼ (cache miss)
LLM interpretation via OpenRouter
   │
   ▼
Deterministic guardrail validation (retry-on-failure, max 3 attempts)
   │
   ▼
Directive compiler (per-hour constraint data)
   │
   ▼
PuLP MILP optimizer (CBC, time limit 10 s)
   │
   ▼
Plan builder (battery action / magnitudes)
   │
   ▼
Replay validator (independent physics + directive check)
   │
   ▼
Summary service (deterministic text)
   │
   ▼
JSON response, cached for 300 s
```

## 2. Module design

```
app/
  main.py             FastAPI app factory, lifespan, error handler install
  api/
    routes.py         /health, /optimize-energy
    error_handlers.py  400 / 422 / 500 mapping; secret redaction
    dependencies.py   DI for InterpretationService (mock-aware)
  core/
    config.py         Pydantic Settings (env-driven)
    logging.py        structured stdout logging
    security.py       secret redaction utilities
  schemas/
    request_models.py OptimizeEnergyRequest, HourEntry, Battery
    response_models.py OptimizeEnergyResponse, HourlyPlanEntry
    directive_models.py DirectiveInterpretation, structured shapes
  services/
    llm_client.py     OpenAI SDK wrapper pointed at OpenRouter
    llm_prompting.py  SYSTEM_PROMPT + user/repair prompt builders
    interpretation_service.py orchestrates LLM + guardrail + retry
    guardrails.py     deterministic validator (single source of truth)
    directive_compiler.py translates interpretation -> per-hour data
    optimizer.py     PuLP model + solve + numerical cleanup
    plan_builder.py   optimized vars -> hourly_plan + totals
    replay_validator.py independent physics + directive check
    summary_service.py deterministic plan_summary text
    cache.py          TTL in-memory cache keyed by SHA256 of canonical JSON
  utils/
    json_utils.py     robust JSON extraction from LLM output
```

## 3. LLM prompt strategy

`SYSTEM_PROMPT` (`app/services/llm_prompting.py`) is the contract between
this service and the model. It:

1. States the role: "operator-note interpreter".
2. States that output feeds deterministic Python validation and a MILP.
3. Defines the time-window convention with multiple worked examples.
4. Defines the six allowed directive types and their required
   `structured_adjustment` shape.
5. Defines the solar factor rule (usable fraction remaining) with
   worked examples for "80% reduction", "drop to 20%", "half remains",
   "one-fifth of normal", "25% of forecast".
6. Defines the percentage-to-kWh battery reserve conversion.
7. Defines `no_op` semantics for irrelevant notes.
8. Forbids invented directive types or altered base parameters.
9. Specifies the strict JSON output schema.
10. Includes 9 worked-out examples.

Repair prompts are precise (one error per retry) and instruct the model
to return ONLY corrected JSON, with no commentary or fences.

## 4. Guardrail strategy

Guardrails (`app/services/guardrails.py`) are deterministic Python
validation. Every check raises `GuardrailError` with a precise message
that the `InterpretationService` feeds back to the LLM as repair
context. Up to `max_attempts=3` retries are attempted. After the final
failure, the request returns a controlled 400 — never an invented
directive.

The guardrails enforce (Problem Statement Section 08):

- Exactly one interpretation per operator note
- `note_index` 0..N-1, no duplicates, no gaps
- `directive_type` ∈ allowed enum
- `applies=false` only for `no_op`
- `structured_adjustment=null` only for `no_op`
- All other directives require their specific shape
- `hours` unique integers 0..23 in ascending order
- `solar_reduction.factor` ∈ [0, 1]
- Battery reserve finite, non-negative, ≤ capacity
- `max_grid_kwh` finite, non-negative
- `explanation` non-empty, ≤ 500 chars

## 5. Optimizer model

MILP via PuLP. Variables, constraints, and objective are spelled out in
`app/services/optimizer.py` and in `README.md`. Highlights:

- 24-hour horizon with per-hour grid, solar, charge, discharge,
  energy_after, and two binary indicators (y_chg, y_dis).
- Energy balance: `grid + solar + disch = demand + charge`.
- Battery transition: `e_after[h] = e_after[h-1] + charge - disch`; with
  `e_after[-1] = initial_energy_kwh` (end-of-day neutrality).
- Rate caps: `charge[h] ≤ max_chg`, `disch[h] ≤ max_dis`.
- Window caps: `charge[h] = 0` in no-charge hours;
  `disch[h] = 0` in no-discharge hours.
- Grid caps: `grid[h] ≤ max_grid[h]`.
- Mutual exclusion: `charge[h] ≤ BIG * y_chg[h]`,
  `disch[h] ≤ BIG * y_dis[h]`, `y_chg[h] + y_dis[h] ≤ 1`.

Objective: `minimize Σ grid[h] * tariff[h]`.

Solver: PuLP's bundled CBC. Time limit 10 s. Non-Optimal status yields
controlled 500.

## 6. Testing strategy

| Layer | Tests |
|---|---|
| Schema | `tests/test_request_validation.py` (10 cases) |
| Security | `tests/test_security.py` |
| Config | `tests/test_config.py` |
| JSON utils | `tests/test_json_utils.py` |
| Guardrails | `tests/test_guardrails.py` (14 cases) |
| LLM client | `tests/test_llm_client.py` |
| Interpretation service | `tests/test_interpretation_service.py` (retry + exhaust) |
| Directive compiler | `tests/test_directive_compiler.py` |
| Optimizer | `tests/test_optimizer.py` (5 cases) |
| Plan builder | `tests/test_plan_builder.py` |
| Replay validator | `tests/test_replay_validator.py` |
| Cache | `tests/test_cache.py` |
| End-to-end | `tests/test_api_integration.py` (10 public samples + error paths) |
| Public samples | `scripts/test_public_samples.py` (10 cases, exact cost match) |
| Edge cases | `scripts/edge_case_matrix.py` (24 cases) |
| Multi-agent QA | `scripts/multi_agent_qa.py` (7 agents, writes `QA_REPORT.md`) |
| Submission | `scripts/generate_submission_checklist.py` |

## 7. Docker strategy

- `python:3.12-slim` base image
- `requirements.txt` only (no dev deps, no tests, no docs in image)
- Non-root user (`gridwise`, UID 1000)
- Healthcheck via Python stdlib `urllib.request`
- Bind `0.0.0.0:8000`
- No `.env` baked in; secrets injected at runtime
- `docker-compose.yml` with healthcheck and `restart: unless-stopped`

## 8. Git strategy

Conventional commits, one per logical step:

1. `chore: initialize project scaffold`
2. `feat: add typed config, logging, secret redaction`
3. `feat: add request, response, and directive Pydantic schemas`
4. `feat: add FastAPI skeleton with /health and /optimize-energy routes`
5. `feat: add deterministic LLM-output guardrails with full coverage`
6. `feat: add OpenRouter LLM client with prompt, repair, and JSON extraction`
7. `feat: add interpretation service with retry-on-guardrail-failure`
8. `feat: add directive compiler turning validated directives into constraints`
9. `feat: add MILP optimizer (PuLP+CBC) with all GridWise constraints`
10. `feat: add plan builder, totals recomputer, and deterministic summary`
11. `feat: add independent replay validator for energy, battery, directives`
12. `feat: wire end-to-end pipeline with cache and replay validation`
13. `test: add public samples harness and multi-agent QA scaffold`
14. `test: full multi-agent QA, edge-case matrix, and QA report`
15. `build: add Dockerfile, dockerignore, and docker-compose with healthcheck`
16. `docs: README, traceability, architecture, scoring, deployment, video script`

## 9. Risk mitigation

| Risk | Mitigation |
|---|---|
| LLM hallucinates a directive type | Guardrail whitelist (6 only); retry with error; safe 400 |
| LLM miscomputes factor | Guardrail enforces `[0, 1]`; examples in prompt |
| LLM miscomputes reserve | Guardrail enforces ≤ capacity; prompt gives capacity context |
| LLM timeout | `LLM_TIMEOUT_SECONDS=10`; no transport retry (avoids pile-up) |
| Solver infeasibility | Organizer promises feasibility; non-Optimal → 500 |
| Solver numerical noise | Epsilon cleanup (1e-6) before plan builder |
| End-of-day neutrality | MILP hard constraint + replay check |
| Secret leak | `.gitignore`, `.env.example` empty, logger redaction, response hygiene |
| p95 spikes | CBC `timeLimit=10s`; LLM `timeout=10s`; cache for repeats |
| Mock contamination | `LLM_MOCK=false` default; mock only via env or test injection |
| Hidden paraphrase | Prompt covers many phrasings; guardrail accepts any valid result |

## 10. Scoring strategy

Per the Participant Guide Section 7 (100 total):

- 25 LLM interpretation — robust prompt with examples; guardrails repair.
- 25 directive application + constraint correctness — full MILP + replay.
- 10 optimization quality — MILP achieves exact optimal cost on every
  public sample (0.000 % drift).
- 10 API contract — exact schema; Pydantic validation; proper HTTP codes.
- 10 performance / reliability — p95 ≈ 1.6 ms on mock; cache + 10s caps.
- 10 deployment / Docker fallback — Dockerfile, compose, healthcheck.
- 10 documentation / local reproducibility — self-contained README.

## 11. Edge-case matrix index

See `docs/04_EDGE_CASE_MATRIX.md` for the full matrix. The script
`scripts/edge_case_matrix.py` covers 24 synthetic scenarios across:

- Time windows (8 cases)
- Solar wording variations (6 cases)
- Reserve styles (3 cases)
- Grid caps (3 cases)
- Directive combinations + distractors (4 cases)

## 12. Final submission checklist

See `SUBMISSION_CHECKLIST.md` (generated by
`scripts/generate_submission_checklist.py`). Mirrors the Participant
Guide Section 11 final pre-submit checklist.