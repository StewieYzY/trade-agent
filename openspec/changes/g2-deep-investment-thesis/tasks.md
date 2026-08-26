# G2 Umbrella Milestones

> 本 change 是能力宪章，不应直接使用 `/opsx:apply` 作为巨型实现计划。以下每项必须由独立 child change 实现、验证和归档；checkbox 仅记录 G2 Capability Gate 的证据闭环。

## 1. Identity 与审计前置

- [x] 1.1 完成并归档 ticker/run audit-chain child change，证明 dossier、prompt、debate、quality report 和最终结果 100% 对应
- [x] 1.2 完成并归档 incomplete cache/quality status child change，阻止不完整运行伪装为成功缓存
- [x] 1.3 完成一次有界 `f3f-r1-crosstalk-failure-repro` 诊断：冻结并复现 `600519` / `600900` 历史失败快照。复现并定位根因后另开独立修复；无法复现或仍无法定位时记录历史现象与残余风险，停止串台根因循环，继续推进 2.x 数据质量 child

## 2. 事实底座

- [x] 2.1 完成并归档 dossier data-quality child change，补齐主营、同行、研报等角色专属证据
- [x] 2.2 为关键事实保存来源、报告期、发布时间、新鲜度和降级状态
- [x] 2.3 证明高严重度凭空数字为 0、关键事实追溯率 ≥95%

## 3. 成长预期资本化诊断

- [x] 3.1 完成并归档 `g2-growth-expectation-contract` child change，冻结输入/输出、用户 assumption snapshot、模型适用性、失败语义和 golden cases
- [x] 3.2 完成并归档 `g2-growth-expectation-v0-engine` child change，实现 EPV proxy、成熟期估值交叉锚、两种 reverse 求解和敏感性分析
- [x] 3.3 完成并归档 `g2-growth-expectation-dossier-integration` child change，将不可变 diagnostic artifact 接入 dossier 与 `InvestmentThesis`
- [x] 3.4 证明强单 Agent 与 Council 使用相同 diagnostic artifact/assumption snapshot，且共享确定性计算不计为 Council 独有增量

## 4. 主流程质量门

- [x] 4.1 完成并归档 main-flow quality-gates child change，将 R1 grounding、R2 revision/new evidence、DA fact-check、R4 divergence 接入正常运行
- [ ] 4.2 持久化所有 soft warning、skip reason、runtime degraded 和 failed 状态
- [ ] 4.3 证明污染或不完整结果不会被下游当作 clean success

## 5. Prompt 决策框架蒸馏

- [ ] 5.1 完成并归档 prompt-distillation child change，以决策问题、证据、判断规则、拒答条件、改变条件、正反案例和常见错误定义角色
- [ ] 5.2 证明角色差异来自分析视角而非口头禅或关键事实隔离

## 6. Baseline 与 A/B Harness

- [ ] 6.1 完成并归档 strong-single-agent baseline child change
- [ ] 6.2 完成并归档 Council A/B harness child change，固定相同模型、dossier、diagnostic artifact、工具权限、预算口径和匿名评分 rubric
- [ ] 6.3 冻结 8-10 只多类型股票样本和评价规则，其中至少覆盖高估值成长股与 diagnostic `not_evaluable` 场景

## 7. 能力实跑

- [ ] 7.1 对全部固定样本执行单 Agent 与 Council 双路径运行
- [ ] 7.2 证明 ticker/run/prompt/dossier/diagnostic/debate/result 审计对齐率 100%，显性与隐性串台为 0
- [ ] 7.3 完成用户盲评并计算：Council 实质增量 ≥70%、Council 更好 ≥60%、Council 更差 ≤20%
- [ ] 7.4 若 Gate 失败，记录回退决定并将默认形态设为强单 Agent + 独立 DA/事实检查器 + Synthesizer

## 8. 稳定输出接口

- [ ] 8.1 完成并归档 InvestmentThesis interface child change
- [ ] 8.2 证明 valuation_expectation、evidence、counter_evidence、assumptions、risks、key_variables、改变条件、分歧、待验证项和质量状态可被下游稳定消费

## 9. Umbrella Closure

- [ ] 9.1 确认所有必要 child changes 均引用本 umbrella 且已独立归档
- [ ] 9.2 汇总 G2 evidence bundle，逐项对照 capability spec 确认无缺口
- [ ] 9.3 仅在真实 Gate 全部通过后标记 G2 capability passed，并记录 G3 runtime 放行决定
