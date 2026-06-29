## 1. Scout Prompt & Input Assembly

- [x] 1.1 Create `scout/__init__.py` module structure
- [x] 1.2 Implement `scout/prompt.py` with `SCOUT_SYSTEM_PROMPT` constant (5 questions + JSON schema from design.md §2)
- [x] 1.3 Implement `scout/prompt.py` `format_snapshot(features: dict) -> str` function to format ~200-token user message (design.md §2 User Message template)
- [x] 1.4 Implement `scout/input_assembly.py` `assemble_snapshot(ticker: str) -> dict` function to fetch all dimensions from CacheManager and return structured features; reuse `data/lib/fin_models.py` for derived metrics (ROE/net margin/debt ratio/goodwill ratio) to maintain consistency with L1
- [x] 1.5 Add missing data handling in `assemble_snapshot`: use `None` placeholders and annotate "数据缺失" for missing fields
- [x] 1.6 Add trend annotation helpers in `input_assembly.py`: `annotate_roe_trend(roe_3y)`, `annotate_cashflow_match(operating_cashflow, net_profit)`, `annotate_revenue_growth(revenue_series)`
- [x] 1.7 Add insufficient data guard in `assemble_snapshot`: if critical fields (name/industry/market_cap) are missing OR more than 50% of required fields are missing, return `{"error": "insufficient_data", "missing_fields": [...]}` to skip LLM call

## 2. Output Parsing & Buffer Zone

- [x] 2.1 Implement `scout/parse.py` `parse_scout_output(raw_json: str) -> dict` function to validate and parse LLM JSON response (verdict/confidence/one_liner/flags)
- [x] 2.2 Implement `scout/parse.py` `apply_buffer_zone(verdict: str, confidence: int) -> tuple[str, bool]` function: confidence ≥ 60 → trust verdict; 40-60 → force "watch"; < 40 → force "watch" + flag anomaly
- [x] 2.3 Add JSON parsing error handling in `parse_scout_output`: return `{"verdict": "watch", "confidence": 0, "parse_error": True}` on malformed JSON
- [x] 2.4 Add field validation in `parse_scout_output`: check verdict ∈ {deep_dive, watch, skip}, confidence ∈ [0, 100], flags are lists of strings

## 3. LLM Client & Batch Processing

- [x] 3.1 Implement `scout/batch.py` `call_llm_snapshot(snapshot: str, system_prompt: str) -> str` async function: POST to `{LLM_API_BASE}/v1/chat/completions` with `temperature=0.0`, `response_format={"type": "json_object"}`, 60s timeout
- [x] 3.2 Add environment variable validation in `call_llm_snapshot`: read `LLM_API_KEY`, `LLM_API_BASE`, `LLM_MODEL` (all required, no defaults), raise `ValueError` if any is missing (fail-fast)
- [x] 3.3 Implement retry logic in `call_llm_snapshot`: catch `httpx.HTTPStatusError` and `httpx.TimeoutException`, retry once after 2s backoff
- [x] 3.4 Implement `scout/batch.py` `scout_batch(candidates: list[dict]) -> list[dict]` async function: process all candidates concurrently with `asyncio.Semaphore(20)`
- [x] 3.5 Add per-candidate error handling in `scout_batch`: catch exceptions, return `{"ticker": ticker, "verdict": "error", "error": str(e)}` for failed calls (don't block batch)
- [x] 3.6 Add insufficient data handling in `scout_batch`: skip LLM call for candidates with `error: "insufficient_data"` from `assemble_snapshot`
- [x] 3.7 Filter output in `scout_batch`: return only candidates with `verdict == "deep_dive"`, sorted by confidence descending, capped at top 20 (AD-03 cost gate 200→20)

## 4. Quality Assurance & Caching

- [x] 4.1 Implement `scout/quality.py` `ScoutCache` class with `get(ticker: str, date: str) -> Optional[dict]` and `set(ticker: str, date: str, result: dict, input_snapshot: dict) -> None` methods
- [x] 4.2 Set TTL=24h (86400 seconds) in `ScoutCache.get`: check file mtime, return `None` if older than 24h
- [x] 4.3 Structure cache entry in `ScoutCache.set`: write JSON with `verdict`, `confidence`, `one_liner`, `red_flags`, `green_flags`, `anti_trap_flags`, `input_snapshot` (dict), `timestamp` (ISO format) to `data/cache/{ticker}/{date}/l2_scout.json`
- [x] 4.4 Integrate cache check in `scout_batch`: before calling LLM, check `ScoutCache.get(ticker, date.today().isoformat())`, reuse if valid
- [x] 4.5 Write cache after LLM call in `scout_batch`: call `ScoutCache.set(ticker, date.today().isoformat(), result, input_snapshot)` for each newly processed candidate

## 5. CLI Integration

- [x] 5.1 Add `scout` subcommand to `cli.py` using `typer` with options: `--input` (L1 output JSON path), `--output` (L2 shortlist JSON path), `--force` (bypass cache)
- [x] 5.2 Implement L1 output loading in `scout` command: read JSON from `--input` path, extract `candidates` list (S5 schema)
- [x] 5.3 Implement snapshot assembly loop in `scout` command: for each candidate, call `assemble_snapshot(candidate["ticker"])` and `format_snapshot(features)`
- [x] 5.4 Implement batch LLM call in `scout` command: call `asyncio.run(scout_batch(candidates_with_snapshots))`
- [x] 5.5 Implement output writing in `scout` command: write filtered deep_dive candidates (top-20 cap) to `--output` path (or stdout if not specified)
- [x] 5.6 Add error handling in `scout` command: if `--input` file not found, raise `typer.BadParameter` with clear message

## 6. Testing & Validation

- [x] 6.1 Create `tests/test_scout_prompt.py`: test `format_snapshot` with sample features dict, verify output matches design.md §2 template
- [x] 6.2 Create `tests/test_scout_input_assembly.py`: test `assemble_snapshot` with mocked CacheManager, verify all dimensions fetched and missing data handled
- [x] 6.3 Add contract test in `test_scout_input_assembly.py`: verify `pe_ttm` fetched from `valuation` dim (not `basic`), ROE uses 3-year window (not 5), `dividend_yield` not in snapshot, `receivables_growth` not in snapshot
- [x] 6.4 Add insufficient data test in `test_scout_input_assembly.py`: verify guard triggers when critical fields (name/industry/market_cap) missing and when >50% fields missing
- [x] 6.5 Create `tests/test_scout_parse.py`: test `parse_scout_output` with valid JSON, malformed JSON, and invalid field values
- [x] 6.6 Create `tests/test_scout_parse.py`: test `apply_buffer_zone` with confidence 75 (trust), 55 (buffer zone), 30 (low confidence)
- [x] 6.7 Create `tests/test_scout_batch.py`: test `scout_batch` with mocked `call_llm_snapshot`, verify concurrency (20 concurrent), retry logic (1 retry after 2s), error handling, and top-20 cap
- [x] 6.8 Add top-20 cap test in `test_scout_batch.py`: verify that when 40 candidates have `verdict == "deep_dive"`, only top 20 by confidence are returned
- [x] 6.9 Create `tests/test_scout_quality.py`: test `ScoutCache` get/set with mocked filesystem, verify TTL=24h, cache structure (input_snapshot included), and `{date}` subdirectory isolation
- [x] 6.10 Add cross-day test in `test_scout_quality.py`: verify cache from 2026-06-29 is not overwritten when running on 2026-06-30
- [x] 6.11 Add cache cold test in `test_scout_batch.py`: verify behavior when all cache entries expired (full LLM call batch)
- [x] 6.12 Create `tests/test_cli_scout.py`: test `scout` subcommand with mocked L1 output and mocked `scout_batch`, verify end-to-end flow

## 7. Documentation

- [x] 7.1 Add docstring to `scout/prompt.py` explaining Scout prompt design (reference design.md §2 and total-design §5.2)
- [x] 7.2 Add docstring to `scout/input_assembly.py` explaining L1→L2 data handoff (reference design.md §1 Decision 1), field sources (pe_ttm from valuation), and fin_models reuse
- [x] 7.3 Add docstring to `scout/batch.py` explaining concurrent LLM calling strategy (reference design.md §4), top-20 cap (AD-03), and retry logic (1 retry after 2s)
- [x] 7.4 Add docstring to `scout/parse.py` explaining buffer zone logic (reference design.md §3.2 and total-design §5.6)
- [x] 7.5 Add docstring to `scout/quality.py` explaining 24h cache with input snapshot and `{date}` subdirectory (reference design.md §3.3)
- [x] 7.6 Update `cli.py` help text for `scout` subcommand: explain usage, environment variables (LLM_API_KEY/BASE/MODEL, all required), and cost (~¥0.01/stock, top-20 cap)

## 8. Deployment & Configuration

- [x] 8.1 Add example environment variables to `README.md`: `LLM_API_KEY`, `LLM_API_BASE`, `LLM_MODEL` (all required) with explanation
- [x] 8.2 Add scout usage example to `README.md`: `python cli.py scout --input l1_output.json --output l2_shortlist.json`
- [x] 8.3 Add cost estimation note to `README.md`: ~¥2/run for 200 stocks with 80% cache hit rate, top-20 cap ensures L3 cost stays within AD-03 budget
