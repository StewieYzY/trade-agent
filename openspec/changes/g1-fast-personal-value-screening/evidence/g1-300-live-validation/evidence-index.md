# G1 300-Sample Live Validation Evidence Index

本索引固化 G1 umbrella 4.1/4.2 使用的真实 300 只分层样本证据。
原始运行文件位于被 `.gitignore` 排除的
`value-screener/data/evidence/g1-300-live-validation/`；可复核副本保存在本目录。

## Identity

- Sample run ID: `g1-300-live-20260812T100142Z`
- L1/L2 run ID: `d32b4444-5635-440b-92f9-7df24bf7f31d`
- ScreeningProfile: `g1-2026-07-21`
- Canonical input ticker set hash: `57f6c50e9c7f`
- Market scope: SH/SZ only; BJ excluded
- Canonical ticker count: 300

样本、固定 universe 和 L1/L2 输入经 canonical ticker 归一后集合完全一致，
均为 300 个唯一 ticker，重算的 `input_ticker_set_hash` 均为
`57f6c50e9c7f`。

## Archived Artifacts

### Live Provider Sample

- Archive:
  `g1-300-live-20260812T100142Z.json`
- Original:
  `value-screener/data/evidence/g1-300-live-validation/g1-300-live-20260812T100142Z.json`
- SHA-256:
  `afb205245ea570f68af61c0c26dd22997d8a28f5979bd1d59e766fa99c159d90`
- Internal sample SHA-256:
  `049f12b1b8c4c6c157d2c778151b6225f4b6901e4cd2d0491ee6aceb85574edb`
- Result: 300 SH/SZ stocks across 33 industries
- Risk coverage:
  - `risk:st_h1`: 22
  - `risk:smallcap_h3`: 91
  - `risk:negative_pe_h8`: 93
  - `risk:overheat_60d`: 32

### Frozen Universe

- Archive:
  `validation_sample_300.universe.json`
- Original:
  `value-screener/data/evidence/g1-300-live-validation/validation_sample_300.universe.json`
- SHA-256:
  `cfc77af393976e7f11bf1d2a2b000e4189c06d3535c1fcefb5da5f61ce90cb48`
- Result: 300 unique input tickers

### L1/L2 Validation Run

- Archive:
  `2026-08-12_d32b4444.json`
- Original:
  `value-screener/data/evidence/g1-300-live-validation/l1-l2/2026-08-12_d32b4444.json`
- SHA-256:
  `b75b642077879449f930c6a9fb63a5f06758b548c8ef284a5defe9914dc9a85a`
- Field availability: 100%
- Unhandled exceptions: 0
- Verdict distribution:
  - `deep_dive`: 24
  - `watch`: 97
  - `skip`: 14
  - `error`: 1
  - `degraded`: 15
- Failure isolation: `600008.SH` produced one `stage=parse` L2 error;
  the remaining batch completed and the error remained visible.

## Scope

These artifacts close only G1 umbrella milestones 4.1 and 4.2. They do not
complete the Top 20 product review, the umbrella closure, or the G1 Capability
Gate. The L1/L2 evidence correctly retains `coverage=partial_market` because
the frozen validation input contains 300 stocks rather than the full market.
