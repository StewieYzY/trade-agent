## 1. Probe plan and contracts

- [x] 1.1 Freeze at least five canonical A-share tickers, market/type labels, probe version, and read-only method matrix.
- [x] 1.2 Define provider/method/field evidence schema, status enum, unit/currency/report-period rules, and redacted error structure.
- [x] 1.3 Define run-scoped manifest, raw response hash/truncation metadata, comparison report schema, and qualification eligibility boundary.

## 2. Provider probe runner

- [x] 2.1 Implement a provider invocation boundary that records provider family, provider, method, market, ticker, and run_id without changing production fetchers.
- [x] 2.2 Implement baseline probes through the existing primary fetcher bindings for static info, quote, calc indexes, historical K-line, IS/BS/CF, and historical valuation; keep industry valuation and consensus explicitly not evaluated where no ticker-aligned contract exists.
- [x] 2.3 Implement optional LongPort/Longbridge candidate probes behind explicit availability/credential checks without adding dependencies.
- [x] 2.4 Normalize only safely verified units, currencies, as-of dates, report periods, and raw field names; mark ambiguous values non-qualified.
- [x] 2.5 Classify transport, schema, permission, rate-limit, market-support, record-not-found, invalid-value, and not-evaluated outcomes without silent defaults.

## 3. Evidence and comparison outputs

- [x] 3.1 Write run-scoped raw/evidence artifacts with code version, plan hash, provider configuration summary, response hashes, and stop reason.
- [x] 3.2 Generate field-level baseline-versus-candidate comparison reports distinguishing documentation, callable code, observed runtime, and later-integration eligibility.
- [x] 3.3 Ensure candidate probe artifacts cannot write production cache, ranking inputs, canonical snapshots, debate, watchlist, or growth diagnostic paths.

## 4. Verification and qualification Gate

- [x] 4.1 Add deterministic tests for available, partial, record-not-found, source-failed, permission-denied, rate-limited, invalid-value, and not-evaluated states.
- [x] 4.2 Add tests for ticker canonicalization, unit/report-period mismatch, redaction, response hashing, partial evidence persistence, and rate-limit stop behavior.
- [x] 4.3 Run the probe against the frozen five-ticker plan when credentials and provider access are available; preserve blocked evidence otherwise.
- [x] 4.4 Review the evidence bundle independently and produce a dated qualification decision per provider/field.
- [x] 4.5 Run focused tests, relevant provider tests, strict OpenSpec validation, compile check, and diff check; explicitly keep ranking/canonical snapshot/G1 Gate unchanged.
