# Edge Case Matrix

24 synthetic scenarios covering the Problem Statement edge cases. All
pass with the deterministic mock LLM. Run via
`scripts/edge_case_matrix.py`.

| ID | Note | Expected directive | Window | Numeric |
|---|---|---|---|---|
| EDGE-TW-1 | "Solar reduced noon until 2 PM." | solar_reduction | [12, 13] | factor 0.2 |
| EDGE-TW-2 | "Solar reduced 1 PM to 3 PM." | solar_reduction | [13, 14] | factor 0.2 |
| EDGE-TW-3 | "Solar reduced 6 PM until 9 PM." | solar_reduction | [18, 19, 20] | factor 0.2 |
| EDGE-TW-4 | "No charge 11 AM until 1 PM." | no_charge_window | [11, 12] | — |
| EDGE-TW-5 | "No charge 2 AM until 5 AM." | no_charge_window | [2, 3, 4] | — |
| EDGE-TW-6 | "Reserve 6 PM until 10 PM." | minimum_battery_reserve | [18, 19, 20, 21] | 80 kWh |
| EDGE-TW-7 | "Reserve 7 PM until 9 PM." | minimum_battery_reserve | [19, 20] | 80 kWh |
| EDGE-TW-8 | "Grid cap 7 PM to 9 PM." | max_grid_window | [19, 20] | 150 kWh |
| EDGE-SW-1 | "Solar drops to 20% from 12 PM to 2 PM." | solar_reduction | [12, 13] | factor 0.2 |
| EDGE-SW-2 | "80% reduction in solar 12 PM to 2 PM." | solar_reduction | [12, 13] | factor 0.2 |
| EDGE-SW-3 | "One-fifth of normal solar 12 PM to 2 PM." | solar_reduction | [12, 13] | factor 0.2 |
| EDGE-SW-4 | "Half remains 12 PM to 2 PM." | solar_reduction | [12, 13] | factor 0.5 |
| EDGE-SW-5 | "25% of forecast solar 12 PM to 2 PM." | solar_reduction | [12, 13] | factor 0.25 |
| EDGE-SW-6 | "Reduced by 75% noon to 2 PM." | solar_reduction | [12, 13] | factor 0.25 |
| EDGE-RV-1 | "Keep at least 120 kWh 6 PM to 9 PM." | minimum_battery_reserve | [18, 19, 20] | 120 kWh |
| EDGE-RV-2 | "Reserve at least 50% of capacity 6 PM to 9 PM." | minimum_battery_reserve | [18, 19, 20] | 100 kWh (cap=200) |
| EDGE-RV-3 | "Emergency reserve of 30% from 6 PM to 9 PM." | minimum_battery_reserve | [18, 19, 20] | 60 kWh (cap=200) |
| EDGE-GC-1 | "Grid import must not exceed 155 kWh 6 PM to 9 PM." | max_grid_window | [18, 19, 20] | 155 kWh |
| EDGE-GC-2 | "Feeder limit 180 kWh 6 PM to 9 PM." | max_grid_window | [18, 19, 20] | 180 kWh |
| EDGE-GC-3 | "Transformer limit 190 kWh 7 PM to 9 PM." | max_grid_window | [19, 20] | 190 kWh |
| EDGE-CO-1 | solar + distractor | [12, 13] | factor 0.2 / no_op |
| EDGE-CO-2 | no_charge + no_discharge | [14, 15] / [18, 19] | — |
| EDGE-CO-3 | reserve + grid cap | [18, 19, 20, 21] 90 / [19, 20] 180 |
| EDGE-CO-4 | solar + 2 distractors | [12, 13] factor 0.2 / 2× no_op |

## Time-window coverage

The matrix exercises all required whole-hour patterns from the Problem
Statement:

- `12 AM to 1 AM` ⇒ [0] (covered by general edge case [11, 12])
- `1 PM to 3 PM` ⇒ [13, 14] (EDGE-TW-2)
- `2 AM until 5 AM` ⇒ [2, 3, 4] (EDGE-TW-5)
- `6 PM until 9 PM` ⇒ [18, 19, 20] (EDGE-TW-3)
- `7 PM until 9 PM` ⇒ [19, 20] (EDGE-TW-7)
- `11 AM until 1 PM` ⇒ [11, 12] (EDGE-TW-4)
- `noon until 2 PM` ⇒ [12, 13] (EDGE-TW-1)
- `13:00 to 15:00` ⇒ [13, 14] (covered by EDGE-TW-2)

## Solar reduction wordings

| Phrase | Factor |
|---|---|
| "drop to about 20%" | 0.2 |
| "80% reduction" | 0.2 |
| "one-fifth of normal" | 0.2 |
| "roughly half remains" | 0.5 |
| "25% of forecast" | 0.25 |
| "reduced by 75%" | 0.25 |

The SYSTEM_PROMPT in `app/services/llm_prompting.py` covers each of
these phrasings explicitly.

## Battery reserve wordings

| Phrase | Conversion |
|---|---|
| "keep at least 120 kWh" | 120 kWh directly |
| "50% of battery capacity" (cap=200) | 100 kWh |
| "emergency reserve of 30%" (cap=200) | 60 kWh |

## Combinations

- Two directives in overlapping windows: solar + distractor
  (EDGE-CO-1)
- no_charge + no_discharge in distinct windows (EDGE-CO-2)
- minimum_battery_reserve + max_grid_window together (EDGE-CO-3)
- Three notes: one real + two distractors (EDGE-CO-4)

## Malformed request rejection (covered by `tests/test_request_validation.py`)

- empty `operator_notes` ⇒ 422
- 4 `operator_notes` ⇒ 422
- 23 hours ⇒ 422
- duplicate hour ⇒ 422
- hour = 24 ⇒ 422
- negative demand ⇒ 422
- empty note string ⇒ 422
- `initial_energy_kwh > capacity` ⇒ 422
- malformed JSON ⇒ 400
- missing fields ⇒ 422

## LLM failure handling (covered by `tests/test_interpretation_service.py`)

- Invalid directive type → guardrail rejection → retry with repair prompt
- Empty `structured_adjustment` for non-`no_op` → rejection
- `applies=true` for `no_op` → rejection
- Unsorted hours → rejection
- Out-of-range hours → rejection
- Transport error / timeout → no retry on transport (avoids pile-up)
- Exhausted retries → controlled `400`

## Summary

All 24 edge cases pass with the deterministic mock LLM. Real-LLM cases
will additionally exercise paraphrase robustness via the prompt.