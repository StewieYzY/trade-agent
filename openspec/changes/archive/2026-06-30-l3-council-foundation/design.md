## Context

L1 量化筛选 + L2 LLM Scout 已完成，能产出 deep_dive 短名单（~20 只/批）。L3 天团深研是系统核心价值主张，但全天团（5+1 agent × 4 轮辩论）成本高（¥20-60/只）、架构复杂。AD-09 要求先用巴菲特单 agent 验证辩论编排架构可行性，通过 gate 后再扩全天团。

**当前状态**：
- L0 数据层（CacheManager）已就绪
- L2 特征组装（`scout/input_assembly.py::assemble_snapshot`）已实现，产出 ~200 tokens 特征快照
- L2 LLM 调用（`scout/batch.py::call_llm_snapshot`）用 httpx 直连 OpenAI 兼容 API，单一 env 三件套（LLM_API_KEY/LLM_API_BASE/LLM_MODEL）

**约束**：
- AD-01：L3 输入是单股特征数据，不假设来自 L1/L2（可从手动输入）
- AD-03：全天团成本 ¥20-60/只，3a 单 agent 应显著低于此
- AD-04：R1-3 重度推理 / R4 中度，不写死模型只标推理等级
- AD-05：不用 Multi-Agent 框架；debate.py 消息总线；A2A 传结构化 JSON；辩论记录 append-only 立即写入
- AD-07：不做格雷厄姆 agent
- AD-08：Level 2 四层 prompt，不引入 RAG
- AD-09：3a 只做巴菲特单 agent + 骨架；gate = 机制门 AND 校准门 AND 信息增量门

## Goals / Non-Goals

**Goals:**
- 验证辩论编排架构可行性：debate.py 消息总线 + 4 轮串行 + 信息可见性控制
- 实现巴菲特单 agent system prompt（Level 2 四层结构）
- 定义 AgentOutput JSON schema（§6.3）并验证 LLM 能稳定产出
- 实现辩论记录持久化（append-only，每轮立即写入）
- 通过 AD-09 gate（机制门 + 校准门 + 信息增量门，三层 AND）

**Non-Goals:**
- 不做全天团 agent（芒格/段永平/冯柳/张坤/质疑者 DA/synthesizer）——3b 范围
- 不做 HTML 报告渲染——3b 或独立 change
- 不做 RAG/知识库——AD-08 不做
- 不做格雷厄姆 agent——AD-07 不做
- 不做 L4 监控/watchlist、Streamlit 前端——后续 change
- 不产出 L3→L4 watchlist 接口文件（`watchlist/{date}_council.json`）——3b 产出

## Decisions

### 决策 1：输入数据交接（对应 AD-01）

**问题**：AD-01 约束"L3 输入是单股特征数据，不假设来自 L1/L2，可手动输入"。但 L2 已有 `scout/input_assembly.py::assemble_snapshot(ticker, cache_manager)` 实现了全维度特征组装。L3a 入口设计如何取 features？

**选项**：
- **A. 直接 import scout.input_assembly**：复用 `assemble_snapshot`，跨包依赖（council 依赖 scout）
- **B. 提升为共享模块**：把 `assemble_snapshot` 移到 `data/lib/features.py`，L2/L3 都 import
- **C. L3 独立实现特征组装**：重复造轮子，但完全解耦

**决策：A（直接 import scout.input_assembly）**

**理由**：
1. **L2 已稳定运行**：`assemble_snapshot` 经过 L2 实际验证，字段覆盖完整（ROE3y/净利率/负债率/商誉比/60日涨幅/换手率分位等），没必要重写
2. **耦合可控**：`scout/input_assembly.py` 是纯函数（输入 ticker + CacheManager，输出 features dict），无副作用，跨包 import 风险低
3. **L3 确实需要 L2 的特征深度**：L3 深研的输入本质上是"单股全维度特征"，和 L2 快照需求一致。如果 L3 未来需要更长上下文（如 5 年历史 vs L2 的 3 年），可在 `assemble_snapshot` 加参数控制，或 L3 内扩展（不破坏 L2）
4. **不硬绑 L2 输出文件**：CLI `council --ticker XXX` 直接调 `assemble_snapshot(ticker)` 取实时特征，不读 L2 的 `watchlist/{date}_scout.json`。`--ticker` 可手动指定任意票，符合 AD-01"不假设来自 L1/L2"

**影响**：
- L2 无改动（`scout/input_assembly.py` 保持原样）
- L3 新增 `council/features.py`，内部 `from scout.input_assembly import assemble_snapshot`，封装 L3 特有逻辑（如未来扩展字段）

---

### 决策 2：LLM client 选型

**问题**：L2 的 LLM 调用写在 `scout/batch.py::call_llm_snapshot` 内，httpx 直连 OpenAI 兼容 API，单一 env 三件套（LLM_API_KEY/LLM_API_BASE/LLM_MODEL），无共享 client 抽象。L3 用重度模型（R1-3）/中度（R4），与 L2 轻量模型 model 名不同。如何组织 LLM 调用？

**选项**：
- **A. 抽取共享 LLM client**：建 `data/lib/llm_client.py`，按推理等级（轻量/重度/中度）映射不同 model env（LLM_MODEL_LIGHT/LLM_MODEL_HEAVY/LLM_MODEL_MODERATE），L2/L3/L4 共用。需改动已归档的 L2 `batch.py`
- **B. L3 独立实现 LLM 调用**：在 `council/` 内独立实现（复用 batch.py 的 httpx/env 模式），独立配置重度 model env（LLM_MODEL_HEAVY + LLM_MODEL_MODERATE），不动 L2

**决策：B（L3 独立实现 LLM 调用）**

**理由**：
1. **L2 已归档**：`l2-llm-scout-agent` 已移至 `archive/2026-06-29`，改动归档代码违反"归档即冻结"原则
2. **回归风险**：L2 是已验证的稳定模块，改其 LLM 调用层（即使抽共享 client）需重新跑回归测试，ROI 不划算
3. **L3 需求简单**：L3 只需"按推理等级映射 model"，~50 行代码，不值得为此引入共享抽象
4. **未来重构时机**：等 L4 实现时再评估是否抽共享 client（届时 L2/L3/L4 都跑过，模式更清晰）

**实现**：
- `council/llm.py`：封装 `call_agent(system_prompt, context, reasoning_level)` 函数
- 环境变量：复用 `LLM_API_KEY` / `LLM_API_BASE`，新增 `LLM_MODEL_HEAVY`（重度，R1-3）/ `LLM_MODEL_MODERATE`（中度，R4）
- 推理等级映射：`reasoning_level="heavy"` → `LLM_MODEL_HEAVY`；`"moderate"` → `LLM_MODEL_MODERATE`
- 异常处理：复用 batch.py 的收窄模式（`httpx.HTTPStatusError` / `httpx.TimeoutException`），超时 120s（重度模型响应慢）

---

### 决策 3：辩论编排骨架（单 agent 场景下的 R2-4 处理）

**问题**：3a 只有巴菲特单 agent，但 debate.py 需预留 4 轮框架。单 agent 下 R2（交叉质疑）无他人论点、R3（DA 挑刺）无其他 agent、R4（收敛共识）无多 agent 可综合。如何处理？

**决策：框架代码完整实现，单 agent 下 R2 跳过 LLM 调用，R3/R4 跳过**

**实现细节**：
- **R1（各自表态）**：单 agent 独立跑，产出 `AgentOutput` JSON（正常流程）
- **R2（交叉质疑）**：框架代码写好（`other_opinions = [r for r in round1 if r.name != name]`），但**单 agent 下跳过 LLM 调用**（不调 LLM，CouncilResult.rounds[1] = None），理由：单 agent + 空 other_opinions = 无输入可质疑，调一次浪费 token
- **R3（DA 挑刺）**：框架代码写好（`full_discussion = round1 + round2`），但单 agent 下无 DA agent 实例，跳过此轮（`da_result = None`）
- **R4（收敛共识）**：框架代码写好（`full_discussion = round1 + round2 + [da_result]`），但单 agent 下无 synthesizer 实例，跳过此轮（`consensus = None`）

**Agent 注册机制**：
- 建 `council/agents.py`，定义 `AGENT_REGISTRY` 字典，3a 仅含巴菲特，3b 追加芒格/段永平/冯柳/张坤/DA/synthesizer
- debate.py 从 `AGENT_REGISTRY` 读 agent 列表，不硬编码 agent 名称
- 3b 只需在 `agents.py` 注册新 agent，无需改编排逻辑（"填 agent 即激活"）

**3b 激活方式**：在 `council/agents.py` 注册全天团 agent，debate.py 自动按 agent 列表跑 R2-4，无需改编排逻辑

**验证**：
- 机制门要求"R2-4 框架代码可执行"——单 agent 下 R2 跳过 LLM 调用、R3/R4 跳过，不报错即通过
- **机制门补充**：R2 注入一份 mock AgentOutput JSON（硬编码"假想芒格"的 bullish 立场），验证巴菲特 agent 能消费他人结构化输出并产出修订立场（A2A 消费链路被真实执行）
- 辩论记录 markdown 中 R2/R3/R4 节写"（单 agent 模式，跳过）"占位
- **moderate 推理等级声明**：`LLM_MODEL_MODERATE` 和 moderate 映射分支在 3a 已实现但未被真实调用覆盖（R4 跳过），留待 3b R4 收敛共识验证

---

### 决策 4：辩论记录持久化

**实现**：
- 路径：`debate/{ticker}/{date}.md`（`{date}` 格式 `YYYY-MM-DD`）
- 结构：按 §6.4.1 的 md 模板（Round 1 各自表态 / Round 2 交叉 / Round 3 DA / Round 4 收敛）
- 写入策略：append-only，每轮结束立即写入（不等 4 轮全完成）
- 并发安全：单股单进程写，无并发冲突

**缓存命中**：
- 同股同日内重跑：默认命中 `debate/{ticker}/{date}.md`，不重跑 LLM（节省成本）
- `--force` flag：跳过缓存，强制重跑
- 跨日：`date` 不同，自然重跑

---

### 决策 5：校准测试（§6.6）

**用例**：
- 巴菲特看多：`600519.SH`（贵州茅台）——品牌定价权 + 简单商业模式
- 巴菲特看空：`600900.SH`（长江电力）——重资产公用事业，巴菲特不偏好

**断言**：
- 看多案例：`signal == "bullish"`
- 看空案例：`signal != "bullish"`（允许 `bearish` / `neutral` / `skip`）

**实现**：`council/calibrate.py`，CLI `council --calibrate` 跑校准用例，输出通过/失败

---

### 决策 6：成本约束

**估算**（按重度推理模型 Opus 级定价）：

| 轮次 | 单次调用成本 | 说明 |
|------|-------------|------|
| R1（重度） | ¥0.675 | 输入 ~2K tokens（¥0.30）+ 输出 ~500 tokens（¥0.375） |
| R2（重度） | ¥0.825 | 输入 ~3K tokens（含 4 份他人 JSON，¥0.45）+ 输出 ~500 tokens（¥0.375） |
| R3（重度） | ¥1.35 | 输入 ~5K tokens（累积全部讨论，¥0.75）+ 输出 ~800 tokens（¥0.60） |
| R4（中度） | ¥0.16 | 输入 ~5K tokens（¥0.10）+ 输出 ~600 tokens（¥0.06） |

**3a 单股单 agent 深研**：
- R1（¥0.675）+ R2 跳过（¥0）+ R3 跳过（¥0）+ R4 跳过（¥0）= **¥0.675/只**
- 显著低于全天团 ¥9/只（见下），符合 AD-03"3a 单 agent 应显著低于全天团"

**gate 验证开销**（一次性，不计入常规 `council --ticker` 成本）：
- mock 注入验证（task 4.3b）：额外 1 次 R2 级 LLM 调用 ≈ ¥0.825
- 校准测试（task 5.2）：2 次 R1 调用 ≈ ¥1.35
- 合计 gate 验证 ≈ ¥2.175（一次性，验证通过后可删除 mock 钩子）

**全天团（3b）**：
- 实际调用次数：R1×5 + R2×5 + R3×1 + R4×1 = **12 次**（非 5×4=20）
- R1×5（¥3.375）+ R2×5（¥4.125）+ R3×1（¥1.35）+ R4×1（¥0.16）= **~¥9/只**
- 低于 AD-03 的 ¥20-60 上限（AD-03 按更保守估计，实测后调整）

**缓存命中**：同股同日内重跑命中 `debate/{ticker}/{date}.md`，不重跑 LLM（成本 ¥0）

## Risks / Trade-offs

**风险 1：L2 特征组装不满足 L3 深度需求**
- 场景：L3 深研可能需要更长上下文（如 5 年历史 vs L2 的 3 年 ROE）
- 缓解：`assemble_snapshot` 加参数控制（如 `history_years=5`），或 L3 内扩展（`council/features.py` 封装）
- 触发条件：巴菲特 prompt 实测后反馈"数据不够深"

**风险 2：单 agent 下信息增量门不通过**
- 场景：巴菲特深研报告比 L2 Scout 无显著信息增量（`core_thesis`/`risks`/`what_would_change_my_mind` 比 L2 的 `one_liner` 更浅）
- 缓解：调 prompt（Level 2 四层结构细化）、调特征输入（加字段）、调推理等级（换更强模型）
- 触发条件：gate 信息增量门失败，暂停扩 agent

**风险 3：校准测试立场不一致**
- 场景：巴菲特对茅台输出 `signal != "bullish"`（应看多却看空/中性）
- 缓解：调 prompt（案例锚定强化）、调特征输入（确保茅台数据完整）
- 触发条件：gate 校准门失败，暂停扩 agent

**风险 4：重度模型响应慢/超时**
- 场景：重度推理模型（如 o1）响应 >120s，超时失败
- 缓解：超时设 120s（L2 是 60s），失败重试 1 次（退避 2s），仍失败则标记 error 不阻塞
- 触发条件：实测后调整超时阈值

**风险 5：辩论记录 markdown 格式不稳定**
- 场景：append-only 写入时格式错乱（如 Round 2 节插入 Round 1 中间）
- 缓解：每轮结束立即写入，按轮次顺序 append，不并发写同一文件
- 触发条件：实测后调整写入策略
