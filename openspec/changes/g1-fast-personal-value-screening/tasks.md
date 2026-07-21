# G1 Umbrella Milestones

> 本 change 是能力宪章，不应直接使用 `/opsx:apply` 作为巨型实现计划。以下每项必须通过独立 child change 实现、验证和归档；checkbox 仅记录 G1 Capability Gate 的证据闭环。

## 1. 排序正确性

- [ ] 1.1 建立并归档 L1 数值口径与 DCF 纠偏 child change，证明所有排序关键指标单位、分母和报告期正确
- [ ] 1.2 明确简化 DCF 是移出 G1 排序还是完成可靠修复，并保存正反向数值测试证据

## 2. 分层采集边界

- [ ] 2.1 建立并归档 G1/G2 fetcher boundary child change，证明全市场路径不采集 dossier 维度
- [ ] 2.2 用采集调用计数或等价证据证明 ticker 集合随漏斗逐层缩小

## 3. 完整输出与运行身份

- [ ] 3.1 建立并归档 L2 full-result contract child change，输出 deep_dive/watch/skip/error、usage 和 failure summary
- [ ] 3.2 建立并归档 canonical ticker/run identity child change，确保结果可定位到 run、规则版本和输入快照

## 4. 规模预检

- [ ] 4.1 固定不少于 300 只、覆盖多行业与不同风险类型的验证样本
- [ ] 4.2 完成样本运行，证明关键字段可用率、失败隔离和 verdict 分布满足进入全市场实跑的前置条件

## 5. 全市场工程 Gate

- [ ] 5.1 建立并归档全市场 performance/cost child change
- [ ] 5.2 完成一次真实全市场 warm-cache L1+L2 运行，证明耗时 ≤15 分钟、关键字段可用率 ≥95%、L2 成本 ≤¥2、未处理异常为 0
- [ ] 5.3 保存完整漏斗、降级分布、失败分布和运行配置证据

## 6. 产品 Gate

- [ ] 6.1 固定通过工程 Gate 的 ScreeningProfile 和 run，完成用户 Top 20 逐只复核
- [ ] 6.2 证明至少 70% Top 20 被判断为值得进一步研究；若失败，建立新的校准 child change 后重跑

## 7. Umbrella Closure

- [ ] 7.1 确认所有必要 child changes 均引用本 umbrella 且已独立归档
- [ ] 7.2 汇总 G1 evidence bundle，逐项对照 capability spec 确认无缺口
- [ ] 7.3 仅在真实 Gate 全部通过后标记 G1 capability passed，并记录 G2 正式验收放行决定
