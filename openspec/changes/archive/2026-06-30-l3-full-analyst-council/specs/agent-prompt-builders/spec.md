## ADDED Requirements

### Requirement: 投资大师 Level 2 四层 prompt 结构
系统 SHALL 为每位投资大师提供独立的 prompt builder 函数，prompt SHALL 严格遵循 Level 2 四层结构（AD-08）：

1. **核心决策框架**：该投资人的判断逻辑
2. **案例锚定**：实际买过/不会买的股票
3. **表达风格**：语言特征、常用句式
4. **内在矛盾**：保持诚实，不脸谱化

4 位大师 prompt builder：
- `build_buffett_prompt`（3a 已实现）
- `build_munger_prompt`（逆向 + 25 心理偏差 + 格栅思维）
- `build_duan_prompt`（商业模式 + 管理层本分 + 能力圈）
- `build_feng_liu_prompt`（弱者体系 + 三类认知差 + 赔率优先）

张坤留给后续迭代（蒸馏素材和校准用例不足，AD-09 同质化风险最高）。

每位大师的 prompt SHALL 体现本质差异（不是风格微调），差异点必须可被辩论增量 gate 检验（AD-09）。

#### Scenario: 芒格 prompt 含逆向思考
- **WHEN** `build_munger_prompt()` 被调用
- **THEN** 返回的 system prompt SHALL 包含"逆向思考"（先想怎么会失败）和"25 个心理偏差检测"相关内容

#### Scenario: 冯柳 prompt 含弱势研究法
- **WHEN** `build_feng_liu_prompt()` 被调用
- **THEN** 返回的 system prompt SHALL 包含"弱者体系"、"市场可能错的三类认知差"、"赔率优先于胜率"相关内容

#### Scenario: 段永平 prompt 含本分概念
- **WHEN** `build_duan_prompt()` 被调用
- **THEN** 返回的 system prompt SHALL 包含"商业模式优先"、"管理层本分度"、"能力圈"相关内容

#### Scenario: 每位大师 prompt 含 JSON 输出格式约束
- **WHEN** 任何 `build_*_prompt()` 函数被调用
- **THEN** 返回的 prompt SHALL 在末尾包含 JSON 输出格式说明，列出 AgentOutput 基础 8 字段（冯柳额外列出 5 个特有字段）

### Requirement: 投资大师注册到 AGENT_REGISTRY
4 位投资大师 SHALL 全部注册到 `council/agents.py` 的 `AGENT_REGISTRY`：
- `buffett` → 巴菲特（3a 已注册）
- `munger` → 芒格
- `duan` → 段永平
- `feng_liu` → 冯柳

每条注册项 SHALL 包含 `name`（显示名）和 `prompt_builder`（模块路径.函数名）。

#### Scenario: 注册表含 4 位大师
- **WHEN** `council/agents.py` 被加载
- **THEN** `AGENT_REGISTRY` SHALL 包含 4 个 key：`buffett` / `munger` / `duan` / `feng_liu`

#### Scenario: 通过 prompt_builder 路径加载函数
- **WHEN** `get_prompt_builder("munger")` 被调用
- **THEN** SHALL 动态导入 `council.prompt` 模块并返回 `build_munger_prompt` 函数

### Requirement: 大师 prompt 不引 RAG
所有投资大师 prompt SHALL NOT 包含知识库 RAG 检索逻辑（AD-08），所有判断 SHALL 基于 Level 2 四层结构 + 传入的特征数据。

#### Scenario: Prompt 无外部检索依赖
- **WHEN** 任何 `build_*_prompt()` 被调用
- **THEN** 返回的 prompt SHALL 是自包含字符串，不引用外部知识库路径或 RAG API
