# Multi-Agent 股票分析系统 · 架构设计方案

> 日期：2026-06-23
> 基于 UZI-Skill v3.x 代码分析 + 第一性原理需求拆解

---

## 一、现有系统诊断

### 1.1 系统本质

UZI-Skill 是一个**传统量化多因子打分系统**，不是 AI 驱动的分析系统：

- **数据采集层**：22 维 fetcher + 三级容错 + wave 并发 → 这是真正的工程资产
- **决策层**：66 套 if-else 规则引擎 + 模板化台词 + 线性加权 → 固化的、无推理能力
- **呈现层**：SVG 可视化 + HTML 报告 → 形式完整但内容空洞

### 1.2 核心问题

| 问题 | 表现 | 根因 |
|---|---|---|
| 评委同质化 | 巴菲特和芒格的区别只是规则权重不同 | 规则引擎无法表达投资哲学差异 |
| 辩论是假的 | Great Divide 只是取分最高/最低的人拼预录台词 | 评委之间没有交互，66 票独立并行 |
| 信息浪费 | 采了 22 维数据，规则引擎只消费 ~60 个扁平字段 | 大量定性数据在打分环节丢失 |
| verdict 线性化 | fund×0.6 + consensus×0.4，阈值切档 | 真实投资决策不是加权求和 |
| 无选股能力 | 每次分析必须指定 ticker | 只有"分析"没有"发现" |

### 1.3 可复用资产（保留）

- 22 维数据采集链（fetch_*.py）+ 三级容错
- Wave 分层并发 + mini_racer 串行锁 + resume 机制
- stock_features.py 统一特征提取（单一数据契约）
- compute_deep_methods.py 机构级金融模型（DCF/LBO/Comps/三表预测）
- Pipeline 三段式解耦（collect → score → synthesize）
- stock_style.py 风格识别（白马/成长/周期/小盘等）

---

## 二、需求拆解——第一性原理

### 2.1 用户画像

A 股价值投资小白投资者，核心需求：
1. **选股**：从全市场找到低估值、好生意、合适时点的标的
2. **深研**：对候选股票做深度分析，辅助买卖决策
3. **监控**：对持仓和观察名单持续跟踪

### 2.2 需求不冲突——它们是投资工作流的不同阶段

```
全市场 5000 只 A 股
    │
    │ ① 选股（快、便宜、广）
    ▼
候选池 ~200 只
    │
    │ ② 初筛（中等速度、LLM 浅分析）
    ▼
观察名单 ~20 只
    │
    │ ③ 深研（慢、贵、multi-agent 辩论）
    ▼
持仓 ~5 只
    │
    │ ④ 监控（定期轻量重跑 + 事件触发）
    ▼
继续持有 / 加仓 / 减仓 / 清仓
```

### 2.3 成本模型

| 阶段 | 操作 | 每只成本 | 数量 | 总成本 |
|---|---|---|---|---|
| ① 量化筛选 | 纯数字过滤，零 LLM | ≈ 0 | 5000 → 200 | ≈ 0 |
| ② LLM 初筛 | 1 次短调用（3-5 句判断） | ≈ ¥0.01 | 200 → 20 | ≈ ¥2 |
| ③ 深研 | multi-agent 辩论（5 agent × 多轮） | ≈ ¥1-3 | 20 → 5 | ≈ ¥20-60 |
| ④ 监控 | 轻量重跑 + diff | ≈ ¥0.1 | 5-20 只/周 | ≈ ¥2/周 |

**总成本约 ¥25-70 完成一轮完整的选股-研究-建仓流程。**

---

## 三、目标架构——三层漏斗 + 数据层复用

```
┌───────────────────────────────────────────────────────────┐
│                   DATA LAYER（复用现有）                    │
│                                                           │
│  22 fetcher + 三级容错 + resume + wave 并发               │
│  stock_features.py 特征提取                                │
│  compute_deep_methods.py 金融模型 (DCF/LBO/Comps)        │
│                                                           │
│  新增: batch mode — 对 N 只股票并发跑 lite fetcher        │
│        (只跑 0_basic + 1_financials + 2_kline + 10_valuation)│
└───────────────────────────┬───────────────────────────────┘
                            │
          ┌─────────────────┼─────────────────┐
          ▼                 ▼                 ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐
│ L1: Screener │  │ L2: Scout    │  │ L3: Analyst Council  │
│ 量化筛选      │  │ LLM 初筛     │  │ Multi-Agent 深研      │
│              │  │              │  │                      │
│ 纯数字       │  │ 1 agent      │  │ 5+1 persona agents   │
│ 无 LLM       │  │ 快速判断      │  │ + 辩论编排             │
│ 5000→200     │  │ 200→20       │  │ + Devil's Advocate   │
│ <1 min       │  │ ~10 min      │  │ ~5 min/股             │
└──────────────┘  └──────────────┘  └──────────────────────┘
          │                 │                 │
          ▼                 ▼                 ▼
┌───────────────────────────────────────────────────────────┐
│                   WATCHLIST + ALERTS                       │
│  定期重跑 L1-L2 · 持仓股事件触发 L3 · 估值到达买入区间提醒  │
└───────────────────────────────────────────────────────────┘
```

---

## 四、Layer 1: Screener（量化筛选）

### 4.1 设计原则

- **纯 Python，零 LLM 调用**
- 复用现有 fetch_basic.py / fetch_financials.py / fetch_kline.py / fetch_valuation.py
- 新增 batch wrapper：对 N 只股票并发采集（max_workers=10）

### 4.2 硬门槛过滤（Hard Gates）

```python
HARD_GATES = {
    # 价值投资者的硬门槛
    "pe_ttm": (0, 30),           # PE 不能为负也不能太高
    "pb": (0, 5),                # PB 合理范围
    "roe_last": (10, None),      # ROE > 10%（巴菲特底线）
    "market_cap_yi": (30, None), # 市值 > 30 亿（流动性）
    "revenue_growth_3y": (5, None),  # 不是僵尸企业
    "list_years": (3, None),     # 上市 > 3 年（有历史数据）
}
```

### 4.3 因子打分体系

```python
FACTOR_SCORES = {
    "value": "pe_ttm分位 + pb分位 + 股息率",           # 越便宜越好
    "quality": "roe_5y_avg + 净利率 + 负债率倒数",     # 好生意
    "safety": "自由现金流 + 分红连续性 + 负债率",       # 不会暴雷
    "momentum": "6月涨幅(反转) + 成交量变化",           # 不追高
}
```

### 4.4 反价值陷阱因子（关键创新）

A 股价值投资最容易踩的坑是"价值陷阱"——便宜是因为真的烂。

```python
ANTI_TRAP = {
    "roe_declining": "ROE 3 年趋势下降 → 扣分",
    "cash_flow_divergence": "净利润正但经营现金流负 → 红旗",
    "receivable_explosion": "应收账款增速 > 营收增速 → 可能造假",
    "goodwill_ratio": "商誉 / 净资产 > 30% → 减值风险",
    "pledge_ratio": "大股东质押比 > 60% → 资金链紧张",
    "audit_opinion": "非标审计意见 → 直接排除",
    "frequent_cfo_change": "3 年内换过 CFO → 治理风险",
}
```

### 4.5 数据来源（复用现有）

| 数据 | 来源 | 对应模块 |
|---|---|---|
| 全 A 股 basic | akshare stock_zh_a_spot_em() | fetch_basic.py 逻辑 |
| 财报指标 | akshare + 东财 F10 | fetch_financials.py |
| K 线 / 量价 | 东财 + akshare | fetch_kline.py |
| 估值分位 | 东财 + akshare | fetch_valuation.py |
| 质押/商誉 | akshare 个股风险数据 | 新增 fetch_risk.py |

---

## 五、Layer 2: Scout Agent（LLM 初筛）

### 5.1 设计原则

- **成本极低**：200 只 × ~200 tokens input + ~100 tokens output ≈ $0.5
- **速度极快**：并发 20 请求，2-3 分钟全部完成
- **过滤质量远超纯数字**：LLM 能识别规则引擎抓不到的 pattern

### 5.2 Prompt 设计

```
你是一个 A 股价值投资初筛分析师。请用 3-5 句话回答：

1. 这是一家什么生意？（一句话）
2. 便宜吗？（PE/PB 分位 + 同行对比）
3. 生意好吗？（ROE 趋势 + 现金流质量）
4. 有什么明显的红旗？（负债/质押/应收/商誉/大股东减持）
5. 一句话结论：值得深研 / 观望 / 排除

输出 JSON: {
  verdict: "deep_dive|watch|skip",
  confidence: 0-100,
  one_liner: "...",
  red_flags: [...],
  green_flags: [...]
}
```

### 5.3 输入格式（~200 tokens）

```
股票: 海天味业 (603288.SH)
行业: 调味品
市值: 2800亿
PE(TTM): 38.5 (5年分位: 25%)
PB: 8.2
ROE(近5年): 32%, 30%, 28%, 25%, 22%  ← 趋势下降
净利率: 26%
负债率: 18%
经营现金流: +45亿 (净利润 +42亿) ← 匹配
应收增速: 3% vs 营收增速: 8% ← 正常
商誉/净资产: 2%
大股东质押: 5%
股息率: 1.8%
近6月涨幅: -12%
```

### 5.4 输出示例

```json
{
  "verdict": "watch",
  "confidence": 72,
  "one_liner": "调味品龙头，生意模式优秀但估值仍偏贵，ROE 连续下降需观察是否为周期性还是结构性",
  "red_flags": [
    "ROE 从 32% 降到 22%，连续 5 年下降",
    "PE 38x 虽然处于历史低位但仍不算便宜"
  ],
  "green_flags": [
    "现金流与净利润匹配，盈利质量高",
    "负债率仅 18%，财务健康",
    "行业地位稳固，调味品龙头护城河清晰"
  ]
}
```

### 5.5 实现

```python
from openai import OpenAI

SCOUT_SYSTEM_PROMPT = """你是 A 股价值投资初筛分析师..."""

def scout_batch(candidates: list[dict]) -> list[dict]:
    """并发对 200 只股票做 LLM 初筛"""
    client = OpenAI()
    results = []
    
    for batch in chunk(candidates, 20):  # 每批 20 并发
        futures = []
        for stock in batch:
            f = client.chat.completions.create(
                model="gpt-4o-mini",  # 便宜够用
                messages=[
                    {"role": "system", "content": SCOUT_SYSTEM_PROMPT},
                    {"role": "user", "content": format_stock_summary(stock)}
                ],
                response_format={"type": "json_object"},
                max_tokens=200,
            )
            futures.append(f)
        results.extend([parse_result(f) for f in futures])
    
    return sorted(results, key=lambda r: -r.confidence)[:20]
```

---

## 六、Layer 3: Analyst Council（Multi-Agent 深研天团）

### 6.1 角色设计——5+1 而不是 66

66 个太多，真正有独立视角的 5+1 个就够：

| Agent | 蒸馏来源 | 核心价值 | 独特贡献 |
|---|---|---|---|
| **巴菲特** | 60 年股东信 + 问答会 | 生意质量 + 护城河 | ROE 质量、自由现金流、长期持有视角 |
| **芒格** | Poor Charlie's Almanack | 逆向思维 + 多学科 | 反面论证、心理学偏差检测、能力圈边界 |
| **段永平** | 博客 + 雪球发言 + 采访 | 中国商业直觉 | A 股适配性最强，管理层本分度判断 |
| **冯柳** | 雪球发言 + 采访 | 逆向 + 认知差 | 弱势研究法、困境反转、"别人不要的我看看" |
| **张坤** | 基金季报 + 路演纪要 | A 股消费/医药 | 赛道选择、估值容忍度、持仓集中逻辑 |
| **Devil's Advocate** | 不需要蒸馏 | 专门找漏洞 | "你们的共识哪里可能出错？" |

**为什么是这 5+1**：
- 巴菲特 + 芒格 = 经典价值框架（全球视角）
- 段永平 = 中国商业理解力（A 股最适配）
- 冯柳 = 逆向思维（A 股独有的 alpha 来源）
- 张坤 = A 股实操标杆（消费/医药/白酒赛道的估值容忍度）
- Devil's Advocate = 防止群体思维

### 6.2 Prompt 蒸馏方法——决策框架而非语录

**不要只做语录摘录**，要做**决策框架蒸馏**。

#### 段永平 Agent Prompt 示例

```markdown
## 你是段永平

### 核心决策框架
1. **商业模式优先**：先问"这是不是一门好生意"，再看数字
   - 好生意 = 有定价权 + 轻资产 + 高复购
   - 如果答不上来"这家公司靠什么赚钱"，直接跳过
2. **管理层本分度**：
   - 管理层有没有做过让股东不舒服的事？（减持、关联交易、乱投资）
   - 管理层有没有说过大话没兑现？
3. **能力圈**：看不懂的生意不碰，宁可错过不可做错
4. **逆向思维**：如果这个公司明天退市，我慌不慌？

### 你实际买过的股票
- 网易（2002，$0.8，困境反转 + 看懂了游戏业务）
- 苹果（2011+，消费生态护城河）
- 茅台（品牌定价权 + 简单商业模式）
- GE（2009，金融危机抄底）
- UHAL（2003，破产困境反转）

### 你不会买的股票
- 看不懂的复杂业务
- 需要持续大量资本开支的行业
- 管理层不本分的公司（哪怕数字好看）
- 纯靠概念和叙事的公司

### 你的表达风格
- 直白，不绕弯子
- 喜欢用反问和类比
- 经常说"看不懂"、"不在能力圈"
- 对好公司愿意给高价，对烂公司白送也不要
- 会提到自己做实业的经验（步步高/OPPO/vivo）
```

#### 芒格 Agent Prompt 示例

```markdown
## 你是查理·芒格

### 核心决策框架
1. **逆向思考**：先想怎么会失败（"反过来想，总是反过来想"）
2. **25 个心理偏差检测**：逐一检查是否存在
   - 激励偏差（管理层有动机做蠢事吗？）
   - 确认偏差（我们是不是只看好的？）
   - 社会认同（大家都看好 = 不一定对）
   - 锤子综合症（我们是不是因为手里有框架就硬套？）
3. **格栅思维**：从不同学科角度交叉验证
   - 经济学（供需、竞争格局）
   - 心理学（消费者行为、管理层动机）
   - 数学（概率、复利）
4. **能力圈边界**：宁可不做也不做错

### 你的表达风格
- 毒舌但精准
- 喜欢用类比和寓言
- 经常引用西塞罗、富兰克林
- 对愚蠢的事情毫不留情
- "如果我知道我会死在哪里，我就永远不去那个地方"
```

### 6.3 结构化输出

每个 agent 输出必须是 JSON：

```json
{
  "signal": "bullish|bearish|neutral|skip",
  "conviction": 0-100,
  "core_thesis": "一句话核心理由",
  "key_metrics": ["引用的具体数据"],
  "risks": ["我看到的最大风险"],
  "what_would_change_my_mind": "什么情况下我会改变看法",
  "out_of_circle": false,
  "historical_parallel": "类似的历史案例（如有）"
}
```

**what_would_change_my_mind 是最有价值的字段**——它告诉你这只股票的关键变量是什么。

### 6.4 辩论机制——真正的多轮对话

```
Round 1: 各自表态（每人读数据，给出初步判断 + 核心理由）
    │
    ▼
Round 2: 交叉质疑（每人可以 challenge 其他人的判断）
    │     "巴菲特认为护城河深，但段永平指出管理层去年减持了 15%"
    │     "冯柳认为有认知差，但芒格质疑这是不是'接飞刀'"
    ▼
Round 3: Devil's Advocate 总结所有盲点
    │     "你们 5 个人都看好，但没人讨论过 XXX 风险"
    ▼
Round 4: 收敛共识
    │     综合结论 + 保留的分歧点 + 需要进一步验证的事项
    ▼
Output: 结构化研判 + 完整辩论记录
```

### 6.5 辩论实现

```python
# council/debate.py
def run_council(stock_data: dict) -> dict:
    """5+1 agent 多轮辩论"""
    
    # Round 1: 各自表态
    opinions = {}
    for name, prompt in INVESTOR_PROMPTS.items():
        opinions[name] = call_agent(
            system=prompt,
            user=f"分析以下股票数据并给出你的判断:\n{stock_data}",
            response_format={"type": "json_object"}
        )
    
    # Round 2: 交叉质疑
    challenges = {}
    for name, prompt in INVESTOR_PROMPTS.items():
        other_opinions = {k: v for k, v in opinions.items() if k != name}
        challenges[name] = call_agent(
            system=prompt,
            user=f"你的判断是: {opinions[name]}\n\n其他人的判断: {other_opinions}\n\n"
                 f"你有什么不同意见？challenge 其他人的判断。",
        )
    
    # Round 3: Devil's Advocate
    all_rounds = {"opinions": opinions, "challenges": challenges}
    devils = call_devils_advocate(
        context=f"以下是 5 位投资者的讨论:\n{all_rounds}\n\n股票数据: {stock_data}",
        instruction="找出他们所有人可能忽略的风险和盲点"
    )
    
    # Round 4: 收敛（用主 agent 综合）
    consensus = synthesize_consensus(opinions, challenges, devils)
    
    return {
        "opinions": opinions,
        "challenges": challenges,
        "devils_report": devils,
        "consensus": consensus,
        "full_transcript": [opinions, challenges, devils, consensus]
    }
```

### 6.6 Prompt 校准方法

用真实案例校准每个 agent 的判断质量：

```python
# 校准用例——巴菲特应该看多的
CALIBRATION_BULL = [
    {"ticker": "600519.SH", "name": "贵州茅台", "reason": "品牌定价权 + 简单商业模式"},
    {"ticker": "002594.SZ", "name": "比亚迪", "reason": "巴菲特实际持有"},
]

# 校准用例——巴菲特应该看空或犹豫的
CALIBRATION_BEAR = [
    {"ticker": "600900.SH", "name": "长江电力", "reason": "重资产公用事业，巴菲特不偏好"},
]

# 校准用例——段永平应该看多的
CALIBRATION_DUAN_BULL = [
    {"ticker": "600519.SH", "name": "贵州茅台", "reason": "段永平实际持有"},
]

# 跑校准测试
for case in CALIBRATION_BULL:
    result = call_agent("buffett", case)
    assert result["signal"] == "bullish", f"巴菲特应该看多 {case['name']}"
```

---

## 七、Layer 4: Watchlist & Monitoring（监控层）

```python
def weekly_monitor(watchlist: list):
    """每周自动监控"""
    for stock in watchlist:
        # 轻量重跑 L1 指标
        features = fetch_lite(stock.ticker)
        
        # diff 检测——什么变了？
        changes = diff_with_previous(features)
        
        if changes.significant:
            # 触发 L2 Scout 重新评估
            scout_result = scout_analyze(stock.ticker, features)
            
            if scout_result.verdict_changed:
                # 触发 L3 深研
                council_result = run_council(fetch_full(stock.ticker))
                save_and_alert(stock.ticker, council_result)
        
        # 估值区间提醒
        if features.price <= stock.buy_zone:
            alert(f"🟢 {stock.name} 进入买入区间！当前 {features.price}")
        
        # 风险事件触发
        if detect_risk_event(stock.ticker):  # 大股东减持/业绩预告/审计变更
            alert(f"🔴 {stock.name} 发生风险事件，建议重新审视")
```

---

## 八、具体实施路径

### Phase 0：剥离可复用资产（1-2 天）

从 UZI-Skill 中提取独立模块到新 repo：

```
uzi-data/                    # 新 repo，纯数据层
├── fetchers/                # 从 fetch_*.py 提取
│   ├── basic.py
│   ├── financials.py
│   ├── kline.py
│   ├── valuation.py
│   └── ...
├── lib/
│   ├── stock_features.py    # 直接复用
│   ├── market_router.py     # 直接复用
│   ├── fin_models.py        # 直接复用
│   └── batch_fetcher.py     # 🆕 批量采集 wrapper
├── screener/                # 🆕 L1 选股引擎
│   ├── filters.py
│   ├── factors.py
│   └── anti_trap.py
└── cache/
```

### Phase 1：L1 Screener（3-5 天）

```python
# screener/main.py
from fetchers.basic import batch_fetch_basic
from fetchers.financials import batch_fetch_financials

def screen_a_shares(top_n=200):
    """全市场扫描 → 候选池"""
    all_stocks = fetch_all_a_basic()      # ~5000 只
    candidates = apply_hard_gates(all_stocks)  # → ~800
    financials = batch_fetch_financials(candidates)  # 并发采集
    scored = score_factors(candidates, financials)
    scored = apply_anti_trap(scored)
    return rank_and_slice(scored, top_n)   # → 200
```

### Phase 2：L2 Scout Agent（3-5 天）

- 设计 + 校准 Scout prompt
- 实现 batch 并发调用
- 输出结构化 verdict 列表

### Phase 3：L3 Analyst Council（1-2 周）

- 蒸馏 5 位投资者的决策框架 prompt
- 实现辩论编排器（4 轮）
- 校准测试（真实案例验证）
- 报告渲染（辩论记录可视化）

### Phase 4：集成 + Watchlist（1 周）

- 统一 CLI 入口
- 定时监控任务
- 估值区间提醒
- 事件触发机制

### 迭代原则

> **先把 L1 + L2 做好（选股漏斗），这部分的 ROI 最高。**
> L3 的 multi-agent 深研可以作为第二步慢慢迭代——先用一个 agent 做深度分析，
> 再加第二个、第三个，边加边看辩论质量有没有信息增量。
> 如果 5 个 agent 说的话和 1 个 agent 没区别，就别加到 5 个。

---

## 九、风险与期望管理

### 9.1 技术风险

| 风险 | 应对 |
|---|---|
| LLM 推理不稳定（同股不同结果） | structured output + temperature=0 + 置信度校验 |
| Prompt 蒸馏质量差（不像真人） | 真实案例校准 + 持续迭代 prompt |
| 数据源不稳定（akshare 接口变更） | 三级容错链已验证可用 |
| 辩论收敛为废话（"各有道理"） | Devil's Advocate 强制找具体漏洞 |

### 9.2 期望管理

A 股价值投资本身是高难度动作。段永平、冯柳、张坤能做到超额收益，不只是因为分析框架好，还因为：
- **信息优势**（产业链调研、管理层接触）
- **心理优势**（拿得住、敢逆向）
- **时间优势**（全职投入、数十年积累）

AI 能帮你做的是**缩小信息处理效率的差距**：
- 更快看完更多数据
- 更系统地应用投资框架
- 更诚实地记录推理过程
- 提醒你关注容易忽略的风险

**AI 不能替你做的**：
- 产业链调研和实地考察
- 扛住 30% 回撤的心理压力
- 在全市场恐慌时逆向买入
- 判断管理层的人品和能力（只能基于公开信息推断）

---

## 十、一句话总结

> **保留数据层，重做决策层：用三层漏斗（量化筛选 → LLM 初筛 → Multi-Agent 深研）替代 66 个规则引擎，让 AI 真正"思考"而不是"打勾"。**
