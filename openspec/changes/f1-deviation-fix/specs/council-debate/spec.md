## ADDED Requirements

### Requirement: R1 features 充分性门
Round 1 调用 LLM 前，编排器 SHALL 校验 `features` 数据充分性。除现有 `critical_fields=["name","market_cap"]` 和整体缺失率 >50% 阈值外，SHALL 新增**财务字段最低组合**校验——L3 深研的命脉是财务维度，不是 name/market_cap。当财务字段组合不满足时，SHALL fail-fast，SHALL NOT 拿"有名字有市值但无财务数据"的 dict 喂给 LLM。

> 背景：deviation-analysis §1.2/1.3 实证发现 600519/600900 在 features 缺失时模型靠 system prompt 案例锚定编造。代码核查（`scout/input_assembly.py:338-354`）发现现有 guard 的实际漏洞：`critical_fields` 只有 name/market_cap，整体缺失率 >50% 才拦——**当 basic 维缓存命中（name/market_cap 有值）但 financials 维度过期/缺失时，缺失率可能才 ~40%，guard 放行**，模型拿到无财务数据的 dict 靠"可口可乐→茅台""ROE 32%"案例编造。本 requirement 在 guard 层补财务字段硬门槛，精确捕获这条幻觉触发路径。

**校验规则**（在 `assemble_council_features` / `assemble_snapshot` guard 层落地）：
- `critical_fields = ["name", "market_cap"]`（保留，basic 维硬门槛）
- `financials_floor = ["pe_ttm", "roe_3y", "net_margin"]`（新增，财务维硬门槛——L3 深研最低三件套，任一缺失则 features 不足以支撑质性判断）
- 触发 `insufficient_data` 的条件（满足任一即 fail-fast）：
  1. `missing_critical` 非空（name 或 market_cap 缺失）
  2. `financials_floor` 中**任一**字段为 None（财务三件套不齐）
  3. 整体 `missing_ratio > 0.5`（保留原阈值作为兜底）

#### Scenario: features 为空字典时 R1 fail-fast
- **WHEN** `assemble_council_features(ticker)` 返回空 dict 或仅含占位字段
- **THEN** R1 SHALL 抛出 `ValueError("insufficient_data")` 并列出缺失字段，不调用任何 LLM

#### Scenario: basic 命中但 financials 全空时 R1 fail-fast（核心漏洞修复）
- **WHEN** `assemble_council_features(ticker)` 返回 `{"name": "贵州茅台", "market_cap": 1.8e12, "pe_ttm": None, "roe_3y": None, "net_margin": None, ...}`（basic 维命中、financials 维过期/缺失）
- **THEN** R1 SHALL 抛出 `ValueError("insufficient_data")` 并列出 `missing_fields=["pe_ttm","roe_3y","net_margin"]`，不调用 LLM——这是 600519 幻觉的真正触发路径，原 guard 因缺失率 <50% 放行，新 guard 因 financials_floor 不齐而拦截

#### Scenario: features 返回 insufficient_data 错误时 R1 fail-fast
- **WHEN** `assemble_council_features(ticker)` 返回 `{"error": "insufficient_data", "missing_fields": [...]}`
- **THEN** `debate.py::run_debate` 已有的 `if "error" in features: raise ValueError` SHALL 消费新校验返回的 error，错误信息含缺失字段列表，提示用户先跑 `batch` 采集

#### Scenario: features 充分时 R1 正常调用
- **WHEN** `assemble_council_features(ticker)` 返回包含 name/market_cap 且 financials_floor（pe_ttm/roe_3y/net_margin）全非空的 dict
- **THEN** R1 SHALL 将 features JSON 注入 user message 并调用 LLM，产出引用真实数据点的 AgentOutput

#### Scenario: 600009 真实产出 vs 600519 幻觉产出的区分
- **WHEN** 对比 600009（features 充分，core_thesis 引用"PE_TTM 26.42、ROE 趋势上升"）与 600519（features 缺失，core_thesis 编"ROE 32%、可口可乐"）的 R1 输出
- **THEN** features 充分性门 SHALL 让前者通过、后者在 R1 入口即 fail-fast，杜绝幻觉产出进入后续轮次

## MODIFIED Requirements

### Requirement: LLM 调用按推理等级映射模型
LLM 调用层 SHALL 按推理等级（`heavy` / `moderate`）映射到不同模型环境变量，并 SHALL 采集每次调用的 token usage 返回给调用方，支撑 AD-03 成本实测。

- `heavy`（R1-R3）→ `LLM_MODEL_HEAVY` 环境变量
- `moderate`（R4）→ `LLM_MODEL_MODERATE` 环境变量
- 复用 `LLM_API_KEY` / `LLM_API_BASE`（与 L2 共享）
- **新增**：`call_llm` SHALL 返回 `(content: str, usage: dict)` 或等价结构，`usage` 含 `prompt_tokens` / `completion_tokens` / `total_tokens`，从 API 响应的 `usage` 字段提取（当前实现丢弃该字段，只返回 JSON 字符串）

不写死模型种类（AD-04），只标推理等级。

#### Scenario: 重度推理调用
- **WHEN** 辩论 Round 1 调用 LLM
- **THEN** SHALL 使用 `LLM_MODEL_HEAVY` 环境变量指定的模型

#### Scenario: 中度推理调用
- **WHEN** 辩论 Round 4 调用 LLM
- **THEN** SHALL 使用 `LLM_MODEL_MODERATE` 环境变量指定的模型

#### Scenario: 环境变量缺失
- **WHEN** `LLM_MODEL_HEAVY` 或 `LLM_MODEL_MODERATE` 未设置
- **THEN** SHALL 抛出 ValueError，fail-fast 不静默降级

#### Scenario: token usage 采集（新增）
- **WHEN** `call_llm` 完成一次 LLM 调用
- **THEN** SHALL 返回 content 与 usage（含 prompt_tokens/completion_tokens/total_tokens），L2 scout 与 L3 council 的调用方 SHALL 累加 usage 以实测 AD-03 成本（≈¥0.01/只），不再仅记录调用次数

#### Scenario: 调用点适配（新增）
- **WHEN** `call_llm` 签名从返回 `str` 改为返回 `(str, usage)`
- **THEN** L3 `debate.py::call_agent` / `_call_da` / `_call_synthesizer` 与 L2 `scout/batch.py` 的所有调用点 SHALL 适配新签名（解构 content 与 usage），不破坏现有 `AgentOutput.from_json` 解析逻辑
