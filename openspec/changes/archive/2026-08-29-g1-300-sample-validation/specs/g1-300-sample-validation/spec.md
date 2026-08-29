## ADDED Requirements

### Requirement: Injectable deterministic sample selection

The validation sample selector SHALL accept spot-shaped records and an industry mapping through explicit function inputs, and MUST NOT call AkShare, Eastmoney, another provider, or an LLM. The selector SHALL normalize records before sampling and SHALL produce the same ticker set and metadata for the same normalized inputs, seed, and configuration regardless of input row order.

#### Scenario: Same input produces the same sample

- **WHEN** the selector receives the same records and industry mapping in two different row orders with the same seed
- **THEN** it SHALL return the same sorted canonical ticker list, strata labels, and design summary

#### Scenario: External calls are not part of selection

- **WHEN** the selector runs with in-memory fixture records
- **THEN** it MUST complete without importing or invoking provider/LLM code

### Requirement: Industry and risk strata coverage

The selector SHALL support explicit industry strata and the risk strata `st:h1`, `smallcap:h3`, `negative_pe:h8`, and `overheat:60d`. It SHALL apply configured industry quota/cap and risk-layer caps, merge overlapping strata labels, and deduplicate by canonical ticker. An unmapped industry SHALL be represented explicitly as `_unmapped` and MUST NOT count as a real industry for coverage.

#### Scenario: Risk labels are retained

- **WHEN** a record is ST, below the small-cap threshold, has negative PE, or belongs to the configured overheat pool
- **THEN** the selected record SHALL retain the corresponding risk strata label in addition to any industry label

#### Scenario: Overlapping pools do not duplicate tickers

- **WHEN** one ticker qualifies for multiple industry or risk pools
- **THEN** it SHALL occur once in the output sample with the union of its applicable strata labels

#### Scenario: Unmapped industry is visible

- **WHEN** a record has no usable industry mapping
- **THEN** the output SHALL label it `_unmapped`, the design summary SHALL expose its count/status, and the record SHALL NOT increase real industry coverage

### Requirement: Explicit value and source status semantics

The fixture input and output SHALL preserve `complete`, `degraded`, `source_failed`, `record_not_found`, and `invalid_value`/missing-value semantics using the canonical status/provenance shape. Missing or invalid values MUST NOT be silently replaced with ranking-affecting defaults. A status that prevents a strata predicate from being evaluated SHALL be reported in per-stratum unavailable counts and reasons.

#### Scenario: Complete record is eligible

- **WHEN** a record has valid ticker, industry/value fields, and complete provenance
- **THEN** it MAY participate in applicable industry and risk strata and SHALL be marked complete

#### Scenario: Degraded record remains visibly degraded

- **WHEN** a record has enough valid fields for a subset of strata but one optional field is missing or degraded
- **THEN** it MAY be selected for evaluable strata, but its output metadata SHALL retain degraded status and the affected field/reason

#### Scenario: Source failure is not record absence

- **WHEN** the industry mapping or a required selection input is marked source_failed
- **THEN** the selector SHALL preserve source_failed and attempted-source provenance, and MUST NOT reinterpret it as record_not_found or successful unmapped coverage

#### Scenario: Record not found is explicit

- **WHEN** a source completed successfully but has no mapping/value record for a ticker
- **THEN** the output SHALL preserve record_not_found and MUST NOT convert it to source_failed or a fabricated value

#### Scenario: Invalid or missing value is not defaulted

- **WHEN** a numeric selection value is missing or cannot be parsed/validated
- **THEN** the corresponding predicate SHALL be not evaluable, the reason SHALL be visible in summary metadata, and the selector MUST NOT substitute zero, a market average, or another implicit default

### Requirement: Full-market semantic threshold

The sample design SHALL expose the actual selected sample size and `full_market_qualified_size`. `full_market_qualified_size` SHALL count only unique selected canonical tickers with a usable mapped industry and a usable record status; `_unmapped`, `source_failed`, `record_not_found`, and invalid records MUST NOT contribute to that count. The selector SHALL reject a configured full-market threshold below 300 and SHALL set `full_market_eligible` to true only when `full_market_qualified_size` is at least the configured threshold. When fewer than 300 qualified records are available, the output SHALL use an explicit insufficient/development semantic and MUST NOT claim a full-market sample or successful G1 precheck.

#### Scenario: Three hundred unique tickers unlock full-market semantics

- **WHEN** the selector returns at least 300 unique valid canonical tickers
- **THEN** the design summary SHALL report `sample_size >= 300` and `full_market_eligible=true`

#### Scenario: Fewer than three hundred remains insufficient

- **WHEN** the selector can select fewer than 300 unique valid canonical tickers
- **THEN** the design summary SHALL report the actual count, `full_market_eligible=false`, and an explicit insufficient/development status

#### Scenario: Unusable records do not unlock full-market semantics

- **WHEN** the selector has 300 selected records but some selected records are `source_failed`, `record_not_found`, `invalid_value`, or otherwise unusable
- **THEN** `full_market_qualified_size` SHALL exclude those records and `full_market_eligible` SHALL remain false when fewer than 300 usable records remain

#### Scenario: Threshold cannot be reduced below three hundred

- **WHEN** a caller configures a full-market threshold below 300
- **THEN** the selector SHALL reject the configuration with a clear validation error

#### Scenario: Missing strata do not unlock the threshold

- **WHEN** the selector reaches 300 only through duplicated, invalid, unmapped, or otherwise ineligible records
- **THEN** it MUST count only unique valid tickers and MUST leave `full_market_eligible=false` if fewer than 300 qualify

### Requirement: Identity, provenance, and fixture isolation

Every selector output SHALL carry canonical ticker identity, `run_id`, `profile_version`, deterministic `input_ticker_set_hash`, `as_of`, schema version, and caller-supplied fixture provenance. The selector SHALL validate that a caller-supplied input hash matches the canonical ticker set and SHALL reject provenance that is marked as live evidence. The envelope SHALL explicitly identify the artifact as `fixture/reference` or `simulated/development`. Fixture outputs MUST remain isolated from provider qualification, canonical promotion, live evidence bundles, production cache, watchlist, and debate artifacts.

#### Scenario: Identity fields are present and internally consistent

- **WHEN** a fixture sample is generated
- **THEN** every ticker SHALL be canonicalized, the input hash SHALL be reproducible from the canonical ticker set, and the envelope SHALL include run/profile/as-of/provenance fields

#### Scenario: Fixture provenance is explicit

- **WHEN** the input source is an in-memory or checked-in development fixture
- **THEN** the output SHALL identify `fixture/reference` or `simulated/development` and SHALL state that it is not live provider evidence

#### Scenario: Fixture cannot be promoted by this child

- **WHEN** a fixture selector run completes
- **THEN** it SHALL produce only development contract output and MUST NOT write or mark provider qualification, canonical promotion, G1 evidence bundle, or G1 passed artifacts
