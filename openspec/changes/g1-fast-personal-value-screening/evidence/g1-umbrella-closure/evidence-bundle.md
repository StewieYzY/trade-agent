# G1 Evidence Bundle

## Scope

- Umbrella: `g1-fast-personal-value-screening`
- Closure milestones: 7.2 and 7.3
- Evidence cutoff: 2026-08-14
- 7.3 release decision is recorded separately in `g1-release-decision.md`
- 本 bundle 不把自动化测试、fixture、历史 debate/watchlist 或模型输出当作用户 Gate 证据

## Gate Summary

| Gate | Verdict | Primary evidence | Conclusion |
| --- | --- | --- | --- |
| 1.1/1.2 数值正确性 | passed | Archived child `2026-07-21-g1-l1-numeric-dcf-correction` | DCF 量纲风险移出 G1 排序，正反向测试和全量验证已归档 |
| 2.1/2.2 分层采集边界 | passed | Archived child `2026-07-21-g1-staged-fetch-boundary` | L1 只使用 G1 量化维度，漏斗集合逐层缩小 |
| 3.1 完整输出 | passed | Archived child `2026-07-21-g1-l2-full-result-contract` | full results、verdict 分布、usage、failure summary 可追溯 |
| 3.2 运行身份 | passed | Archived child `2026-07-22-g1-canonical-run-identity` + repair | canonical ticker、run/profile/input identity 和 run-scoped 产物已闭环 |
| 4.1/4.2 规模预检 | passed | `evidence/g1-300-live-validation/2026-08-12_d32b4444.json` | 300 只沪深样本、33 个行业、字段可用率 100%、未处理异常 0；该证据明确为 partial-market 前置条件 |
| 5.1/5.2/5.3 全市场工程 Gate | passed | `archive/2026-08-12-g1-full-market-performance-cost/evidence/2026-08-12_7887d515.json` | 5208 只沪深、字段可用率 100%、未处理异常 0、完整漏斗/成本/失败分布已保存 |
| 6.1/6.2 Top 20 产品 Gate | passed | `archive/2026-08-14-g1-top20-style-review/evidence/2026-08-14_b4862934/top20_gate_evidence.json` | 固定 run/profile/input identity，20/20（100%）值得进一步研究，20 条均有用户理由 |
| 7.1 child 治理 | passed | `evidence/g1-umbrella-closure/child-governance-crosswalk.md` | 必需 child 的 Gate 引用、归档目录和历史 repair 关系可审计 |

## Capability Spec Crosswalk

| Spec requirement | Evidence check | Verdict |
| --- | --- | --- |
| 个人价值风格筛选能力边界 | Top 20 复核使用“值得进一步研究”标签，不产生自动交易或买卖指令；Top 20 evidence 保留逐只理由 | passed |
| 版本化筛选规则与运行身份 | 300-sample、full-market 和 Top 20 evidence 均保存 `run_id`、`profile_version`、`input_ticker_set_hash`；Top 20 三者绑定一致 | passed |
| 数值与量纲正确性 | numeric/DCF child 的实现、测试、归档状态已由 crosswalk 映射；DCF 不参与 G1 排序 | passed |
| G1 与 G2 分层采集边界 | staged-fetch child 明确 L1 量化维度白名单，dossier 维度不进入 G1 L1 路径 | passed |
| 完整漏斗与失败结果 | full-market evidence 保存完整 funnel、deep_dive/watch/skip/error/degraded、failure summary 和未处理异常 | passed |
| 规模、数据质量、性能与成本 Gate | 300-sample 前置证据与 full-market 工程证据分层保存；字段可用率和未处理异常满足硬 Gate，耗时/成本作为观测值保存 | passed |
| Top 20 个人风格验收 | 同一固定 run 的 20 条用户复核均合法，`worth_research_count=20/20`，达到 ≥14/20 | passed |
| Umbrella 与 child change 治理 | child crosswalk 已确认引用、独立归档和 repair 关系；本 bundle 不改写历史 archive | passed |

## Identity and Hash Checks

- 300-sample L1/L2 run：`d32b4444-5635-440b-92f9-7df24bf7f31d` /
  `g1-2026-07-21` / `57f6c50e9c7f`
- Full-market engineering run：`7887d515-157d-4d17-bcb5-fab54c7fbee3` /
  `g1-2026-07-21` / `9d20ac29743c`
- Top 20 product run：`b4862934-907a-441a-9503-8fbc2c3f57e4` /
  `g1-2026-07-21` / `9d20ac29743c`
- Top 20 derivation and review records carry the same pinned identity; the
  derivation is from the pinned bundle's ordered `l1_candidates`, not a new
  provider or LLM replay.

## Known Facts Preserved

- Full-market scope is SH/SZ 5208; BJ is explicitly excluded.
- Full-market evidence uses `freshness_policy=allow_stale`; stale basic data is
  recorded as stale and is not represented as fresh.
- The full-market run retains one isolated L2 parse error and degraded counts;
  `unhandled_exceptions=0` remains explicit.
- The 300-sample evidence is not misrepresented as full-market evidence.

## 7.2 Verdict

All G1 Gate requirements through 6.2 have a real, traceable evidence source and
no unresolved evidence gap was found in this crosswalk. Therefore 7.2 is
eligible to be marked complete.

## 7.3 Release Boundary

The separate `g1-release-decision.md` records:

- `g1_capability_status=passed`;
- `g2_formal_acceptance_status=approved_to_start_formal_acceptance`;
- `g2_capability_status=not_started`.

The release decision does not start G2 runtime or claim G2 capability passed.
