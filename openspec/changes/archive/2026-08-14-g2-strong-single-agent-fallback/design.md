## Context

f3c/f3e 已完成输入 containment、严格 schema harness 和 bounded compatibility probe，但 live provider 链路无法稳定产生可比较的多 agent 响应。继续追加 Council A/B 会把 provider availability 与 Council 信息增量混在一起。G2 umbrella 已明确：Council 未通过相对价值 Gate 时，默认产品形态回退为“强单 Agent + 独立 DA/事实检查器 + Synthesizer”。

当前 `run_debate(agents=["buffett"])` 虽能减少 agent 数量，但仍会进入 Council 的 debate/watchlist 写入和缓存路径，不能作为不污染生产成功缓存的 fallback foundation。

## Goals / Non-Goals

**Goals:**

- 新增一个 run-scoped、可测试的 strong single-agent fallback 入口。
- 在任何 LLM 调用前复用现有 dossier preflight。
- 只调用一个 strong agent，并记录 model/ticker/run/features provenance。
- 用 deterministic grounding 和 circular-reference 检查作为独立 fact checker。
- 将 schema、transport、fact-check failure 统一为不可发布的 `blocked` 状态。
- 用 deterministic synthesis envelope 保留已验证内容；失败时不复制方向性判断。
- 明确 fallback artifact 不进入 Council cache、watchlist 或 G2 capability success。

**Non-Goals:**

- 不修改 `run_debate` 的 4 轮编排。
- 不新增第二次 LLM synthesizer 调用。
- 不定义最终 `InvestmentThesis` contract；该 contract 由独立 child change 负责。
- 不通过 mock 或 fixture 宣称 strong model live capability。
- 不放行 G2/G3，不执行大规模 A/B 或用户盲评。

## Decisions

### D1：独立 fallback module，不包裹 `run_debate`

新增 `council/fallback.py`，直接复用 `_prepare_council_input` 和 `_build_user_message`，但自行调用 `call_llm` 并只写 fallback artifact。这样可以保证 preflight 一致，同时避免 Council cache/watchlist 的副作用。

备选方案是调用 `run_debate(agents=["buffett"])` 后再清理文件；该方案存在中途崩溃留下 clean-looking artifact 的风险，因此不采用。

### D2：R1 hard quality breaker

单 agent 输出先通过 `AgentOutput.from_json`，再由 deterministic fact checker 执行：

- `verify_r1_feature_grounding`：key metric 数字必须来自当前 dossier；
- `detect_circular_reference`：R1 不得引用其他 agent。

任一失败都不允许保留 agent 的 bullish/bearish/neutral 作为 fallback final signal；synthesis 改为 `skip`、conviction `0`，并保留问题。

### D3：synthesis 只复制已验证事实

`build_fallback_synthesis` 不调用 LLM，不创造新数字，不改写 agent 的事实字段。质量通过时复制 agent signal/conviction/core thesis/key metrics/risks/what-would-change；质量失败时只输出安全 skip envelope，并把 fact-check issues 放入 pending verification。

### D4：artifact 与状态

每次运行写入 `fallback_runs/<run_id>/result.json` 和 `manifest.json`，包含 canonical ticker、agent、model、features hash、prompt/user hash、usage、quality status、fact-check report 和 synthesis。失败 artifact 可以保留用于诊断，但不得写入 Council success cache 或 watchlist。

### D5：强模型和成本边界

默认模型来自 `LLM_MODEL_HEAVY`；显式 override 只允许 heavy/moderate reasoning level。一次 fallback run 最多一次 agent LLM call；deterministic synthesis 不消费额外 token。该 foundation 不是 G2 capability pass 证据。

## Risks / Trade-offs

- [Provider 仍不可用] → 返回 blocked artifact，不伪造 thesis；保留 transport error。
- [grounding 检查存在容差误判] → 记录原始 AgentOutput 和逐项 issues，后续可独立校准，不降级为静默 warning。
- [单 agent 缺少多视角] → 明确标注 fallback path，Council A/B 若未来重开仍需独立 Gate。
- [fallback envelope 不是最终 Thesis] → 不接入 watchlist/G3；另开 InvestmentThesis interface child。

## Migration Plan

1. 先写 RED tests：preflight zero side effect、single strong call、hard breaker、fact-check、synthesis 和 artifact isolation。
2. 实现 `council/fallback.py` 最小路径。
3. 运行 focused/full pytest、strict OpenSpec validation 和 diff check。
4. 先用 fixture/mock 验证机制，不把它写成 live capability pass。
5. 若后续获得独立 live 授权，再执行单 ticker、单 agent、单 call 的 fallback smoke run；结果仍需 G2 Gate。

## Open Questions

- 默认 strong agent 暂定 `buffett`，后续应由 G2 baseline child 冻结，而不是暗含为最终产品选择。
- 独立 fact checker 是否需要第二个 LLM/外部 source，留给后续 evidence-quality child；本 foundation 只实现 deterministic checker。
