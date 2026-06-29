## 1. 项目骨架

- [ ] 1.1 建 `value-screener/council/` 目录结构（`__init__.py` / `agents.py` / `prompt.py` / `schema.py` / `debate.py` / `calibrate.py` / `llm.py` / `features.py`）
- [ ] 1.2 `council/agents.py` 定义 `AGENT_REGISTRY` 字典，3a 仅注册巴菲特（`{"buffett": {"name": "巴菲特", "prompt_builder": "council.prompt.build_buffett_prompt"}}`），debate.py 从此注册表读取 agent 列表（3b 填 agent 即激活）
- [ ] 1.3 `council/llm.py` 实现 `call_llm` 函数：httpx 直连 OpenAI 兼容 API，支持 `reasoning_level` 参数（"heavy" → LLM_MODEL_HEAVY / "moderate" → LLM_MODEL_MODERATE），超时 120s，重试 1 次，异常收窄（httpx.HTTPStatusError / httpx.TimeoutException）

## 2. Schema 定义

- [ ] 2.1 `council/schema.py` 定义 `AgentOutput` dataclass：signal（枚举 bullish/bearish/neutral/skip）/ conviction（0-100）/ core_thesis / key_metrics / risks / what_would_change_my_mind / out_of_circle / historical_parallel，含 `from_json` 和 `to_json` 方法
- [ ] 2.2 `council/schema.py` 定义 `CouncilResult` dataclass：rounds（列表）/ final_verdict / key_variables，含单 agent fallback 逻辑（final_verdict 取 rounds[0][0].signal）

## 3. 巴菲特 Agent Prompt

- [ ] 3.1 `council/prompt.py` 写巴菲特 system prompt（Level 2 四层结构：核心决策框架 / 案例锚定 / 表达风格 / 内在矛盾），参照 total-design.md §6.2 巴菲特示例（591-638 行）
- [ ] 3.2 `council/features.py` 封装 `assemble_council_features(ticker)`：import scout.input_assembly.assemble_snapshot，扩展 L3 特有逻辑（预留 history_years 参数）

## 4. 辩论编排器

- [ ] 4.1 `council/debate.py` 实现 `run_debate` 函数签名：接收 ticker / features / agents 列表，返回 CouncilResult
- [ ] 4.2 `council/debate.py` 实现 Round 1（各自表态）：并行调用所有 agent（asyncio.gather），每个 agent context 中 other_opinions 为空列表，reasoning_level="heavy"
- [ ] 4.3 `council/debate.py` 实现 Round 2（交叉质疑）：并行调用所有 agent，每个 agent context 中 other_opinions 包含 R1 中其他 agent 的 AgentOutput JSON（排除自己）；**单 agent 下跳过 LLM 调用**（CouncilResult.rounds[1] = None，不调 LLM 浪费 token）
- [ ] 4.3b `council/debate.py` 实现 R2 mock 注入机制（机制门验证用）：支持注入一份硬编码的 mock AgentOutput JSON（如"假想芒格"的 bullish 立场），验证巴菲特 agent 能消费他人结构化输出并产出修订立场。3a 专用钩子，3b 全天团时移除
- [ ] 4.4 `council/debate.py` 实现 Round 3（DA 挑刺）：单 agent 下跳过（da_result = None），全天团时调用 Devil's Advocate agent，context 含 R1+R2 全部讨论
- [ ] 4.5 `council/debate.py` 实现 Round 4（收敛共识）：单 agent 下跳过（consensus = None），全天团时调用 synthesizer agent，context 含 R1+R2+R3 全部讨论，reasoning_level="moderate"
- [ ] 4.6 `council/debate.py` 实现辩论记录持久化：每轮结束后立即 append 到 `debate/{ticker}/{YYYY-MM-DD}.md`，markdown 格式（## Round 1 · 各自表态 / ## Round 2 · 交叉质疑 / ## Round 3 · Devil's Advocate / ## Round 4 · 收敛共识），单 agent 下 R3/R4 节写"（单 agent 模式，跳过）"占位
- [ ] 4.7 `council/debate.py` 实现缓存命中逻辑：检查 `debate/{ticker}/{date}.md` 是否存在且内容完整（至少含 Round 1 节），命中则直接读取返回 CouncilResult，不重跑 LLM；`force=True` 参数跳过缓存

## 5. 校准测试

- [ ] 5.1 `council/calibrate.py` 实现 `run_calibration` 函数：定义巴菲特校准用例（600519.SH 看多 / 600900.SH 看空），调用 assemble_council_features 取真实特征 → 调用 run_debate → 断言立场一致性（看多案例 signal == "bullish" / 看空案例 signal != "bullish"）
- [ ] 5.2 运行 `council/calibrate.py`，验证校准测试通过（若失败则调 prompt 重跑，直到立场一致性过关）

## 6. CLI 集成

- [ ] 6.1 `cli.py` 新增 `council` 子命令：`--ticker <TICKER>`（6 位数字，自动补 .SH/.SZ 后缀）/ `--calibrate` / `--force`
- [ ] 6.2 端到端测试：`council --ticker 600519` 跑完整流程（assemble_snapshot → run_debate → 输出 AgentOutput JSON + 写入 debate/600519/{date}.md），验证输出格式正确
- [ ] 6.3 验证 AD-09 gate（三层 AND）：
  - **机制门**：debate.py 能跑完整流程，R1 独立跑通；R2 注入 mock AgentOutput JSON 验证 A2A 消费链路（agent 消费他人结构化输出并产出修订立场）；R3/R4 框架代码可执行不报错
  - **校准门**：校准测试（茅台看多 / 长江电力看空）立场一致性全部通过
  - **信息增量门**：单 agent 深研报告比 L2 Scout 有可判定增量——L3 产出的 `risks` 和 `what_would_change_my_mind` 两个字段均为非空，且 `core_thesis` 信息量明显多于 L2 的 `one_liner`
  - **moderate 推理等级声明**：`LLM_MODEL_MODERATE` 映射分支在 3a 已实现但 R4 跳过未被真实调用覆盖，留待 3b 验证

## 7. 文档与收尾

- [ ] 7.1 写 `council/README.md`：用法（`council --ticker` / `council --calibrate`）/ 配置（LLM_MODEL_HEAVY / LLM_MODEL_MODERATE 环境变量）/ gate 结果（机制门 + 校准门 + 信息增量门通过情况）
- [ ] 7.2 代码审查：检查 council/ 下所有文件是否符合 design.md 6 个决策（输入数据交接 / LLM client 选型 / 编排骨架 / 记录持久化 / 校准 / 成本约束），无遗漏后准备归档
