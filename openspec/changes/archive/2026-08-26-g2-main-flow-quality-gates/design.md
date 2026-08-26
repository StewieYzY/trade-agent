## Context

当前 `council/debate.py` 已负责 R1、R2、DA、R4 的串行编排，也已有 `verify_quality_gate.py` 中的 R1 grounding、R2 new evidence、DA fact-check、R4 divergence 校验函数，以及 `quality_status.py` 的 closed status vocabulary。问题在于这些契约并未完整地作为正常运行链路的终态 gate：部分函数只被验证脚本调用，部分 warning/skip/degraded 信息只停留在局部变量，且最终结果可能在质量证据不完整时仍被当作 clean success。

本 change 只处理 G2 4.1 的 engineering closure。它必须兼容现有 `AGENT_REGISTRY`、`AgentOutput`、`SynthesizerOutput`、`CouncilResult` 和 run-scoped quality record 设计，并尊重 `council-debate` 中的 low/extreme、evidence_exhausted、runtime_degraded 分流。

## Goals / Non-Goals

**Goals:**

- 在正常 `run_debate` 链路中按阶段执行 R1 grounding、R2 evidence、DA fact-check、R4 divergence gate。
- 明确 hard failure、soft warning、合法 skip、runtime degradation 与 interruption 的状态传播。
- 确保任意污染结果、非法结构、缺失阶段或 gate 未通过结果不能写成 `complete` 或进入 success cache。
- 保持外部调用边界不变，并用 mock 检查 `call_agent`、DA、Synthesizer 的参数形状。
- 以最小 diff 完成可回归的行为测试和 strict validation。

**Non-Goals:**

- 不实现 G2 4.2 的完整状态持久化、恢复协议或新的数据库/存储层。
- 不实现 G2 4.3 的独立下游证明、A/B、盲评或 capability gate。
- 不修改 growth expectation engine、G1 ranking/hard gate、主 prompt 或启动 G3。
- 不调用真实 LLM/provider，不增加依赖，不重构无关模块。

## Decisions

1. **复用现有 gate 函数，编排器作为唯一调用方。**
   `run_debate` 在 R1、R2、DA、R4 各阶段成功后调用现有可导入校验函数，避免复制规则。替代方案是新建第二套 validator，但会产生词汇和边界漂移；不采用。

2. **hard/soft/skip 采用显式聚合，不以 truthiness 推断成功。**
   R1 环形引用、DA 运行时输出缺失、R4 分歧报告非法属于 hard failure；R1 grounding、R2 新证据缺失/疑似伪造、DA 因 evidence_exhausted/runtime_degraded 跳过属于 warning；low/extreme 的 DA skip 是合法 skip，但仍使终态不可 cache。聚合器只在所有必需阶段完成且无 hard issue、无 warning/skip/degraded 时写 `complete/passed`。

3. **终态状态优先由实际执行证据决定。**
   `runtime_degraded`、`da_skipped`、`warning`、`failed`、`incomplete` 均保留 reasons 和 completed stages；任何方向性 verdict、debate markdown 或 watchlist 文件都不能覆盖这些状态。这样沿用 `g2-run-quality-status` 的 fail-closed cache eligibility。

4. **R4 使用已计算的分歧信息作为校验上下文。**
   Synthesizer 输出必须携带结构化 `divergence_level`；若 low/extreme 等分流导致 DA/R2 跳过，仍要求 R4 通过分歧报告校验。对 extreme 不伪造共识，保留 neutral + key disagreements 的既有语义。

5. **测试优先覆盖主流程行为与调用契约。**
   先写能在当前实现上失败的端到端编排测试，再做最小实现。LLM mock 使用带显式参数断言的 async callable，验证 ticker、features/dossier、other_opinions、reasoning level、stage、model 等参数形状，避免只断言调用次数。

## Risks / Trade-offs

- [Risk] 既有历史 fixture 或旧 markdown 缺少新质量字段 → 读取时继续按 degraded/unknown 处理，不能升级为 clean；测试明确覆盖 legacy 不命中 cache。
- [Risk] R1 grounding 的数字匹配存在容差和嵌套 dossier 误报 → 保留其 soft warning 语义，不把该检查扩大成未经验证的 hard gate。
- [Risk] DA 合法 skip 会降低信息量 → 持久化具体 skip reason，并让 R4 分歧报告承担可见性；skip 结果不进入成功缓存。
- [Risk] 某阶段异常可能留下部分 markdown → 先写 incomplete quality record，异常向上抛出，后续 cache lookup 依据 record 拒绝。
- [Risk] 修改编排器容易引入单 agent/机制门回归 → 保留现有单 agent 分支，只对 Council 正常链路增加检查，并运行 focused 与 full tests。
