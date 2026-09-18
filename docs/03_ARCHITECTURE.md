# Architecture

## Request flow

```
HTTP POST /optimize-energy
   │
   ▼
┌──────────────────────────────────────────────┐
│  FastAPI + Pydantic request validation       │
│  - 400 malformed JSON                         │
│  - 422 structural validation                  │
└──────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────┐
│  Cache lookup (SHA-256 of canonical JSON)     │
│  - hit  -> return cached body                 │
│  - miss -> continue                          │
└──────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────┐
│  LLM interpretation (Groq OpenAI-compatible)  │
│  - openai Python SDK                          │
│  - JSON mode when reasoning disabled;         │
│    reasoning_effort via extra_body otherwise  │
│  - extract_json strips <think>...</think>     │
│  - SYSTEM_PROMPT + user prompt                │
└──────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────┐
│  Deterministic guardrails                     │
│  - exactly N interpretations                  │
│  - directive_type whitelist                   │
│  - applies semantics                          │
│  - hours shape                                │
│  - numeric ranges                             │
│  - retry on failure (max 3 attempts)         │
└──────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────┐
│  Directive compiler                           │
│  - effective_solar[h]                         │
│  - active_minimum[h]                          │
│  - no_charge_hours / no_discharge_hours      │
│  - max_grid[h]                                │
└──────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────┐
│  MILP optimizer (PuLP + CBC)                  │
│  - 24-hour horizon                            │
│  - 168 variables (≈ 120 real + 48 binary)    │
│  - solve in <1s typical                       │
│  - 10s time limit                             │
└──────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────┐
│  Plan builder                                 │
│  - battery_action ∈ {charge,discharge,idle}  │
│  - battery_kwh magnitude                      │
│  - battery_energy_after_kwh                   │
│  - numerical cleanup (epsilon 1e-6)           │
└──────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────┐
│  Replay validator (independent check)         │
│  - 24 hours                                   │
│  - energy balance per hour                    │
│  - battery transitions + bounds + rates       │
│  - end-of-day neutrality                      │
│  - directive application                      │
│  - tolerance 0.01 kWh / 0.01 BDT              │
└──────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────┐
│  Summary service (deterministic)              │
│  - applied directives                         │
│  - ignored notes                              │
│  - battery strategy                           │
│  - cost outcome                               │
└──────────────────────────────────────────────┘
   │
   ▼
JSON response + cache put
```

## Component responsibilities

| Component | Responsibility | LOC budget |
|---|---|---|
| `routes.py` | HTTP entry points | ~80 |
| `error_handlers.py` | 400/422/500 mapping | ~50 |
| `dependencies.py` | DI; mock routing | ~50 |
| `llm_client.py` | OpenRouter transport | ~80 |
| `llm_prompting.py` | Prompt construction | ~100 |
| `guardrails.py` | Deterministic validation | ~150 |
| `interpretation_service.py` | LLM + guardrail + retry | ~40 |
| `directive_compiler.py` | Per-hour constraints | ~70 |
| `optimizer.py` | MILP model | ~110 |
| `plan_builder.py` | Vars → entries + totals | ~60 |
| `replay_validator.py` | Independent check | ~140 |
| `summary_service.py` | Deterministic text | ~50 |
| `cache.py` | TTL in-memory cache | ~40 |
| `json_utils.py` | Robust extraction | ~70 |

## Data contracts

### Request

```json
{
  "scenario_id": "SAMPLE-01",
  "operator_notes": ["Solar drops to 20% 12-2 PM.", "Cafeteria menu changes."],
  "hours": [
    {"hour": 0, "demand_kwh": 100, "solar_kwh": 0, "tariff_bdt_per_kwh": 10},
    ...
    {"hour": 23, "demand_kwh": 100, "solar_kwh": 0, "tariff_bdt_per_kwh": 10}
  ],
  "battery": {
    "capacity_kwh": 200,
    "initial_energy_kwh": 100,
    "minimum_energy_kwh": 30,
    "max_charge_kwh_per_hour": 50,
    "max_discharge_kwh_per_hour": 50
  }
}
```

### Response

```json
{
  "scenario_id": "SAMPLE-01",
  "directive_interpretation": [
    {
      "note_index": 0,
      "applies": true,
      "directive_type": "solar_reduction",
      "structured_adjustment": {"hours": [12, 13], "factor": 0.2},
      "explanation": "Solar reduced 12-13 to 20%."
    },
    {
      "note_index": 1,
      "applies": false,
      "directive_type": "no_op",
      "structured_adjustment": null,
      "explanation": "Not relevant to today's schedule."
    }
  ],
  "hourly_plan": [
    {"hour": 0, "grid_kwh": 100.0, "solar_used_kwh": 0.0,
     "battery_action": "idle", "battery_kwh": 0.0,
     "battery_energy_after_kwh": 100.0},
    ...
  ],
  "total_grid_kwh": 2400.0,
  "total_cost_bdt": 24000.0,
  "peak_grid_kwh": 100.0,
  "plan_summary": "Applied: solar reduced to 0.2 during hours 12,13. ..."
}
```