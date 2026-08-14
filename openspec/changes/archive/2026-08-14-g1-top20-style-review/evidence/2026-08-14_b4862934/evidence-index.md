# 2026-08-14 `b4862934` Controlled Full-Market Run

## Scope

- Child: `g1-top20-style-review`
- G1 umbrella scope: 6.1/6.2 evidence closure
- Frozen input: 5208 SH/SZ tickers; BJ excluded by scope
- `input_ticker_set_hash`: `9d20ac29743c`
- `profile_version`: `g1-2026-07-21`
- `run_id`: `b4862934-907a-441a-9503-8fbc2c3f57e4`

## Files

| File | SHA-256 | Meaning |
| --- | --- | --- |
| `full_market_evidence.json` | `f641e81486be802bbee655be91fc248815db3912a97e4c6697e76e650714bfff` | Controlled `force_l2` full-market run. |
| `top20_derivation.json` | `89960716758022d39fec60b23eea7ad17032d8c0d4290e27eb882d3817711489` | Top 20 derived from archived `l1_candidates`; no cache/provider/LLM replay. |
| `user_review_template.json` | `2cd6ae546e90f7df18a1d1626a7af66f76a1c6d140d4bba701a01d64018ac13f` | User-completed 20-row review input with labels, confidence, and reasons. |
| `top20_gate_evidence.json` | `00061909053fc3c8d72db1d194aa380b937927d888fc50a8640fb33c9f7a24c5` | Final auditable Gate 6.1/6.2 evidence; `passed`, 20/20 worth further research. |

## Observed Run Facts

- `coverage=full_market`, `cache_warm=true`, `hard_gate_passed=true`,
  `l2_execution_passed=true`, `gate_passed=true`.
- L1 funnel: 5208 → 2545 → 300 → 250; archived `l1_candidates` count is 250.
- L2: 217 real calls, ¥0.251184 measured cost, 95 deep-dive, 154 watch,
  1 error, 32 degraded, 0 unhandled exceptions.
- `freshness_policy=allow_stale`: all 5208 `basic` slots were structurally
  valid but stale; this fact is preserved in `data_freshness` and is not
  represented as fresh.

## Product Gate Status

The run is now the fixed engineering-qualified source for the Top 20 product
review. The user completed all 20 labels, confidence values, and non-empty
逐只 reasons. No model, fixture, historical debate, or watchlist result has
been used as a user verdict.

`top20_gate_evidence.json` records `gate_verdict=passed` with
`worth_research_count=20/20` (100%), satisfying the ≥14/20 threshold for
product Gate 6.2. This closes the child evidence for G1 umbrella 6.1/6.2
only; it does not claim G1 capability passed and does not modify 7.1/7.2/7.3.
