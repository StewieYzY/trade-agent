## Why

f3e 已完成有界 compatibility probe，但当前 provider/model 链路无法稳定返回可比较响应，不能继续等待 Council 根因实验。G2 需要一个可独立验证、可 fail closed 的 fallback foundation：在同一经过 preflight 的 dossier 上运行一个 strong agent，用独立事实检查器拦截污染，再输出带质量状态的最小 synthesis envelope。

## What Changes

- 新增 strong single-agent fallback 运行入口，默认使用 `LLM_MODEL_HEAVY`，允许显式 model override。
- 复用 Council dossier preflight，但不复用 Council cache、debate markdown 或 watchlist success path。
- 增加 R1 hard quality breaker：schema failure、transport failure、凭空数字或显性串台不得生成 clean result。
- 增加独立 deterministic fact-check report，记录 grounding/crosstalk 检查结果和问题。
- 增加不调用额外 LLM 的 deterministic synthesizer fallback：只复制已验证 agent 字段，不补事实；失败时输出 `signal=skip`、`conviction=0` 和待验证状态。
- 产出 run-scoped fallback artifact；不写成功 Council cache，不放行 G2 capability 或 G3 runtime。

## Capabilities

### New Capabilities

- `strong-single-agent-fallback`: 定义 G2 fallback foundation 的输入、单 agent 调用、质量断路器、事实检查、deterministic synthesis 和审计产物。

### Modified Capabilities

<!-- 无现有生产 Council requirement 变化；本 change 新增独立 fallback 运行路径。 -->

## Impact

- 受影响代码：`value-screener/council/` 新增 fallback module 及对应 tests。
- 复用现有 `AgentOutput`、dossier preflight、`call_llm`、grounding/crosstalk 校验。
- 不修改现有 `run_debate`、Council cache、watchlist 写入、G3 HoldingContract 或最终 InvestmentThesis interface。
- 不引入新依赖。
