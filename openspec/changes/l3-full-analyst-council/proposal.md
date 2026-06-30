## Why

L3a（council-foundation）已完成并归档。AD-09 三门验证结果：机制门 ✓（debate.py 编排 + AgentOutput schema + A2A 消费链路可运行）、校准门 ✓（巴菲特茅台/长江电力通过）、信息增量门 ✓（AgentOutput 的 core_thesis/risks/what_would_change_my_mind 比 L2 one_liner 有显著深度）。3b 在此基础上扩展全天团（4 投资大师 + DA + synthesizer），激活 4 轮完整辩论，交付 L3→L4 接口，是 L4 监控层启动的前置条件。

## What Changes

- 注册芒格/段永平/冯柳 3 位投资大师到 `AGENT_REGISTRY`（巴菲特已有），加上 DA（devils advocate）和 synthesizer（共 6 个 agent_id）；张坤留给后续迭代（蒸馏素材和校准用例不足，AD-09 同质化风险最高）
- 新增 4 个 prompt builder：`build_munger_prompt` / `build_duan_prompt` / `build_feng_liu_prompt`（Level 2 四层结构）+ DA/synthesizer 各自的 prompt（非 Level 2 结构，职责不同）
- `debate.py` R3 补 DA 调用（当前 `# TODO` + `None`），R4 补 synthesizer 调用，`final_verdict` 改为取 R4 synthesizer 收敛结论（当前硬编码 `= round1[0].signal`，全天团后逻辑错误）
- `schema.py` 扩展支持 agent 特有字段（冯柳：`market_consensus` / `consensus_flaw` / `odds_assessment` / `is_reversible` / `catalyst`；DA 盲点清单）；`CouncilResult` 重构为显式命名字段（`round1`/`round2`/`round3`/`round4`），新增 `consensus_summary`/`dissent_points`/`pending_verification`
- `calibrate.py` 校准范围扩展：段永平用茅台案例（§6.6），芒格/冯柳标 TODO（案例待补充），DA/synthesizer 只验证 schema 合法 + 产出非空
- 新增 `watchlist/{date}_council.json` 产出（L3→L4 接口），`key_variables` 从 R1/R2 的 `what_would_change_my_mind` 原始收集，`pending_verification` 来自 synthesizer 结构化提炼，两者并列
- 全天团 4 轮辩论完整跑通（R1×4 + R2×4 + R3×1 + R4×1 = 10 次 LLM 调用）
- 辩论增量验证：4 个 agent R1 `core_thesis` 有实质差异，R2 有真实修订，DA 盲点未被共识覆盖

## Capabilities

### New Capabilities
- `agent-prompt-builders`: 4 位投资大师的 Level 2 四层结构 prompt（段永平/芒格/冯柳/巴菲特增强）+ DA/synthesizer 的独立 prompt 设计
- `schema-extensions`: AgentOutput 支持 agent 特有字段（extra: dict 透传），冯柳/DA 各自特有字段，LLM 输出特有字段进入辩论记录 + A2A 透传；CouncilResult 重构为显式命名字段
- `da-and-synthesizer`: DA（devils advocate）综合 R1+R2 找盲点和共识漏洞，synthesizer 综合 R1+R2+DA 产出收敛结论 + 保留分歧 + 待验证事项（LLM 实现，§6.4 说"MVP 先用 LLM"）
- `council-output-interface`: L3→L4 接口文件 `watchlist/{date}_council.json`，包含 `ticker` / `final_verdict` / `conviction` / `key_variables` / `pending_verification` / `dissent_points` / `debate_path`
- `debate-quality-gate`: 辩论增量验证机制——R1 core_thesis 差异检查、R2 修订检查、DA 盲点覆盖检查，质量门不通过则暂停加 agent 先调 prompt

### Modified Capabilities
- `debate-orchestration`（3a 已有）: R3/R4 从 TODO 补成可运行调用，`final_verdict` 从 `round1[0].signal` 改为 R4 synthesizer 共识结论，全天团缓存复用 3a `_check_cache`
- `calibration-framework`（3a 已有）: 校准范围从巴菲特扩展到段永平（完整案例）+ 芒格/冯柳（TODO 占位），DA/synthesizer 校准只验 schema 合法 + 产出非空

## Impact

- **代码**：`value-screener/council/{agents,prompt,schema,debate,calibrate}.py` 全部修改，`__main__.py` 可能需适配 `final_verdict` 新逻辑
- **API/依赖**：无新依赖（复用 httpx）
- **成本**：单股 10 次 LLM 调用（R1×4 + R2×4 + R3×1 + R4×1，其中 9 次重度推理 + 1 次中度推理），实测记录 token 消耗和费用，不做硬阈值约束；缓存命中（同股同日不重跑）是主要成本优化手段
- **下游系统**：L4 监控层依赖 `watchlist/{date}_council.json` 接口文件，但 L4 消费逻辑不在本 change scope
- **Scope 边界**：不做 L4 监控/watchlist diff、不做 Streamlit 前端、不做 RAG、不做格雷厄姆 agent（AD-07）、不引入 Multi-Agent 框架（AD-05）
