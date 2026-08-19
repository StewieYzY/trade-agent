## MODIFIED Requirements

### Requirement: L3→L4 接口文件结构
系统 SHALL 产出 `watchlist/{canonical_ticker}/{run_id}/{date}.json`，每个 council
子命令跑完单股即写
（不引入批跑聚合）。除既有字段外，新写入的接口文件 SHALL 包含
`run_quality_status`、`run_quality_reasons`、`final_quality_gate`、
`success_cache_eligible` 与 `quality_record_path`。

`success_cache_eligible` 只有在 `run_quality_status="complete"` 且
`final_quality_gate="passed"` 时才 SHALL 为 true。接口文件中存在
`final_verdict`、`conviction` 或 `debate_path` MUST NOT 单独表示 clean success。

#### Scenario: Complete 接口文件
- **WHEN** Council run 的 quality record 为 complete 且 final quality gate passed
- **THEN** 接口文件 SHALL 写入 `success_cache_eligible=true` 和 quality record reference

#### Scenario: 降级或中断接口文件
- **WHEN** Council run 为 warning、failed、incomplete、runtime_degraded 或 da_skipped
- **THEN** 接口文件 SHALL 明确写入对应 status/reasons，且 `success_cache_eligible=false`

#### Scenario: Run-scoped 输出被 L4 读取
- **WHEN** Council 输出写在 `watchlist/{canonical_ticker}/{run_id}/{date}.json`
- **THEN** L4 聚合 SHALL 选择该 run-scoped 文件并透传 status、reasons、quality gate、
  cache eligibility 与 quality record reference；非 complete 结果 SHALL 标记为
  `l3_incomplete=true`

#### Scenario: 接口文件与 L1/L2 watchlist 独立
- **WHEN** L3 产出 `watchlist/{canonical_ticker}/{run_id}/{date}.json`
- **THEN** SHALL NOT 覆盖或修改 `watchlist/{date}_screener.json`（L1/L2 产出），两个文件独立存在
