# G3 Umbrella Milestones

> 本 change 是能力宪章，不应直接使用 `/opsx:apply` 作为巨型实现计划。以下每项必须在 G2 Gate 通过后，通过独立 child change 实现、验证和归档；checkbox 仅记录 G3 Capability Gate 的证据闭环。

## 1. 上游契约与放行

- [ ] 1.1 确认 G2 capability passed，并取得稳定 `InvestmentThesis` contract 与质量状态语义
- [ ] 1.2 建立并归档 InvestmentThesis-to-HoldingContract child change，明确只接受 passed Thesis

## 2. HoldingContract 领域模型

- [ ] 2.1 建立并归档 HoldingContract schema/lifecycle child change
- [ ] 2.2 覆盖 draft、activate、versioned amend、review、close 和人工 override
- [ ] 2.3 验证成本、仓位、承受回撤、持有期、复核周期和冷静期的输入校验与错误提示

## 3. 持仓真值源

- [ ] 3.1 建立并归档 HoldingsRepository child change
- [ ] 3.2 证明 CandidateWatchlist 变化不会自动创建、关闭或停止监控 active holding
- [ ] 3.3 建立 append-only contract/state/history identity

## 4. 监控接口

- [ ] 4.1 建立并归档 MonitorSignal contract child change
- [ ] 4.2 证明 signal 包含来源、时间、严重度、key variable、证据引用和数据质量
- [ ] 4.3 证明 L4 不越权直接决定状态或交易动作

## 5. 确定性状态机

- [ ] 5.1 建立并归档 holding state-machine child change
- [ ] 5.2 覆盖 Green、Yellow、Red、Blue 和 Rebalance Review
- [ ] 5.3 证明每次状态变化映射到 contract rule + evidence，价格下跌不能单独触发卖出，Thesis 破坏不能被长期主义隐藏

## 6. 交易前纪律检查

- [ ] 6.1 建立并归档 pre-trade-check child change
- [ ] 6.2 覆盖 add、sell、trim 的正反向场景、冷静期、仓位上限和 Thesis-break evidence
- [ ] 6.3 证明所有输出只做纪律审查且自动交易次数为 0

## 7. 历史场景回放

- [ ] 7.1 建立并归档 historical-scenario-replay child change
- [ ] 7.2 预注册并通过五类状态场景，保存规则命中、证据和前后状态
- [ ] 7.3 对误报、漏报和人工 override 建立可复盘记录

## 8. Shadow Mode 产品 Gate

- [ ] 8.1 选择并冻结 3-5 只真实或模拟持仓及合同版本
- [ ] 8.2 连续运行至少四周 shadow mode，记录周期性与事件触发评估
- [ ] 8.3 证明每次 add/sell/trim 请求均经过 pre_trade_check，自动交易次数为 0
- [ ] 8.4 验证用户可在一分钟内理解状态、原因、允许/禁止动作和待验证项

## 9. 后续体验层

- [ ] 9.1 仅在核心 Gate 通过后建立前端状态灯与复核界面 child change
- [ ] 9.2 前端覆盖 loading、empty、error 三态，以及持仓参数校验和明确错误提示

## 10. Umbrella Closure

- [ ] 10.1 确认所有必要 child changes 均引用本 umbrella 且已独立归档
- [ ] 10.2 汇总 G3 evidence bundle，逐项对照 capability spec 确认无缺口
- [ ] 10.3 仅在历史回放与至少四周 shadow mode 全部通过后标记 G3 capability passed；否则保留人工 checklist 并继续修复
