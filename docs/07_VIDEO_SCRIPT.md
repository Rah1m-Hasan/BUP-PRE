# 3-Minute Video Script (Tie-Break)

**Goal:** Clearly explain problem, architecture, and how to run/test, in
under 3 minutes. Read at a natural pace; pause where indicated.

---

## 0:00–0:20 — Problem understanding (≈ 20s)

> The GridWise challenge asks a public HTTP service to interpret
> free-text operator notes for a campus microgrid, convert them into
> structured directives, and return a valid 24-hour energy schedule
> that minimizes grid cost. The LLM must be in the interpretation path
> — not just for summary text — so a real language-capable model is
> mandatory.

---

## 0:20–1:00 — Architecture: LLM → Guardrails → MILP → Validator (≈ 40s)

> Our pipeline is four stages.
>
> First, the LLM — we use the official OpenAI Python SDK pointed at
> Groq (an OpenAI-API-compatible endpoint) — takes the operator notes and
> produces a structured JSON `directive_interpretation` array.
>
> Second, deterministic Python guardrails validate that JSON against
> the Problem Statement's hard rules: exactly one entry per note,
> `note_index` 0..N-1, only the six allowed directive types, the right
> `applies` semantics, hours ascending and in range, factor in [0, 1],
> reserves within capacity. If validation fails, we retry with a
> precise repair prompt — up to three times.
>
> Third, the directive compiler turns the validated directives into
> per-hour constraints: `effective_solar[h]`, `active_minimum[h]`,
> `no_charge_hours`, `no_discharge_hours`, `max_grid[h]`.
>
> Fourth, a PuLP MILP optimizer minimizes total grid cost subject to
> energy balance, battery transitions, rate caps, and end-of-day
> neutrality.
>
> Finally, an independent replay validator runs the schedule back
> through every GridWise rule before the response is returned.

---

## 1:00–1:30 — LLM interpretation and prompt design (≈ 30s)

> The system prompt spells out the contract: six allowed directive
> types with their exact `structured_adjustment` shapes, the whole-hour
> time convention, the solar factor rule, the percentage-to-kWh
> battery reserve conversion, and the `no_op` semantics for
> distractors. It includes worked examples for "80% reduction",
> "drop to 20%", "half remains", and the standard time windows.
> Hidden cases may paraphrase; the prompt is built to handle that.

---

## 1:30–1:50 — Guardrails (≈ 20s)

> Guardrails are deterministic Python — not another LLM call — so
> they're fast and reliable. Each violation raises a precise error
> message that becomes the next repair prompt. We never invent a
> directive type. We never silently mark a relevant note as `no_op`.

---

## 1:50–2:20 — MILP optimizer (≈ 30s)

> The optimizer is a mixed-integer linear program with one binary
> indicator per hour per direction to prevent simultaneous charge and
> discharge. The objective minimizes the sum of `grid_kwh[h] *
> tariff[h]`. CBC solves the 24-hour instance in well under a second
> on commodity hardware. On the 10 public reference cases our cost
> matches the reference exactly — zero percent drift on every single
> case.

---

## 2:20–2:40 — Testing (≈ 20s)

> We have unit tests for schemas, guardrails, the compiler, the
> optimizer, the plan builder, and the replay validator. End-to-end,
> `scripts/test_public_samples.py` runs all 10 public cases with a
> deterministic mock LLM and checks interpretation, validity, and cost.
> `scripts/edge_case_matrix.py` runs 24 synthetic scenarios covering
> time windows, solar wordings, reserve styles, grid caps, and
> directive combinations. `scripts/multi_agent_qa.py` runs seven QA
> agents and writes `QA_REPORT.md`.

---

## 2:40–2:55 — Deployment (≈ 15s)

> Deployment is one command: `docker compose up -d`. The Dockerfile
> uses Python 3.12 slim, a non-root user, and a built-in healthcheck.
> Environment variables are documented in `.env.example` and never
> committed.

---

## 2:55–3:00 — How to run (≈ 5s)

> `git clone`, `cp .env.example .env`, set `OPENROUTER_API_KEY`,
> `docker compose up -d`, `curl /health`. That's it.

---

## Recording tips

- Speak clearly and at a natural pace; ~150 wpm.
- Show the README, the architecture diagram, and one running public
  sample request during the demo.
- Mention the zero-percent cost drift on public samples — it's the
  strongest signal of optimization quality.
- End on the run command, not a logo or call-to-action.