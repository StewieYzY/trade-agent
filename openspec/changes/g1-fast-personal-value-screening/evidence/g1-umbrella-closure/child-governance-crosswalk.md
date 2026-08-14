# G1 必需 Child 治理 Crosswalk

## Purpose

本文件为 G1 umbrella milestone 7.1 提供可审计的治理映射。它不修改
任何已归档 child 的历史 proposal/tasks；历史文档使用的 `G1 umbrella`
或 milestone/Gate 语义引用，均映射到本 umbrella
`g1-fast-personal-value-screening` 的 1–6 项。

同名的未跟踪 `openspec/changes/g1-300-sample-validation/` 属用户 WIP，
不参与本 crosswalk；本文件只引用已归档、已跟踪的证据。

## Required Children

| Umbrella milestones | Archived child | Historical umbrella/Gate reference | Archive completion evidence |
| --- | --- | --- | --- |
| 1.1/1.2 | `2026-07-21-g1-l1-numeric-dcf-correction` | `proposal.md` 的 `G1 umbrella D4`；`tasks.md` 5.3 明确推进 1.1/1.2 | Archive directory; child tasks complete |
| 2.1/2.2 | `2026-07-21-g1-staged-fetch-boundary` | `proposal.md` 明确推进 G1 umbrella tasks 2.1/2.2 | Archive directory; child tasks complete |
| 3.1 | `2026-07-21-g1-l2-full-result-contract` | `proposal.md` 明确推进 G1 umbrella task 3.1 | Archive directory; child tasks complete |
| 3.2 | `2026-07-22-g1-canonical-run-identity` | `proposal.md` 明确推进 G1 umbrella 3.2 | Archive commit `71b4df8`; `tasks.md` 14.3 未勾选但该提交已实际完成归档；14.4 是由用户决定是否生成的 handoff，不是运行时 Gate |
| 3.2 repair | `2026-07-22-g1-canonical-run-identity-repair` | `proposal.md` 明确说明修复已归档的 G1-3，且不重开其设计 | Archive commit `5e86d32`; 唯一未勾选 8.4 是用户决定是否生成 handoff，不是运行时 Gate |
| 4.1/4.2 | `2026-08-07-g1-300-sample-validation` | `proposal.md` 引用本 umbrella 并限定 4.1/4.2 | Archive directory and `g1-300-live-validation/evidence-index.md` |
| 5.1/5.2/5.3 | `2026-08-12-g1-full-market-performance-cost` | `proposal.md` 引用本 umbrella 并限定全市场工程 Gate | Archive directory and `evidence-index.md` |
| 6.1/6.2 | `2026-08-14-g1-top20-style-review` | `proposal.md` 引用本 umbrella 并限定 6.1/6.2 | Archive directory and `evidence/2026-08-14_b4862934/evidence-index.md` |

## Verdict

所有实现 G1 milestones 1–6 所必需的 child 均有可追溯的 umbrella/Gate
引用并已独立归档。历史 tasks 中保留的两项 handoff/归档行政勾选不构成
未完成运行时 Gate，且不应通过改写 archive 历史来“补绿”。

因此 umbrella milestone 7.1 通过。该结论不替代 7.2 的最终 evidence
bundle 对照，也不表示 G1 capability passed。
