# GridWise — LLM-Assisted 24-Hour Energy Optimization

A submission-ready FastAPI service for the **BUP CSE Fest 2026 Hackathon Preliminary — GridWise LLM-Assisted Sample Case Pack**.

The service interprets free-text operator notes via an LLM, validates the
structured interpretation with deterministic guardrails, compiles the
directives into a MILP model, and returns a valid low-cost 24-hour energy
schedule that satisfies all GridWise rules.

## Architecture

```
                            GridWise
   ┌──────────────────────────────────────────────────────────────┐
   │                                                              │
   │   Operator Notes + 24h Scenario                              │
   │           │                                                  │
   │           ▼                                                  │
   │   ┌────────────────┐    JSON      ┌─────────────────────┐    │
   │   │   LLM (LLM)    │────────────▶ │  Deterministic      │    │
   │   │ Groq via       │              │  Guardrails         │    │
   │   │ openai SDK     │              │  (retry on fail)    │    │
   │   └────────────────┘              └──────────┬──────────┘    │
   │                                              │               │
   │                                              ▼               │
   │                                  ┌─────────────────────┐     │
   │                                  │ Directive Compiler  │     │
   │                                  │ effective_solar[h]  │     │
   │                                  │ active_minimum[h]   │     │
   │                                  │ no_charge/_discharge│     │
   │                                  │ max_grid_caps[h]    │     │
   │                                  └──────────┬──────────┘     │
   │                                              │               │
   │                                              ▼               │
   │                                  ┌─────────────────────┐     │
   │                                  │ MILP Optimizer      │     │
   │                                  │ (PuLP + CBC)        │     │
   │                                  │ minimize Σ grid*tariff│   │
   │                                  └──────────┬──────────┘     │
   │                                              │               │
   │                                              ▼               │
   │                                  ┌─────────────────────┐     │
   │                                  │ Plan Builder        │     │
   │                                  │ + Replay Validator  │     │
   │                                  │ + Summary Service   │     │
   │                                  └──────────┬──────────┘     │
   │                                              │               │
   └──────────────────────────────────────────────┼───────────────┘
                                                  ▼
                                       Valid 24h schedule
```

Human notes → LLM → guardrails → MILP → replay validation → response.

## Technology stack

| Concern | Library |
|---|---|
| HTTP | FastAPI + Uvicorn |
| Validation | Pydantic v2 + pydantic-settings |
| LLM | Official `openai` Python SDK pointed at **Groq** (`api.groq.com/openai/v1`) |
| Optimizer | PuLP (MILP) with bundled CBC solver |
| JSON extraction | Custom robust extractor (fenced blocks, prose, balanced braces, `<think>` strip) |
| Tests | pytest + FastAPI TestClient |
| Container | python:3.12-slim + Docker + docker-compose |

## Endpoints

### `GET /health`

```bash
curl -sf http://127.0.0.1:8000/health
# {"status":"ok"}
```

### `POST /optimize-energy`

Accepts the exact request schema from the Problem Statement and returns the
exact response schema.

```bash
curl -sf -X POST http://127.0.0.1:8000/optimize-energy \
  -H 'content-type: application/json' \
  --data @sample_request.json
```

See `docs/03_ARCHITECTURE.md` for the full schema.

## Environment variables

Set these in `.env` (loaded automatically) or your platform's secret store.
**Never commit `.env`.** The included `.env.example` shows every variable name.

| Variable | Required | Default | Description |
|---|---|---|---|
| `GROQ_API_KEY` | Yes (production) | _empty_ | Groq API key |
| `GROQ_BASE_URL` | No | `https://api.groq.com/openai/v1` | Groq OpenAI-compatible endpoint |
| `LLM_MODEL` | No | `openai/gpt-oss-120b` | Model identifier on Groq |
| `LLM_TEMPERATURE` | No | `0` | Sampling temperature |
| `LLM_REASONING_EFFORT` | No | `low` | `""` disables reasoning; `low`/`medium`/`high` enables it (reasoning models only) |
| `LLM_TIMEOUT_SECONDS` | No | `10` | Per-call timeout |
| `LLM_MAX_RETRIES` | No | `2` | Repair-attempt budget after guardrail failure |
| `LLM_MOCK` | No | `false` | `true` enables deterministic in-process mock (testing only) |
| `APP_HOST` | No | `0.0.0.0` | Bind address |
| `APP_PORT` | No | `8000` | Bind port |
| `LOG_LEVEL` | No | `INFO` | Log verbosity |

## Local quickstart

```bash
# 1. Clone
git clone <your-repo-url> gridwise
cd gridwise

# 2. Create a virtualenv (optional but recommended)
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements-dev.txt

# 4. Configure environment
cp .env.example .env
# Edit .env and set GROQ_API_KEY=<your real key>

# 5. Run the service
./scripts/run_local.sh
# OR
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 6. Smoke-test
curl -sf http://127.0.0.1:8000/health
# {"status":"ok"}

# 7. Try a public sample (in mock mode, no API key required)
LLM_MOCK=true python scripts/test_public_samples.py --mock
```

## Docker quickstart

```bash
# Build
docker compose build

# Start
docker compose up -d

# Healthcheck (Docker's own)
docker compose ps   # status = healthy

# Smoke test
curl -sf http://127.0.0.1:8000/health
```

To stop: `docker compose down`.

## Testing

| Command | Purpose |
|---|---|
| `pytest -q` | All unit + integration tests |
| `LLM_MOCK=true pytest -q` | Same, with deterministic mock LLM |
| `LLM_MOCK=true python scripts/test_public_samples.py --mock` | 10-case public reference runner |
| `LLM_MOCK=true python scripts/edge_case_matrix.py` | 24-case edge-case matrix |
| `LLM_MOCK=true python scripts/multi_agent_qa.py --mock` | 7-agent QA report → `QA_REPORT.md` |
| `python scripts/generate_submission_checklist.py` | Submission checklist from QA state |

## Public sample cases

All 10 cases in `BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json` are
covered by `scripts/test_public_samples.py`. With the deterministic mock
LLM, the optimizer achieves **0.000 % cost drift versus the reference
schedule for every case**, every plan is valid, and all directives are
correctly applied.

## LLM role

The LLM is **mandatory** in the operator-note interpretation path. The
LLM converts free-text notes into a structured `directive_interpretation`
array; that array is fed through deterministic Python guardrails and then
into the MILP model. The LLM is not used for `plan_summary`,
documentation, or any other cosmetic purpose.

**Default backend:** Groq (`https://api.groq.com/openai/v1`) with model
`openai/gpt-oss-120b`. The backend is configurable via `GROQ_BASE_URL`
and `LLM_MODEL`; any OpenAI-API-compatible endpoint will work (OpenRouter,
Together, Anyscale, Fireworks, local llama.cpp, etc.).

The system prompt (`app/services/llm_prompting.py`) defines:

- The allowed six directive types and their `structured_adjustment` shapes
- The whole-hour time-window convention (start inclusive, end exclusive)
- The solar factor rule (usable fraction remaining)
- The percentage-to-kWh battery reserve conversion
- The `no_op` semantics for irrelevant notes
- The prohibition on invented directive types or parameter changes

If the LLM output fails guardrail validation, the service retries with a
precise repair prompt (up to `LLM_MAX_RETRIES` times). Repeated failures
yield a controlled 400 response — never an invalid directive.

## Guardrails

`app/services/guardrails.py` is a strict, deterministic validator. It
enforces (from Problem Statement Section 08):

- Exactly one `directive_interpretation` entry per operator note
- `note_index` values are 0..N-1 with no duplicates or gaps
- `directive_type` ∈ {`solar_reduction`, `minimum_battery_reserve`,
  `no_charge_window`, `no_discharge_window`, `max_grid_window`, `no_op`}
- `applies=false` only for `no_op`; `applies=true` for every other type
- `no_op` requires `structured_adjustment=null`
- All other directives require their specific `structured_adjustment`
  shape
- `hours` are unique integers 0..23 in ascending order
- `solar_reduction.factor` ∈ [0, 1]
- Battery reserve finite, non-negative, ≤ capacity
- `max_grid_kwh` finite, non-negative
- No invented fields or directive types
- `explanation` non-empty, ≤ 500 chars

## Optimizer / solver

`app/services/optimizer.py` builds a mixed-integer linear program using
PuLP. Decision variables per hour `h`:

| Variable | Range | Meaning |
|---|---|---|
| `grid[h]` | ≥ 0 | grid energy purchased (kWh) |
| `solar[h]` | [0, effective_solar[h]] | solar used (kWh) |
| `charge[h]` | ≥ 0 | battery charge (kWh) |
| `disch[h]` | ≥ 0 | battery discharge (kWh) |
| `e_after[h]` | [active_min[h], capacity] | battery energy after hour h (kWh) |
| `y_chg[h]`, `y_dis[h]` | {0,1} | binary flags preventing simultaneous charge and discharge |

Constraints enforce: hourly energy balance, battery transition,
end-of-day neutrality (`e_after[23] = initial_energy_kwh`), rate caps,
window caps (`charge[h] = 0` in no-charge hours, etc.), grid caps
(`grid[h] ≤ max_grid[h]`), and mutual exclusion.

Objective: `minimize Σ grid[h] * tariff[h]`.

Solver: PuLP's bundled CBC. Time limit: 10 s. If non-Optimal status is
returned, the service returns 500 (never an invalid plan).

## Replay validator

`app/services/replay_validator.py` independently replays the final plan
against the directive ground truth and GridWise rules. Tolerance: 0.01
kWh / 0.01 BDT (per Problem Statement Section 11.5). If replay fails,
the service returns 500.

## Known limitations

- Real-LLM cost and latency depend on Groq availability and the chosen
  model. A 10-second per-call timeout keeps p95 bounded; the cache
  (`app/services/cache.py`) eliminates repeated-call cost for identical
  requests during testing.
- Reasoning models (e.g. `openai/gpt-oss-120b`) emit `<think>...</think>`
  blocks; `app/utils/json_utils.py` strips these before extracting JSON.
- Hidden judge cases are not published; the system is engineered for
  paraphrase robustness via the LLM prompt and guardrail normalization.
- PuLP's bundled CBC is sufficient for the 24-hour horizon; the model is
  small (≈ 200 variables, 24 binary indicators) and solves in well under
  one second on commodity hardware.

## Secret handling

- `.env` is git-ignored.
- `.env.example` ships with the API key field empty.
- The Dockerfile does not `COPY .env`; secrets are injected at runtime
  via `env_file` / Docker `--env-file` / platform secret store.
- The structured logger (`app/core/logging.py`) redacts authorization
  headers and `sk-…` / `gsk_…` keys.
- HTTP responses never echo secrets or stack traces.

## Credits

- [FastAPI](https://fastapi.tiangolo.com/) — modern HTTP framework
- [Pydantic](https://docs.pydantic.dev/) — data validation
- [OpenAI Python SDK](https://github.com/openai/openai-python) — Groq-compatible client
- [PuLP](https://coin-or.github.io/pulp/) — MILP modeling
- [CBC](https://github.com/coin-or/Cbc) — open-source MILP solver
- [pytest](https://docs.pytest.org/) — testing

## License

Internal submission package for BUP CSE Fest 2026. Not for redistribution.