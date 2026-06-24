# PRD: RULE.md 分层体系 + 历史案例库

> 基于 2026-06-23 设计讨论，对 design-v1 的补充设计
> 两个独立模块，但都与「系统如何持续进化」相关

---

## 一、RULE.md 分层体系

### 1.1 设计动机

借鉴 Claude Code 的 `CLAUDE.md` 分层思路——全局规则（`~/.claude/CLAUDE.md`）定义通用行为准则，项目级规则（`<repo>/CLAUDE.md`）定义项目特定约束。trade-agent 的 agent 天团也需要类似的规则继承体系。

**核心问题**：5+1 个 agent 各自有独立的 system prompt，但有些规则是**所有 agent 都必须遵守的**（如「不择时」）。如果每个 agent prompt 都重复写一遍，维护成本高，容易遗漏，且改一条规则要改 6 个文件。

### 1.2 三层结构

```
~/.trade-agent/RULE.md          ← 全局投资铁律（用户级）
        │
        ▼ 继承 + 可覆盖
value-screener/RULE.md          ← 项目级规则（A 股特定）
        │
        ▼ 继承 + 可覆盖，但全局铁律不可推翻
council/prompts/*.md            ← agent 级（巴菲特/芒格/...）
```

### 1.3 各层职责

| 层级 | 类比 | 内容 | 优先级 |
|------|------|------|--------|
| **全局 RULE.md** | `~/.claude/CLAUDE.md` | 投资铁律——不择时、不追高、不碰不懂的、格雷厄姆纪律底线 | **不可覆盖** |
| **项目 RULE.md** | `value-screener/CLAUDE.md` | A 股特定规则——当前市场周期判断、行业排除列表、L1 因子权重偏好 | 可覆盖 agent 默认，不可破全局铁律 |
| **Agent prompt** | sub-agent 指令 | 各投资人的决策框架 + 风格 | 在两层 RULE 约束内自由发挥 |

### 1.4 优先级规则

```
全局 RULE.md（硬约束，任何 agent 不得违反）
    ↓
项目 RULE.md（默认约束，agent 可提出异议但需明确论证）
    ↓
Agent system prompt（个性化学术立场）
```

**关键设计**：全局铁律不是「建议」，是 agent 的宪法。如果某个 agent 在辩论中违反铁律（如「现在 PE 分位 15%，是买入时机」——这隐含了择时判断），应在 prompt 中要求 agent 标注 `⚠️ violates global rule`，或由系统在组装 prompt 时前置注入约束。

### 1.5 实现方式

```python
def build_system_prompt(agent_name: str) -> str:
    """组装 agent 的完整 system prompt"""
    global_rules = load("~/.trade-agent/RULE.md")
    project_rules = load("value-screener/RULE.md")
    agent_prompt = load(f"council/prompts/{agent_name}.md")

    return f"""
{global_rules}

{project_rules}

{agent_prompt}

注意：以上全局规则是你的硬约束，不可违反。项目规则如有异议需明确论证。
"""
```

实现成本极低——纯字符串拼接。Phase 0 就可以建骨架。

### 1.6 为什么有用

1. **全局铁律一次定义，所有 agent 自动继承**——「不择时」写一次，巴菲特和段永平都不用各自重复；Devil's Advocate 也会自动用这个标准去挑刺
2. **项目级规则可以随市场环境更新**——2026 年觉得「消费板块整体回避」，改项目 RULE.md 就行，不用改 6 个 agent prompt
3. **agent prompt 变干净**——只保留「这个人怎么看问题」，不掺和「这个系统有什么底线」

### 1.7 全局 RULE.md 草稿

```markdown
# 全局投资铁律

## 不可违反的底线

1. **不择时**：不预测股价短期走势，不判断"现在是不是买入时机"。只判断"这个价格下这个生意值不值得拥有"。
2. **不懂不做**：看不懂的生意直接跳过，宁可错过不可做错。
3. **不追高**：不因为"最近涨了"或"大家都在买"而买入。
4. **格雷厄姆纪律**：PE×PB > 22.5 的标的，必须有特别强的护城河论证才能进入下一轮，否则直接排除。

## 分析原则

- 买入决策必须基于"如果明天交易所关门 5 年，我还愿意持有吗？"
- 任何判断必须有具体数据支撑，不允许"感觉便宜"、"可能有机会"的模糊表述
- 分歧是信息，不要为了达成共识而抹平分歧

## 行为约束

- 不推荐个股买卖时点
- 不预测短期涨跌
- 不做技术分析
```

### 1.8 项目 RULE.md 草稿

> ⚠️ **设计决策（Codex R2）**：项目规则拆为两块——结构性规则（长期有效，改需记录理由）和周期性判断（每季度复核，标注有效期）。避免「重点关注消费复苏」这类周期性判断混入结构性规则，过期后变成错误约束。

```markdown
# 项目级规则：A 股价值投资选股

## 一、结构性规则（长期有效 · 修改需记录理由）

### 行业排除（可覆盖，但需论证）

- 金融/券商：估值指标失效，适用不同框架
- 强周期：钢铁/煤炭/航运/化工/水泥/养殖
- ST/*ST/退市风险

### L1 因子权重

- 质量 50% / 估值 30% / 安全边际 20%
- 权重调整需记录理由

### L3 深研准入

- 只有 L2 verdict = "deep_dive" 的标的才进入 L3
- L3 每次辩论必须产生明确的"关键变量"列表（what_would_change_my_mind）

## 二、周期性判断（每季度复核 · 标注有效期）

> 有效期：2026-06-23 ~ 2026-09-23（下次复核日）
> 复核人：用户

- 市场整体估值：中等偏低
- 重点关注：消费复苏、制造业升级、高股息防御
- 谨慎对待：地产链、中小银行、高商誉公司

注意：以上为周期性判断，反映当前市场环境，不是硬约束。
agent 可以在辩论中对这些判断提出异议并记录理由。
```

---

## 二、历史案例库

### 2.1 设计动机

MVP（选股 + 个股评价）做完后，需要一种方式验证系统逻辑是否自洽。**不是验证能不能预测涨跌，是验证分析框架有没有盲区。**

### 2.2 走偏 vs 不走偏的分界线

| | 走偏 ❌ | 不走偏 ✅ |
|---|---|---|
| **目标** | 优化选股收益 / 预测涨跌 | 验证分析框架的逻辑一致性 |
| **问的问题** | "系统能不能提前抓到光模块暴涨？" | "光模块暴涨前，L1/L2 会不会筛出这些票？L3 天团怎么评价？" |
| **优化方向** | 调参数让回测收益率更高 | 调 prompt 让 agent 判断更符合其投资哲学 |
| **本质** | 把系统当量化策略优化 | 把系统当分析工具校准 |

### 2.3 案例库结构

MVP 做完后，创建 `value-screener/cases/` 目录：

```
value-screener/
├── cases/
│   ├── 2026-01-optical-module/       # 光模块暴涨
│   │   ├── context.md                # 事件背景 + 时间线
│   │   ├── candidates.json           # 相关股票列表
│   │   ├── l1_snapshot.json          # 暴涨前的 L1 指标快照
│   │   ├── council_transcript.md     # 天团辩论记录（事后跑）
│   │   └── postmortem.md             # 复盘：框架盲区在哪
│   │
│   ├── 2025-xx-liquor-correction/    # 白酒回调
│   ├── 2024-xx-real-estate-crisis/   # 地产暴雷
│   └── ...
│
└── tests/
    └── test_calibration.py           # 校准测试 = design-v1 6.6 节的校准用例
```

### 2.4 案例的正确用法——以光模块暴涨为例

2026 年初光模块（中际旭创/新易盛/天孚通信）暴涨，这不是用来验证「系统能不能预测暴涨」的——**价值投资系统本来就不预测暴涨**。正确用法：

1. **回溯 L1**：2025 年中，这些票在 L1 筛选里是什么位置？F-Score 几分？PE/PB 分位？如果 L1 把它们排除了（比如 PE 太高），那排除理由是否合理？
2. **回溯 L2**：如果 L1 没排除，L2 scout 会怎么判？当时有什么红旗/绿旗？
3. **回溯 L3**：如果丢进天团，巴菲特会怎么说？段永平会怎么说？（光模块是段永平说的「看不懂的复杂业务」吗？冯柳会不会在这种「高成长+高估值」的票上找到认知差？）
4. **记录分歧**：天团一致看好 / 一致看空 / 有分歧？如果一致看空但后来暴涨，错在哪里？是分析框架的问题，还是**价值投资框架本身就覆盖不了这类机会**（这是可以接受的）？
5. **写 postmortem**：不是找 bug，是记录盲区——「价值框架在此类高成长科技股上的已知局限」

### 2.5 校准测试

> ⚠️ **设计决策（Codex R5）**：校准测试的价值不在于 assert pass/fail，而在于**人工 review transcript**。
> 关键词 assert 和 signal 断言只是 smoke test（确保 agent 没有完全跑偏），不能把测试通过等同于校准合格。
> 真正的校准流程是：跑完案例 → 生成对比报告（agent 说了什么 vs 真实投资人说过什么 vs 实际发生了什么）→ 人工判断推理质量。

#### 2.5.1 Smoke Test（自动化 · 防跑偏）

```python
# tests/test_calibration.py

def test_optical_module_case_smoke():
    """光模块案例 smoke test：确保 agent 没有完全跑偏，不做质量判断"""
    case = load_case("2026-01-optical-module")

    # 1. 验证 L1 行为一致性
    for stock in case.candidates:
        result = run_l1(stock.snapshot)
        assert result.passed or result.exclusion_reason, \
            f"L1 必须对 {stock.name} 有明确判断（通过或排除+理由）"

    # 2. 验证 agent 输出结构完整性（不验证内容正确性）
    for agent_name in ["buffett", "munger", "duan", "feng_liu", "zhang_kun"]:
        result = run_agent(agent_name, case.candidates[0])
        assert result.signal in ("bullish", "bearish", "neutral", "skip")
        assert 0 <= result.conviction <= 100
        assert len(result.core_thesis) > 0
        assert len(result.risks) > 0
        assert len(result.what_would_change_my_mind) > 0
```

#### 2.5.2 校准报告（人工 review · 真正判断质量）

```python
def generate_calibration_report(case_name: str):
    """生成校准对比报告，辅助人工判断推理质量"""
    case = load_case(case_name)

    report = []
    for stock in case.candidates:
        report.append(f"\n## {stock.name} ({stock.ticker})")
        report.append(f"实际结果: {stock.actual_outcome}")

        for agent_name in ["buffett", "munger", "duan", "feng_liu", "zhang_kun"]:
            result = run_agent(agent_name, stock)
            report.append(f"\n### {agent_name}")
            report.append(f"- Signal: {result.signal} (conviction: {result.conviction})")
            report.append(f"- Core thesis: {result.core_thesis}")
            report.append(f"- Risks: {result.risks}")
            report.append(f"- What would change my mind: {result.what_would_change_my_mind}")
            report.append(f"- Historical parallel: {result.historical_parallel}")

    # 输出到文件，供人工 review
    write_report(f"cases/{case_name}/calibration_report.md", "\n".join(report))

    # 自动标注可能需要人工关注的异常
    alerts = []
    for agent_name, result in all_results:
        # 段永平对高复杂度技术股如果 bullish → 需要人工检查推理是否合理
        if agent_name == "duan" and result.signal == "bullish":
            if any(kw in result.core_thesis for kw in ["光模块", "光通信", "芯片"]):
                alerts.append(f"⚠️ 段永平对技术股 bullish，需人工检查能力圈判断")

    return report, alerts
```

**核心原则**：smoke test 只测「格式对 + 没崩」，校准报告才是真正的校准。如果 smoke test 全通过但校准报告里 agent 都在胡说八道，那 prompt 就有问题——关键词匹配是检测不出这个的。

### 2.6 核心原则

> **案例库是用来发现盲区的，不是用来证明系统厉害的。**
> 如果所有案例都「验证通过」，可能不是系统好，而是案例选得不够狠。

### 2.7 迭代节奏

> ⚠️ **时间线已调整（Codex R6）**：案例库从「MVP 完成后」前移到「Phase 3 开始时」。Phase 3 做 agent prompt 校准需要案例，不能等 MVP 做完才开始。

| 阶段 | 做什么 |
|------|--------|
| **Phase 0-2**（L1 + L2 开发） | 设计时预留 `cases/` 目录结构，校准测试框架搭好骨架 |
| **Phase 3 开始时**（L3 天团开发） | 准备 1-2 个最小可用案例（不需要完整 postmortem 和 `l1_snapshot.json`，人工标注关键指标即可），用于 prompt 校准 |
| **Phase 3 中期** | 随 agent prompt 迭代，用案例反复跑校准报告，调 prompt 直到 agent 推理质量过关 |
| **MVP 完成后** | 每季度选 1-2 个有代表性的市场事件做完整回溯 case（含 postmortem） |
| **积累期** | 从 case 中提炼 agent prompt 改进点，回写进 prompt 和 RULE.md |
| **长期** | cases 积累到 10+ 个时，做一次系统性复盘——哪些盲区是框架固有的（接受），哪些是 prompt 可以改进的（修复） |

### 2.8 初期案例的数据策略

> ⚠️ **设计决策（Codex R7）**：初期案例不追求完整的 `l1_snapshot.json`（历史全维度数据获取困难），采用「当前数据 + 人工标注当时的关键指标」方式。

例如光模块案例，手动记录「2025 年 6 月中际旭创 PE 约 XX，PB 约 XX，F-Score 7 分」就够了，不需要重跑整个 L1 pipeline。后续工具链成熟后逐步自动化。

---

## 三、与 design-v1 的关系

| 模块 | 在 design-v1 中的位置 | 本 PRD 补充 |
|------|----------------------|-------------|
| RULE.md 分层 | 未覆盖（agent prompt 写在 6.1-6.2 节） | 新增规则继承体系，作为 agent prompt 的组装层 |
| 案例库 | 6.6 节有校准用例，但局限于单一 agent 立场一致性 | 扩展为完整的案例库 + 回溯框架 + 复盘机制 |
| 实施优先级 | — | RULE.md 分层：Phase 0 建骨架；案例库：Phase 0-2 预留目录，Phase 3 开始准备 1-2 个最小可用案例 |

### 3.1 代码位置（Codex R8）

`build_system_prompt` 放在 `council/prompt_builder.py`，在 `debate.py` 中调用：

```
council/
├── prompt_builder.py    # 🆕 build_system_prompt() + RULE.md 加载
├── prompts/             # 5+1 agent system prompts（不含全局/项目规则）
├── debate.py            # 调用 prompt_builder 组装完整 prompt
├── calibrate.py
└── output.py
```

### 3.2 Agent 异议处理（Codex R4）

项目规则中 agent 可提出异议，但**不做系统自动裁决**。处理流程：

1. Agent 在结构化输出中填写 `project_rule_objection` 字段（可选）
2. 异议记录在辩论输出中，不做自动拦截
3. 最终由用户判断异议是否成立

```json
{
  "project_rule_objection": {
    "rule": "行业排除：强周期/钢铁",
    "reason": "宝钢股份 ROE 连续 5 年 > 15%，股息率 5%，虽属钢铁但不符合典型周期股特征",
    "suggested_action": "建议对此标的豁免行业排除规则"
  }
}
```

---

## 四、已记录风险（不阻塞 MVP）

以下风险点已识别，MVP 阶段暂不实现，但记录在案供后续迭代参考：

| 编号 | 风险 | 来源 | MVP 处理 |
|------|------|------|----------|
| R1 | **执行机制靠 prompt 自律，无运行时校验** | Codex | 不做后处理检查。结构化 JSON 输出 + Devil's Advocate 构成第一/二道防线。MVP 后视 agent 违规频率决定是否加后处理扫描 |
| R3 | **Token 预算**（三层拼接 ~3000-4000 tokens/agent） | Codex | 当前模型上下文窗口足够，不优化。辩论轮数多了再考虑精简 |
| R7 | **回溯数据源获取困难**（历史全维度数据） | Codex | 初期案例用人工标注关键指标，不自建历史数据 pipeline。见 2.8 节 |
| R8 | **代码位置细节** | Codex | 已采纳 `council/prompt_builder.py`，见 3.1 节 |

---

## 附：参考

- Claude Code CLAUDE.md 分层机制：全局 `~/.claude/CLAUDE.md` + 项目 `<repo>/CLAUDE.md`
- design-v1 6.6 节：Prompt 校准方法