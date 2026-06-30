## 1. Schema 扩展（schema.py）

- [ ] 1.1 AgentOutput 新增 `extra: dict` 字段（默认空 dict），`to_dict` / `to_json` 自动包含
- [ ] 1.2 `from_dict` 修改：未定义字段收集进 `extra`（不再丢弃），基础 8 字段校验逻辑不变
- [ ] 1.3 新增 `SynthesizerOutput` dataclass（`final_signal` / `conviction` / `consensus_summary` / `dissent_points` / `pending_verification`），提供 `from_json` / `to_json` / `to_dict` 方法
- [ ] 1.4 `SynthesizerOutput` 校验：`final_signal` 枚举、`conviction` 0-100、`consensus_summary` 非空
- [ ] 1.5 单元测试：冯柳特有字段透传、DA `blind_spots` 透传、基础字段校验不变

## 2. Agent 注册表（agents.py）

- [ ] 2.1 `AGENT_REGISTRY` 追加 3 位大师：`munger` / `duan` / `feng_liu`，每条含 `name` 和 `prompt_builder` 路径
- [ ] 2.2 DA/synthesizer 不注册（设计决策 3），保持 `AGENT_REGISTRY` 只含投资大师
- [ ] 2.3 单元测试：注册表含 4 个 key，`get_prompt_builder("munger")` 返回函数

## 3. Prompt builders（prompt.py）

- [ ] 3.1 `build_munger_prompt()`：逆向 + 25 心理偏差 + 格栅思维（Level 2 四层结构，参考 total-design §6.2 芒格示例）
- [ ] 3.2 `build_duan_prompt()`：商业模式 + 管理层本分 + 能力圈（Level 2 四层结构，参考 total-design §6.2 段永平示例）
- [ ] 3.3 `build_feng_liu_prompt()`：弱者体系 + 三类认知差 + 赔率优先（Level 2 四层结构，参考 total-design §6.2 冯柳示例），末尾列出 5 个特有字段（`market_consensus` / `consensus_flaw` / `odds_assessment` / `is_reversible` / `catalyst`）
- [ ] 3.4 `build_da_prompt()`：职责导向，综合 R1+R2 找盲点，强调"具体漏洞"，列出 `extra.blind_spots` 结构（`title` / `detail` / `which_agents_missed_it`）
- [ ] 3.5 `build_synthesizer_prompt()`：职责导向，综合 R1+R2+DA 产出收敛结论，列出 `SynthesizerOutput` 字段（`final_signal` / `conviction` / `consensus_summary` / `dissent_points` / `pending_verification`）
- [ ] 3.6 单元测试：每位大师 prompt 含关键内容（芒格含"逆向思考"、冯柳含"弱者体系"等），DA/synthesizer prompt 含职责定义

## 4. Debate 编排器（debate.py）

- [ ] 4.1 新增 `_call_da(round1, round2, ticker, features)` 私有函数：构建 DA system prompt + user message（传入 R1+R2 的 AgentOutput JSON），调用 `call_llm(reasoning_level="heavy")`，解析为 AgentOutput（含 `extra.blind_spots`）
- [ ] 4.2 新增 `_call_synthesizer(round1, round2, da_result, ticker, features)` 私有函数：构建 synthesizer system prompt + user message（传入 R1+R2+R3 的输出），调用 `call_llm(reasoning_level="moderate")`，解析为 `SynthesizerOutput`
- [ ] 4.3 `run_debate` 修改：R3 从 `# TODO` 改为调用 `_call_da`（全天团下），R4 从 `# TODO` 改为调用 `_call_synthesizer`（全天团下）
- [ ] 4.4 `CouncilResult` 结构重构（schema.py）：将 `rounds: list` 改为显式字段 `round1: list[AgentOutput]` / `round2: list[AgentOutput] | None` / `round3: AgentOutput | None` / `round4: SynthesizerOutput | None`，新增 `consensus_summary` / `dissent_points` / `pending_verification` / `debate_path` 字段
- [ ] 4.5 `run_debate` 组装 `CouncilResult`：全天团下 `final_verdict` 取 `round4.final_signal`，`key_variables` 从 R1/R2 的 `what_would_change_my_mind` 提取（`extract_key_variables`），从 `round4` 提取 `consensus_summary` / `dissent_points` / `pending_verification`
- [ ] 4.6 辩论记录 md：R3 写入 DA 的 AgentOutput JSON（含 `extra.blind_spots`），R4 写入 `SynthesizerOutput` JSON；`_append_round` 拆为三个函数（`_append_agent_round` / `_append_da_round` / `_append_synthesizer_round`）
- [ ] 4.7 缓存适配：`_parse_debate_markdown` 按轮次 section 区分解析——R1/R2/R3 用 `AgentOutput.from_dict`，R4 用 `SynthesizerOutput.from_dict`；`CouncilResult.to_json` 显式序列化四个字段
- [ ] 4.8 单元测试：`_call_da` 返回 AgentOutput 含 `extra.blind_spots`，`_call_synthesizer` 返回 `SynthesizerOutput`，`final_verdict` 取 R4，缓存命中后 `round4` 正确恢复

## 5. L3→L4 接口（watchlist 产出）

- [ ] 5.1 新增 `_write_council_output(ticker, council_result)` 函数：从 `CouncilResult` 顶层字段提取（`final_verdict` / `conviction`（来自 round4.conviction） / `consensus_summary` / `key_variables` / `dissent_points` / `pending_verification` / `debate_path`），写入 `watchlist/{date}_council.json`；单 agent fallback 时 `consensus_summary`/`dissent_points`/`pending_verification` 为 None
- [ ] 5.2 `run_debate` 末尾调用 `_write_council_output`，单股跑完即写（不引入批跑）
- [ ] 5.3 `watchlist/` 目录不存在时自动创建（`mkdir(parents=True, exist_ok=True)`）
- [ ] 5.4 单元测试：接口文件字段完整，与 L1/L2 watchlist 独立（不覆盖 `{date}_screener.json`）

## 6. 校准扩展（calibrate.py）

- [ ] 6.1 扩展 `CALIBRATION_CASES`：按 agent_id 组织用例，新增段永平看多茅台（`600519.SH`，`signal == "bullish"`）
- [ ] 6.2 新增 DA 校准：跑 1 只真实票（600519.SH），验证输出 schema 合法 + `extra.blind_spots` 非空，不断言 signal 值
- [ ] 6.3 新增 synthesizer 校准：跑 1 只真实票（600519.SH），验证输出 schema 合法 + `dissent_points` 非空，不断言 signal 值
- [ ] 6.4 芒格/冯柳校准标 `# TODO: calibration case pending`，不阻塞测试
- [ ] 6.5 单元测试：段永平校准通过、DA/synthesizer 校准验证 schema

## 7. 辩论增量验证（AD-09 质量门）

- [ ] 7.1 机制门验证 task：跑 1 只真实票（600519.SH），确认 10 次 LLM 调用成功、DA `blind_spots` 非空且结构合法、synthesizer `dissent_points` / `pending_verification` 非空
- [ ] 7.2 质量门验证 task（人工检查）：跑 1-2 只真实票（600519.SH + 601318.SH），人工检查 R1 core_thesis 差异、R2 修订（至少 2 个 agent `conviction` ±5 或 `core_thesis` 修改）、DA 盲点覆盖（至少 1 个盲点 `which_agents_missed_it` 含 ≥3 个 agent）
- [ ] 7.3 成本验证 task：记录全天团单股 token 消耗和费用（10 次调用：9 重度 + 1 中度），不做硬阈值约束，作为后续优化的参考数据
- [ ] 7.4 质量门不通过回退路径：若 R1 core_thesis 同质化，优先调 prompt（增强差异点）；若 DA 泛泛，在 prompt 中加 few-shot 示例

## 8. 集成测试与验收

- [ ] 8.1 端到端测试：`council --ticker 600519.SH` 跑全天团，确认 4 轮完整、辩论记录 md 含 R1-R4、接口文件写入、缓存命中不重跑
- [ ] 8.2 缓存测试：同股同日重跑命中 `debate/{ticker}/{date}.md`，`--force` 跳过缓存重跑
- [ ] 8.3 校准测试：`council --calibrate` 跑巴菲特 + 段永平 + DA + synthesizer 校准，输出通过/失败
- [ ] 8.4 数据不足测试：`council --ticker 999999` 输出 "insufficient_data" + 缺失字段列表
