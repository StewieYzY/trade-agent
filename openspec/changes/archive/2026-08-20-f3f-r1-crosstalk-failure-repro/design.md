## Context

f3c/f3e 的受控实验使用冻结 600009.SH dossier 均未复现显性/隐性串台，说明
600009 这条冻结输入不足以触发历史失败。G2 1.3 的下一步是把证据焦点移回
600519 / 600900 的历史失败快照：600519 全天团 R1 环形串台，600900 单 agent
R1 复读茅台特征（ROE 32%、毛利率 90%+、munger 看好长期价值）。

这些历史失败发生在 f1 之前的旧扁平 features 路径：`basic` 维度 2h TTL 过期，
`critical_fields=["name","market_cap"]` 缺失，guard 在旧代码中未能 fail-closed，
模型在缺少真实财务数据时回退到 system prompt 案例锚定/训练语料中的
"巴菲特-芒格-段永平-冯柳"叙事，产生环形串台。f1 已加 `financials_floor`
hard fail，f3c 已把显性环形引用接进主流程断路器；本 change 只负责冻结并复现
这条历史失败路径，定位根因，不重复实现修复。

## Goals / Non-Goals

**Goals:**

- 冻结 600519/600900 历史失败快照，绑定 ticker/run_id/source hash/payload hash。
- 用 fixture 回放历史 R1 输出，证明显性串台可被现有检测器识别。
- 用 dry-run 证明历史 `insufficient_data` 输入在当前路径下 fail-closed，不会到达 LLM。
- 产出有界结论：根因路径已定位，记录残余风险，停止串台诊断循环。

**Non-Goals:**

- 不修改主 prompt，不切换模型，不启动 G3。
- 无授权时不调用真实 LLM；fixture/dry-run 不等于 live 复现。
- 不在本 change 实施 prompt/检测器修复；如需修复另开独立 child。

## Decisions

- **D1 冻结快照自包含**：每份 fixture 包含 `freeze`（canonical ticker、run_id、
  source hash）、`input_snapshot`（历史 insufficient_data 输入）和
  `observed_r1`（文档化的历史串台输出）。
- **D2 envelope fail-closed**：ticker、source hash、fixture payload hash、run_id
  任一不一致都在任何 LLM 调用前 fail-closed，不产生 clean success。
- **D3 fixture 回放边界**：`observed_r1` 的 signal/conviction 仅为检测器占位
  （历史证据只记录 core_thesis/key_metrics），fixture 结论不能升级为 live 模型
  行为结论。
- **D4 根因边界**：根因定位为「历史 insufficient_data → prompt 案例锚定复读 →
  显性环形串台」，对应已有 f1 输入 fail-closed 与 f3c 显性串台断路器；剩余
  prompt 案例锚定设计审查与隐性串台语义检测记入残余风险，不在本 change 实施。

## Risks / Trade-offs

- [无 live 授权] → 只做 fixture/dry-run，结论是历史证据回放 + 代码路径 dry-run，
  不是新的真实 LLM 复现；不宣称 G2 capability passed。
- [fixture 的 signal/conviction 为占位] → 检测器只消费 name/core_thesis，
  占位不影响串台检测，但报告明确标注该边界。
- [检测器逃逸面] → 显性串台可识别，隐性串台（不直呼 agent_id）仍是残余风险，
  不升级为 hard gate。

## Migration Plan

1. 先写 OpenSpec spec/tasks，再写 RED 测试并确认失败。
2. 实现 fixture envelope + 最小 harness（不碰主 prompt/debate）。
3. 生成确定性 fixture 报告，跑 focused/full tests、compileall、OpenSpec strict。
4. 独立 review 后 archive；不 merge、不 push、不宣称 G2 passed。

## Open Questions

- 历史 `600519/600900` 的 live 级复现是否仍需一次真实 LLM 授权？
  本 change 按「无授权只做 fixture 和 dry-run」执行，live 复现留作残余风险。
- prompt 案例锚定设计审查是否值得单独开修复 child？
  本 change 不实施，仅在残余风险中记录，避免在无新 live 证据时继续派生串台 child。
