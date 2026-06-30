## Why

L3 天团深研是系统的核心价值主张——通过多投资大师视角的辩论产出高质量研判。但全天团（5+1 agent × 4 轮辩论）成本高（¥20-60/只），且架构复杂。AD-09 要求先验证架构可行性：用巴菲特单 agent 跑通辩论编排骨架，证明 debate.py 消息总线、AgentOutput schema、校准流程可工作，通过 gate 后再扩全天团。降低风险，避免一次性投入过大却因架构问题返工。

## What Changes

- 新增 `council/` 包：巴菲特单 agent system prompt（Level 2 四层结构）、AgentOutput JSON schema、辩论编排骨架（4 轮串行、信息可见性控制）、校准测试（真实案例立场一致性）
- 新增 `council/llm.py`：LLM 调用层，按推理等级映射模型（重度/中度），复用 httpx
- CLI 集成：`council --ticker 600519` 子命令，输入单股 → 巴菲特深研 → 输出 AgentOutput JSON + 辩论记录 markdown
- 辩论记录持久化：`debate/{ticker}/{date}.md`，append-only，每轮结束立即写入
- 不做：全天团 agent（3b）、HTML 报告渲染、RAG/知识库、格雷厄姆 agent（AD-07）、L4 监控/watchlist、Streamlit 前端

## Capabilities

### New Capabilities
- `council-debate`: AgentOutput JSON schema（signal/conviction/core_thesis/key_metrics/risks/what_would_change_my_mind/out_of_circle/historical_parallel）+ 辩论编排契约（4 轮串行、信息可见性控制、A2A 传结构化 JSON）+ 校准契约（真实案例立场一致性断言）

### Modified Capabilities

## Impact

- **代码**：新增 `value-screener/council/` 包（7 个文件含 `__init__.py`），CLI 新增 `council` 子命令
- **依赖**：复用 `httpx~=0.27.0`（不引入新依赖）
- **数据**：复用 L0 CacheManager + L2 `scout/input_assembly.py` 的特征组装（或直接读 L2 deep_dive 候选）
- **配置**：新增环境变量 `LLM_MODEL_HEAVY` / `LLM_MODEL_MODERATE`（推理等级映射，AD-04）
- **产出**：`debate/{ticker}/{date}.md`（辩论记录 markdown）
- **不动**：L1 量化筛选、L2 LLM Scout、L4 监控（后续 change）
