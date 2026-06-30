## Context

L3a（council-foundation）已完成并归档，验证了：
- debate.py 4 轮编排骨架（R1/R2 可运行，R3/R4 是 `# TODO` 占位）
- AgentOutput schema 基础 8 字段 + 严格校验
- 巴菲特单 agent prompt（Level 2 四层结构）+ 校准（茅台看多 / 长江电力看空）
- 辩论记录 append-only 持久化 + 缓存命中检查

AD-09 三门验证结果：机制门 ✓、校准门 ✓、信息增量 ✓（详见 proposal.md Context）。

**L3b 当前代码状态**（直接扩展的文件）：
- `council/agents.py`：`AGENT_REGISTRY` 只注册巴菲特，芒格/段永平/冯柳/张坤/DA/synthesizer 以注释占位
- `council/debate.py`：R3 和 R4 是 `# TODO: 3b 实现 DA agent` / `# TODO: 3b 实现 synthesizer agent`，`final_verdict` 硬编码 `= round1[0].signal`
- `council/prompt.py`：只有 `build_buffett_prompt`
- `council/schema.py`：`AgentOutput` 只有基础 8 字段，`from_dict` 丢弃未定义字段
- `council/calibrate.py`：只校准巴菲特

**约束引用**（见 architecture-decisions.md）：
- AD-04：R1-3 重度推理，R4 中度推理
- AD-05：不引入 Multi-Agent 框架，debate.py 是唯一状态持有者
- AD-07：无格雷厄姆 agent
- AD-08：Level 2 prompt，不引 RAG
- AD-09：辩论增量 gate——5 个 agent 说的话和 1 个没区别就别加到 5 个

## Goals / Non-Goals

**Goals:**
- 注册全天团（4 投资大师 + DA + synthesizer），激活 4 轮完整辩论（R1×4 + R2×4 + R3×1 + R4×1 = 10 次 LLM 调用）；张坤留给后续迭代（蒸馏素材和校准用例不足）
- 实现 DA（综合 R1+R2 找盲点和共识漏洞）和 synthesizer（综合 R1+R2+DA 产出收敛结论 + 保留分歧）
- 支持 agent 特有字段（冯柳 5 字段 + DA 盲点清单），通过 `extra: dict` 透传
- 重构 `CouncilResult` 为显式命名字段（`round1`/`round2`/`round3`/`round4`），新增 `consensus_summary`/`dissent_points`/`pending_verification`
- 交付 L3→L4 接口文件 `watchlist/{date}_council.json`，`key_variables` 与 `pending_verification` 并列
- 验证辩论增量（AD-09 质量门）：R1 core_thesis 有实质差异、R2 有真实修订、DA 盲点未被共识覆盖

**Non-Goals:**
- 不做 L4 监控/watchlist diff（L4 change 的职责）
- 不做 Streamlit 前端
- 不引入 RAG（AD-08）
- 不做格雷厄姆 agent（AD-07）
- 不引入 Multi-Agent 框架（AD-05）
- 不做批跑（消费 L2 ~20 只）——3b 只做单股 council 子命令，批跑留给 L4 触发
- 不做 DA/synthesizer 的 signal 断言校准（它们不是立场型 agent）

## Decisions

### 决策 1：AgentOutput 支持 agent 特有字段（extra: dict 透传）

**选择 A：加 `extra: dict` 透传特有字段。**

`AgentOutput` 新增 `extra: dict = field(default_factory=dict)`，冯柳特有字段（`market_consensus` / `consensus_flaw` / `odds_assessment` / `is_reversible` / `catalyst`）和 DA 盲点清单（`blind_spots: list`）都放进 `extra`。

**理由**：
- 最小改动：基础 8 字段的校验逻辑完全不变，`from_dict` 只把未定义字段收集进 `extra`
- 校验仍只认基础字段：`extra` 中的字段不做类型/值校验（LLM 输出格式不稳定，强校验会误杀）
- `to_dict` / `to_json` 自动包含 `extra`，辩论记录 md 中完整呈现特有字段
- A2A 传给其他 agent 时透传：R2 输入包含他人的 `extra`，其他 agent 可消费（如芒格看到冯柳的 `market_consensus` 后可以针对性质疑）

**排除 B（子类/可选字段）的理由**：schema 膨胀，每种 agent 一个 dataclass，维护成本高，且 LLM 输出格式不稳定时强校验会频繁报错。

**排除 C（3b MVP 不做特有字段）的理由**：§6.3 明确冯柳需要这些字段来体现逆向逻辑的独特性，不做特有字段会导致冯柳与巴菲特同质化（AD-09 辩论增量 gate 直接不过）。

**实现细节**：
- `from_dict`：已知字段按现有逻辑处理，未定义字段收集进 `extra`（不再丢弃）
- `to_dict` / `to_json`：`asdict` 自动包含 `extra`，无需特殊处理
- 辩论记录 md：`extra` 字段在 JSON 块中完整呈现，人类可复盘
- prompt 中告知冯柳/DA 输出这些额外字段，其他 agent 的 prompt 不提及

### 决策 2：DA 与 synthesizer 的 prompt 设计

#### DA（Devil's Advocate）prompt

DA 不是投资大师，不是 Level 2 四层结构。DA 的 system prompt 是职责导向：

```markdown
## 你是质疑者（Devil's Advocate）

### 职责
综合所有分析师的初步判断（R1）和交叉质疑（R2），找出他们遗漏或低估的盲点。

### 工作守则
- 必须找**具体**漏洞，不允许「可能有问题」的泛泛之谈
- 每个盲点必须指向具体的数据或事件（"管理层去年减持了 15%"而非"管理层风险"）
- 如果所有分析师的共识看起来合理，指出"共识哪里可能出错"
- 不要提出新的投资建议，只负责"撕"已有的结论

### 输入
- R1：4 位分析师的独立判断（AgentOutput JSON）
- R2：4 位分析师的交叉质疑（AgentOutput JSON）

### 输出格式
输出 JSON，包含基础 AgentOutput 字段 + extra 中的 blind_spots：
- signal: "neutral"（DA 不给出投资建议，固定 neutral）
- conviction: 0（固定）
- core_thesis: 一句话总结最大盲点
- blind_spots: 盲点列表，每项包含 {title, detail, which_agents_missed_it}
```

**DA 输出格式**：用 `AgentOutput` + `extra.blind_spots`（决策 1 的透传机制）。`signal` 固定 `neutral`，`conviction` 固定 0，`core_thesis` 写最大盲点的一句话总结。`extra.blind_spots` 是列表，每项有 `title` / `detail` / `which_agents_missed_it`。

#### Synthesizer prompt

Synthesizer 是"非投资者收敛角色"（§6.4），职责是综合而非判断：

```markdown
## 你是共识收敛器

### 职责
综合所有分析师的判断（R1）、交叉质疑（R2）和质疑者的盲点（R3），
产出结构化结论。

### 工作守则
- 收敛结论必须反映多数分析师的共识方向
- 保留真实分歧点（不抹平），列出哪些分析师持不同意见及理由
- 列出待验证事项（从 DA 盲点 + what_would_change_my_mind 提取）
- final_signal 基于加权多数（conviction 加权），但分歧严重时降为 neutral

### 输出格式
输出 JSON，包含以下字段（synthesizer 特有 schema，不走 AgentOutput）：
- final_signal: "bullish" | "bearish" | "neutral" | "skip"
- conviction: 0-100（加权平均 conviction）
- consensus_summary: 一句话结论
- dissent_points: 保留的分歧点列表 [{topic, who_disagrees, their_reason}]
- pending_verification: 待验证事项列表（从 DA 盲点 + what_would_change_my_mind 提取）
```

**Synthesizer 输出格式**：不用 `AgentOutput`，用独立的 `SynthesizerOutput` dataclass。理由：synthesizer 的输出语义完全不同（`signal` → `final_signal`、新增 `dissent_points` / `pending_verification`），硬套 `AgentOutput` 会语义混乱。`SynthesizerOutput` 定义在 `schema.py` 中，与 `AgentOutput` 平级。

**MVP 先用 LLM**（§6.4 说"后续看哪种更好"）：synthesizer 用 LLM 调用（reasoning_level="moderate"，AD-04），后续可根据效果切换为规则聚合（conviction 加权投票）。

### 决策 3：DA/synthesizer 不进 AGENT_REGISTRY，debate.py 内独立调用

**选择 B：DA/synthesizer 不进 `AGENT_REGISTRY`，`debate.py` 内独立调用。**

**理由**：
- 职责分割清晰：`AGENT_REGISTRY` 只放投资大师（R1/R2 并行调用的角色），DA/synthesizer 是 R3/R4 的独立角色，调用模式不同（各调 1 次，不并行 5 次）
- prompt 结构不同：投资大师用 Level 2 四层结构，DA/synthesizer 用职责导向结构（决策 2），混在同一个注册表里会让"填 agent 即激活"的语义变模糊
- debate.py 直接硬编码调用：R3 调 `call_da_agent(round1, round2)`，R4 调 `call_synthesizer(round1, round2, da_result)`，prompt 在 `prompt.py` 中用独立函数（`build_da_prompt` / `build_synthesizer_prompt`）

**实现**：
- `agents.py`：`AGENT_REGISTRY` 只注册 4 位投资大师（buffett / munger / duan / feng_liu）；张坤留给后续迭代
- `prompt.py`：新增 `build_da_prompt()` 和 `build_synthesizer_prompt()`（与 build_xxx_prompt 同文件，但命名区分）
- `debate.py`：新增 `_call_da(round1, round2, ticker, features)` 和 `_call_synthesizer(round1, round2, da_result, ticker, features)` 私有函数，内部调用 `call_llm`（不走 `call_agent`，因为 prompt 构建和输出解析逻辑不同）

### 决策 4：校准范围扩展

**按 §6.6 有完整案例的做断言，没有的标 TODO 不阻塞。**

| Agent | 校准用例 | 断言 | 状态 |
|-------|---------|------|------|
| 巴菲特 | 600519.SH 看多 / 600900.SH 看空 | signal == "bullish" / signal != "bullish" | 3a 已实现 |
| 段永平 | 600519.SH 看多（§6.6 案例） | signal == "bullish" | 3b 新增 |
| 芒格 | TODO（案例待补充） | — | 占位，不阻塞 |
| 冯柳 | TODO（案例待补充） | — | 占位，不阻塞 |
| DA | 无 signal 断言 | 输出 schema 合法 + `extra.blind_spots` 非空 | 3b 新增 |
| synthesizer | 无 signal 断言 | 输出 schema 合法 + `dissent_points` 非空 | 3b 新增 |

**校准实现**：
- `calibrate.py` 扩展 `CALIBRATION_CASES`，按 agent_id 组织用例（当前只有 buffett 的 2 个用例，3b 加 duan 的 1 个用例）
- DA/synthesizer 的校准跑 1 只真实票（600519.SH），只验输出结构合法 + 关键字段非空，不断言 signal 值
- 芒格/冯柳的校准用例在开发阶段从蒸馏库补充后实现，标 `# TODO: calibration case pending`
- 张坤留给后续迭代（蒸馏素材和校准用例均不足）

### 决策 5：L3→L4 接口（watchlist/{date}_council.json）

**接口文件**：`watchlist/{date}_council.json`，每个 council 子命令跑完单股即写（不引入批跑聚合）。

**文件结构**：

```json
{
  "ticker": "600519.SH",
  "date": "2026-06-30",
  "final_verdict": "bullish",
  "conviction": 75,
  "consensus_summary": "品牌定价权 + 简单商业模式，护城河深厚",
  "key_variables": [
    "ROE 是否持续 > 20%",
    "管理层是否出现减持行为"
  ],
  "dissent_points": [
    {
      "topic": "估值是否过高",
      "who_disagrees": "munger",
      "their_reason": "PE 30x 高于历史均值，安全边际不足"
    }
  ],
  "pending_verification": [
    "现金流/ROE 是否有背离",
    "管理层薪酬结构是否与股东利益一致"
  ],
  "debate_path": "debate/600519/2026-06-30.md"
}
```

**字段说明**：
- `ticker` / `date` / `final_verdict` / `conviction`：来自 `CouncilResult`（synthesizer 输出）
- `consensus_summary`：来自 `CouncilResult.consensus_summary`（synthesizer 输出）
- `key_variables`：从 R1/R2 所有 AgentOutput 的 `what_would_change_my_mind` 原始收集（与 `total-design.md` §6.4/§7 一致，`extract_key_variables` 函数），L4 监控盯这些变量做宽泛盯盘
- `dissent_points`：来自 `CouncilResult.dissent_points`（synthesizer 输出）
- `pending_verification`：来自 `CouncilResult.pending_verification`（synthesizer 结构化提炼的待验证事项），L4 做聚焦验证。与 `key_variables` 是**两个独立字段**：前者是原始收集，后者是结构化提炼
- `debate_path`：辩论记录 md 路径，L4 可回溯完整辩论过程

**与 L1/L2 watchlist 的关系**（AD-01）：
- L1/L2 产出 `watchlist/{date}_screener.json`（快筛管线）
- L3 产出 `watchlist/{date}_council.json`（深研管线）
- 两个文件独立，L4 同时消费两个文件（L4 change 的职责）

**产出时机**：council 子命令跑完单股即写（`run_debate` 返回 `CouncilResult` 后立即写），不引入批跑。批跑（消费 L2 ~20 只）留给 L4 触发。

### 决策 6：辩论增量验证（AD-09 质量门）

**质量门必须在 tasks 中有对应验证 task**（跑 1-2 只真实票，人工 + 自动检查）。

**机制门**（全天团 4 轮完整跑通）：
- R1×4 + R2×4 + R3×1 + R4×1 = 10 次 LLM 调用全部成功返回
- DA 输出 `extra.blind_spots` 非空且每项有 `title` / `detail` / `which_agents_missed_it`
- Synthesizer 输出 `dissent_points` 和 `pending_verification` 非空

**质量门**（辩论增量）：
- R1 core_thesis 差异：4 个 agent 的 `core_thesis` 两两相似度低（人工检查，不做 NLP 自动判分——MVP 阶段人工 1-2 只票可接受）
- R2 真实修订：至少 2 个 agent 在 R2 调整了 `conviction`（±5 以上）或修改了 `core_thesis`（与 R1 不完全相同）
- DA 盲点覆盖：`blind_spots` 中至少 1 个盲点的 `which_agents_missed_it` 包含 ≥3 个 agent（说明是真实共识盲区）

**若质量门不通过**：暂停加 agent，先调 prompt（AD-09 迭代原则）。具体调什么在 tasks 中定义回退路径。

**成本验证**：
- 实测全天团单股成本（10 次 LLM 调用：9 次重度推理 + 1 次中度推理），记录 token 消耗和费用，不做硬阈值约束
- 缓存命中验证：同股同日命中 `debate/{ticker}/{date}.md` 不重跑（3a `_check_cache` 复用）

### 决策 7：CouncilResult 结构重构

**问题**：当前 `CouncilResult.rounds: list[list[AgentOutput] | None]` 无法表达 R3（单 DA 输出）和 R4（SynthesizerOutput，不同类型）的语义。强行用 `rounds[2][0]` / `rounds[3][0]` 访问单对象既违反类型契约（`list[AgentOutput]` 里放 `SynthesizerOutput`），又导致缓存解析时类型混淆。

**选择**：抛弃 `rounds` 列表，改为显式命名字段。

```python
@dataclass
class CouncilResult:
    ticker: str
    round1: list[AgentOutput]           # R1 各 agent 独立判断
    round2: list[AgentOutput] | None    # R2 交叉质疑（单 agent=None）
    round3: AgentOutput | None          # R3 DA 输出（单对象，不是列表）
    round4: SynthesizerOutput | None    # R4 收敛共识（单对象，不是列表）
    final_verdict: str                  # 全天团=round4.final_signal，单 agent=round1[0].signal
    key_variables: list[str]            # 从 R1/R2 what_would_change_my_mind 提取（与 §6.4/§7 一致）
    consensus_summary: str | None = None           # 来自 round4
    dissent_points: list[dict] | None = None       # 来自 round4
    pending_verification: list[str] | None = None  # 来自 round4
    debate_path: str | None = None                 # 辩论记录 md 路径
```

**理由**：
- 类型安全：R3 是 `AgentOutput`（DA 也用 AgentOutput + extra.blind_spots），R4 是 `SynthesizerOutput`，类型各异，不再混用
- 语义清晰：`result.round4.final_signal` 比 `result.rounds[3][0].signal` 直观
- 扩展性：新增字段（`consensus_summary` / `dissent_points` / `pending_verification`）直接挂在顶层，`_write_council_output` 无需深挖 rounds
- 向后兼容：单 agent 场景下 `round2`/`round3`/`round4` 为 `None`，与 3a 行为一致

**缓存适配**：`_parse_debate_markdown` 按轮次 section 决定解析方式：
- `## Round 1/2` 内的 JSON 块 → `AgentOutput.from_dict`
- `## Round 3` 内的 JSON 块 → `AgentOutput.from_dict`（DA 输出也是 AgentOutput + extra.blind_spots）
- `## Round 4` 内的 JSON 块 → `SynthesizerOutput.from_dict`

**辩论记录写入适配**：`_append_round` 拆为三个函数：
- `_append_agent_round(path, round_num, agents: list[AgentOutput])` — R1/R2（并行输出列表）
- `_append_da_round(path, da: AgentOutput)` — R3（单对象）
- `_append_synthesizer_round(path, syn: SynthesizerOutput)` — R4（单对象，不同类型）

**CouncilResult.to_json 显式序列化**：不再用 `[a.to_dict() for a in r] for r in rounds` 遍历，改为显式序列化 `round1` / `round2` / `round3` / `round4` 四个字段。

## Risks / Trade-offs

**[风险] 4 个 agent 同质化 → 辩论增量 gate 不过**
→ 缓解：prompt 设计阶段确保每位大师的决策框架有本质差异（巴菲特=护城河、芒格=逆向+心理偏差、段永平=商业模式+本分、冯柳=弱势研究法+认知差）。若仍同质化，优先调 prompt 而非加 agent。张坤留给后续迭代（蒸馏素材和校准用例不足，同质化风险最高）。

**[风险] DA 输出泛泛之谈 → 盲点质量低**
→ 缓解：DA prompt 中强调"必须找具体漏洞"，`blind_spots` schema 要求每项有 `detail`（具体数据或事件）和 `which_agents_missed_it`（指向具体 agent）。若仍泛泛，在 prompt 中加 few-shot 示例。

**[风险] Synthesizer 输出与 R1 多数信号不一致 → final_verdict 逻辑混乱**
→ 缓解：synthesizer prompt 中明确"final_signal 基于加权多数（conviction 加权），分歧严重时降为 neutral"。若 LLM 不遵守，考虑切换为规则聚合（conviction 加权投票）。

**[风险] 全天团成本**
→ 缓解：全天团 10 次 LLM 调用（R1×4 + R2×4 + R3×1 + R4×1，其中 9 次重度推理 + 1 次中度推理），成本取决于模型定价和上下文长度。3b 实测记录 token 消耗和费用，不做硬阈值约束。缓存命中（同股同日不重跑）是主要的成本优化手段。

**[Trade-off] `extra: dict` 透传 vs 强校验**
→ 选择透传：LLM 输出格式不稳定，强校验会误杀。代价是 `extra` 中的字段不做类型/值校验，人类复盘时需自行判断字段质量。

**[Trade-off] Synthesizer 用 LLM vs 规则聚合**
→ MVP 先用 LLM（§6.4），代价是 R4 多一次 LLM 调用（~¥0.5）。若效果不好，切换为规则聚合（conviction 加权投票），不增加新依赖。

**[剩余风险] 芒格/冯柳校准用例缺失**
→ 不阻塞 3b，但 L4 启动前必须补充（L4 依赖校准通过的 agent 输出）。在 tasks 中标 TODO。张坤作为辩论增量验证通过后的首个扩展 agent，校准用例在后续迭代中补充。
