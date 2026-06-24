# 待讨论话题清单

> 来自 2026-06-23 设计讨论，design-v1 未充分覆盖的细节话题
> 最后更新：2026-06-23

---

## 状态说明

| 标记 | 含义 |
|------|------|
| ✅ 已解决 | 已写入设计文档 |
| 🟡 部分覆盖 | 有初步方案但细节未定 |
| 🔴 未讨论 | 尚未展开 |
| 🔒 阻塞性 | 动手写代码前必须明确 |

---

## 话题列表

### 1. L1 因子权重 (50/30/20) 的校准 ✅

**已解决**：写入 design-v1 Section 4.8「L1 因子权重校准」。

**决定**：
- 初始值 50/30/20 符合价值投资常识（好生意 > 便宜 > 安全边际），不需要严格回测验证
- 边做边调：跑几轮后看 L2/L3 反馈，如果 L2 经常否决 L1 的 top 候选，说明权重需要调整
- 调优信号：L2 否决率、L3 共识与 L1 排序的背离度

**涉及模块**：L1 Screener

---

### 2. 冯柳 agent 的决策框架 ✅

**已解决**：写入 design-v1 Section 6.2 冯柳 Agent Prompt 示例 + Section 6.3 Agent 特有字段。

**决定**：
- 蒸馏来源：[investment-masters-handbook/feng_liu.md](https://github.com/sou350121/investment-masters-handbook/blob/main/investors/feng_liu.md)（弱者体系完整框架，直接复用）
- 核心决策框架：假设市场是对的 → 赔率优先于胜率 → 左侧买入四条件
- 防止同质化的关键：冯柳特有结构化输出字段（market_consensus / consensus_flaw / odds_ratio / is_reversible / catalyst）
- 防"捡垃圾"约束：结构性不可逆的担心 → PASS；赔率 < 2:1 → PASS；说不清"市场哪里错了" → PASS

---

### 3. 辩论中 agent 之间的信息不对称 ✅

**已解决**：写入 design-v1 Section 6.4.1「Agent 间通信格式与 Token 预算」。

**已覆盖**：design-v1 6.5 节的 `debate.py` 骨架已定义信息可见性控制：
- Round 1：agent 彼此隔离（防从众）
- Round 2：每个 agent 看到其他 4 人的论点（促质疑）
- Round 3：Devil's Advocate 看到全部讨论（找盲区）

**决议**：
- Agent 间消息载体：§6.3 的 `AgentOutput` JSON（结构化、紧凑、~400 tokens/人），不需要额外写自由文本摘要
- 辩论记录：`debate/{ticker}/{date}.md`，append-only，按轮次顺序，供人类复盘 + L4 消费
- Token 预算：~22.6K tokens/辩论，任何现代模型都不会爆窗口
- 不需要「遗忘读文件」机制：LLM 单次调用 context window 固定，不存在中途遗忘行为；文件是审计轨迹不是 agent 记忆

**涉及模块**：L3 Analyst Council

---

### 4. L4 催化事件检测的具体设计 ✅

**已解决**：写入 design-v1 Section 7.1「催化事件检测设计」。

**决定**：
- 催化事件 = 财报超预期 / 分红提升 / 行业政策 / 管理层变动 / 风险事件
- 估值低位（PE 分位 < 20%）是独立条件，不是催化事件（与 §1.2 定义一致）
- 触发提醒 = 估值低位 AND 出现催化事件（两个并列条件）
- `what_would_change_my_mind` 约束只适用于已跑 L3 的持仓股；新发现股无此变量时，催化作为加分项
- 实现细节（数据源、LLM prompt、缓存）等 L1-L3 跑顺后补充

**涉及模块**：L4 Monitor

---

### 5. 回测与验证体系 ✅

**已解决**：写入 design-v1 Section 10.3「回测与验证策略」。

**决定**：
- MVP 不做系统性回测
- 案例库（§6.6）已覆盖基本校准需求
- L1 因子（F-Score/PE/PB/格雷厄姆数）是学术验证过的公式，无需回测
- L2/L3 质性推理的回测成本高、收益有限（历史标注数据难获取，过拟合风险）
- 实际跑几轮后再评估是否需要系统性回测

**涉及模块**：全局

---

### 6. 系统交互形态 ✅

**已解决**：Docker + Streamlit，写入 design-v1「九、技术决策」。

**决定**：MVP 用 Streamlit（纯 Python 数据看板），后续如需复杂交互可迁移到 FastAPI + React。

---

### 7. L2 输出的质量保证 ✅

**已解决**：写入 design-v1 Section 5.6「输出质量保证」。

**决定**：
- `temperature=0` 基础配置，消除模型随机性
- 阈值缓冲带：confidence 40-60 → 强制 `watch`（不强制二选一，减少边界摇摆）
- 缓存 24h：L2 结果 TTL=24h，同一交易日不重复跑
- 多轮投票 MVP 不做（成本 +200%，收益有限，等实际跑出问题再决定）

**涉及模块**：L2 Scout Agent

---

### 8. 数据采集的工程细节 ✅

**已解决**：写入 design-v1 Section 4.7「数据采集工程方案」。

**决定**：
- 三层漏斗式采集（全市场快照 → ~800 只财报+估值+K线 → ~200 只治理+反陷阱）
- L1 只需 5 维（0_basic / 1_financials / 2_kline / 10_valuation / 11_governance），其余 16 维留给 L3
- 全市场快照 4 级容错链（spot_em → tencent qt → 雪球 → baostock），MVP 先做主选 + 兜底 1
- 并发 max_workers=10（Layer 2）/ 5（Layer 3），无 mini_racer 锁风险
- TTL：基础信息 2h，财报/估值/K线/治理 24h，行业分类 7 天
- L1 结果缓存 TTL=24h + diff 缓存（标记新进/新出候选，L4 消费）

---

## 讨论优先级建议

| 优先级 | 话题 | 理由 |
|--------|------|------|
| ✅ P0 | 8. 数据采集工程细节 | 已写入 design-v1 Section 4.7 |
| ✅ P0 | 2. 冯柳 agent 决策框架 | 已写入 design-v1 Section 6.2 + 6.3 |
| ✅ P1 | 3. 辩论上下文窗口 | 已写入 design-v1 §6.4.1 |
| ✅ P1 | 7. L2 输出质量保证 | 已写入 design-v1 §5.6 |
| ✅ P2 | 1. L1 因子权重校准 | 已写入 design-v1 §4.8 |
| ✅ P2 | 4. L4 催化事件检测 | 已写入 design-v1 §7.1 |
| ✅ P2 | 5. 系统性回测 | 已写入 design-v1 §10.3 |