## Context

L3 天团辩论骨架已落地（`council/`：4 agent 巴菲特/芒格/段永平/冯柳 + DA + Synthesizer，固定 4 轮 R1隔离/R2可见R1/R3 DA仲裁/R4收敛），P0 串台+同质化 bug 已在 f1-deviation-fix 修完（`financials_floor` 硬门槛 + §6 质量门反向特征校验 + 环形引用检测）。f1 堵的是「数据没进去」的漏洞；本 change 处理「数据进去之后，辩论本身如何不退化、如何省成本、如何保留不确定性」。

借鉴源：`design/kimi-worldcup-learnings.md` 从 Kimi 2026 世界杯 Multi-Agent 报告提炼两套机制。**关键差异**：Kimi 是持续运行的概率预测系统（39 天、300 agent、蒙特卡洛、输出胜率要校准），trade-agent 是请求式的单只股票质性研判（一次调用、5+1 agent、输出好不好+为什么、不输出概率）。conviction 是主观 0-100 分不是概率估计——这让 Brier/Platt 那套概率校准概念上水土不服，需降级为「标注未校准」。

约束继承：
- **AD-05**：不用 Multi-Agent 框架，`debate.py` 是唯一消息总线，4 轮 = `asyncio.gather` + 信息可见性控制
- **AD-09**：辩论产生信息增量是核心假设，f1 已修到「能跑」，本 change 让它「跑得有价值」
- **deviation-analysis §2.5**：L3 schema（final_verdict+conviction+consensus_summary+dissent_points+key_variables+pending_verification）语义正确不改——本 change 的分歧报告字段是**增量叠加**，不替换现有字段

## Goals / Non-Goals

**Goals:**
- 低分歧时跳 R2/R3 省 heavy-model token（分歧度作为元信号）
- R2 新证据 soft 信号（防辩论退化为复读，原「强制新证据」已降级，见 D2 scope 调整；f1 没覆盖的 Kimi MVP② 缺口）
- DA 从「找盲点」升级为「仲裁」——做事实回查而非纯文字评估
- R4 输出结构化分歧报告，保留不确定性而非强行抹平
- L2/L3 降级分场景：L2 优雅降级（继续跑整批），L3 fail-fast（单只深研诚实）
- structural 不确定性标注「不可解决」省死辩论

**Non-Goals:**
- 不做 Brier Score 实际计算（无样本，Phase 3；conviction 非概率概念别扭）——只标注 `calibration_status: "uncalibrated"`
- 不做 L4 分歧追踪（依赖 L3 稳定产出 + 持续数据流，当前全市场没跑过、watchlist 6/7 全 null）——仅在 schema 预留 `divergence_*` 字段供 L4 后续消费
- 不引入 Multi-Agent 框架（AD-05）
- 不替换 L3 现有 schema 字段（§2.5 已拍板），分歧报告是叠加层
- 不调 f1 已修的 `financials_floor` 硬门槛（L3 入口 fail-fast 触发器保持不变）
- 不做张坤（第 5 agent）

## Decisions

### D1：分歧度量化——以 signal 一致性为主、conviction std 为辅

**问题**：Kimi 用「概率估计差异的百分点数」量化分歧度，但 trade-agent 的 conviction 是主观 0-100 分、从未校准（不同 agent 对「75 分」的主观锚定不同），单独用 conviction std 不可靠。

**决策**：分歧度量化函数 `compute_divergence(round1) -> {signal_consensus, conviction_std, level}`：
- `signal_consensus` = 多数 signal 占比（如 4 个 bullish 1 个 neutral → 0.8）——**主信号**
- `conviction_std` = 全体 agent conviction 的标准差——**辅助信号**（仅当 signal 一致时用来区分「都看多但确信度差异大」）。agent 数 <2 时返回 0（spec review #4 修订：不硬编码 agent 数，当前 4 位投资大师，未来张坤加入变 5）
- `level` 映射（保守默认值，**待 MVP 实测校准**）：
  - `low`：signal_consensus ≥ 0.8 且 conviction_std < 10 → 跳 R2/R3，直接 R4
  - `medium`：signal_consensus ≥ 0.6 或 conviction_std 10-20 → 正常跑 R2/R3
  - `high`：signal 不一致（无多数派，如 2:2 或 2:1:1）→ 正常跑 R2/R3，R4 输出 `divergence_level: "high"` + confidence_adjustment 负向调整
  - `extreme`：signal 完全分散（1:1:1:1:1 类似）→ 跳 R2/R3，直接 R4 输出 `final_signal: "neutral"`（无法收敛到多数派，最诚实的投资动作信号是「无法形成方向判断」）+ `divergence_level: "extreme"` + 非空 `key_disagreements`（分歧信息靠 divergence_level/key_disagreements 表达，不污染 final_signal 枚举——见 spec review #1 调整，守 f1 N1「不改 L3 schema 语义」）

**为何不照搬 Kimi 的 15%/30%/50%**：那是世界杯概率场景调的阈值，trade-agent 是质性 signal（枚举 4 值不是连续概率），百分点数口径不适用。先用保守默认（signal_consensus 0.8/0.6 为主），标注待校准，MVP 实测后调。

**备选**：纯 conviction std 分流——否决，因 conviction 未校准；纯 signal 多数决——可作主信号但丢了「都看多但分歧大」的 nuance，故 conviction std 作辅助。

### D2：新证据字段——结构化信号（soft），非硬约束（f3 落地后升为 hard gate）

> **scope 调整（2026-07-10）**：原 D2 设计为「R2 强制引用 R1 未讨论维度，否则声明 evidence_exhausted」。但偏移分析实证（Explore 验证）显示 L3 输入仅 21 个纯量化字段，R1 已引用信息量最高的几个（PE/ROE/F-score/涨跌幅），R2 要引「新维度」只能凑低信息量字段（换手率量比/60日高点距离）或像 600009 DA 那样从训练知识里编——两者都比不引更差。**根因不在 agent 不想引新证据，在数据里就没有新维度可引。** 此为信息基底问题（属 f3-l3-research-dossier 范畴），本 change 不解决。故 D2 从硬约束降为结构化信号，避免在 21 字段底座上触发「编造-校验-拦截」死循环、evidence_exhausted 成为常态而非例外。字段保留是为 f3 铺路：f3 引入定性维度后，agent R2 确有新东西可引，`new_evidence` 字段即报告「引用了哪个新维度」的载体，届时 soft warning 升回 hard gate。

**决策**：
- `AgentOutput` 加两个选填字段（向后兼容，老输出无此字段不报错）——**字段保留，仅约束降级**：
  - `new_evidence: list[str]`——本轮引用的数据点（R1 时为空或全部，R2 时鼓励引用 R1 未充分覆盖的维度）
  - `evidence_exhausted: bool`——是否已穷尽所有可用数据（默认 false）
- R2 prompt 从「**必须**引用至少一个 R1 未讨论维度，否则声明 evidence_exhausted」改为「**鼓励**性引导」：
  > 「如果 R1 未充分覆盖某些数据维度，请在 `new_evidence` 中列出。如果所有相关数据已在 R1 被引用，请声明 `evidence_exhausted: true`。」
- `run_debate` 在 R2 后聚合逻辑（task 3.3/3.4）**保留不变**：≥3 个 agent 标 `evidence_exhausted=true` 仍跳 R3——这是合理的穷尽退出路径，不依赖硬约束。
- **质量门降级**（task 5.1/5.2/5.7 改动）：`verify_r2_new_evidence` 从「`new_evidence` 空 且 `evidence_exhausted=false` → 拦截（hard gate）」改为「soft warning——仅记录日志，不阻断流程」。对 `new_evidence` 中数字的反向特征校验（复用 `verify_r1_feature_grounding`）保留，命中伪造数字仍可降级为 warning 内的标记，但不拦截产出（防在 21 字段底座上误杀 R2 全员穷尽声明的诚实退出）。

**为何不全删 D2**：`new_evidence`/`evidence_exhausted` 字段是 f3 的 enabling carrier——f3 给 L3 补定性维度后，R2 的 new_evidence 才有真东西可填，届时把 soft warning 改回 hard gate 是一行改动。现在删字段，f3 还得加回来，且 schema 重构成本高。

**为何不维持原硬约束**：design 自列风险「强制新证据逼模型编造」在 21 字段底座上必然触发——R2 凑数（低信息字段）或编造（训练知识）二选一，质量门拦截编造但产出 evidence_exhausted 全员命中，R3 被跳光，辩论退化。降为 soft 是把该风险从「设计缺陷」降为「已知局限 + f3 修复路径」。

### D3：DA 升级为仲裁——事实回查而非 LLM 评 LLM 文字

**问题**：Kimi 让风险感知 Agent 兼任仲裁，评估双方证据质量。直接照搬到 trade-agent 的风险：DA 若只看 agent 输出文字评估证据质量，是 LLM 评 LLM 的文字游戏——agent 说「ROE 32%」DA 也只能基于这句话评估，无法判真假。

**决策**：DA 已在 user message 注入 `features`（`_call_da` 现有实现，传 `json.dumps(features)`）。改造：
- `build_da_prompt` 加职责：「你不仅找盲点，还要**评估各 agent 引用数据点的真实性**——对每个 agent 的 key_metrics，回查 features 实际值，标注是否准确（如 agent 说"ROE 32%"但 features.roe_3y=18.2，标记为 `inaccurate`）」
- DA 输出 `extra` 加 `evidence_quality_assessment: {agent_id: "accurate"/"moderate"/"weak"/"inaccurate"}` + `recommendation: "defer_to_<agent_id>_consensus"` 或 `"no_clear_winner"`
- R4 synthesizer prompt 改为「基于 DA 的 `evidence_quality_assessment` 和 `recommendation` 做最终判断，而非自行重新综合所有观点」

**为何这是改造不是照搬**：Kimi 仲裁基于概率输出可量化比较；trade-agent 是质性论点，必须靠 features 回查做事实层仲裁，否则文字游戏。

### D4：分歧报告——增量叠加，不替换现有 schema

**问题**：Kimi 辩论产出是「分歧报告」而非「共识结论」。deviation-analysis §2.5 已拍板 L3 schema 不改。冲突。

**决策**：`SynthesizerOutput` 加 6 个**选填**字段（向后兼容，老 watchlist 无此字段不崩）：
- `divergence_level: str`（low/medium/high/extreme，来自 D1）
- `divergence_score: float`（signal_consensus 或综合分）
- `key_disagreements: list[dict]`（[{topic, bull_case, bear_case, strength}]——结构化分歧点，比现有 `dissent_points` 更细）
- `confidence_adjustment: float`（-0.2 表示 conviction 下调 20%，来自分级响应）
- `divergence_source: dict`（{parameter, model, structural}，粗标，来自 D7）
- `calibration_status: str`（固定 `"uncalibrated"`，来自 D8）

`final_verdict`/`consensus_summary`/`dissent_points` 保留不变。watchlist 输出（`_write_council_output`）透传新字段。

**为何不替换**：§2.5 拍板「好不好+为什么+什么条件下改变」语义正确，final_verdict 是用户决策的核心抓手。分歧报告是**补充不确定性信息**，不是替代判断。

### D5：降级分场景——L2 优雅降级 vs L3 fail-fast

**问题**：Kimi 主张「系统永远有输出，精度随数据质量变」（优雅降级）。f1-deviation-fix 给 L3 选了 fail-fast（`financials_floor` 硬门槛，数据不足直接报错）。600900 复读茅台就是「数据缺失还硬出结论」的后果——证明 L3 fail-fast 更诚实。但 L2 是 200 只快筛批处理，单只 fail 会中断整批，优雅降级更合理。冲突。

**决策**：分场景：
- **L2（scout-agent）优雅降级**：`financials_floor` 不齐但 `basic` 命中时，从 fail-fast 改为 `confidence_cap=50` + 强制 `verdict="watch"` + 标注 `degraded=true`，继续跑完整批不中断。注：L2 现有 guard 是 `critical_fields=["name","industry","market_cap"]` + 缺失率>50%，本 change 补「financials 不齐但 basic 齐」这一中间态的降级路径（非 fail-fast 非 full）。
- **L3（council）保持 fail-fast**：f1 的 `financials_floor` 入口门槛不变。本 change 补 L3 **运行时**降级：agent error rate `failed_count / active_agent_count ≥ 0.4` 时（spec review #4 修订：动态比，当前 4 agent ≥2 失败即 50%≥40% 触发；未来张坤加入变 5 agent，逻辑不变），跳 R2/R3 只做 R1+R4 + `confidence_cap=40` + 标注 `council_degraded`。区别于入口 fail-fast（数据根本进不来）vs 运行时降级（数据进来了但 agent 跑崩了）。

**为何不照搬 Kimi「永远有输出」**：L3 单只深研若数据不足硬出结论，就是 600900 悲剧重演。L3 的诚实比「有输出」重要。L2 批处理则不同，单只降级比整批 fail 体验好。

**备选**：L2 也 fail-fast——否决，200 只里几只数据不全就整批崩，不可接受。

### D6：L3 运行时降级——agent error rate 触发

**问题**：L3 入口 fail-fast 只防「数据不足」。若数据够但 LLM 调用大面积失败（限流/超时），当前会逐个抛异常中断。

**决策**：`run_debate` 用 `asyncio.gather(*, return_exceptions=True)` 收集 R1 结果，统计 error rate = `failed_count / active_agent_count`（**spec review #4 修订：动态比，不硬编码 agent 数**）：
- error rate < 0.4：正常继续（个别失败容忍，R2 时 other_opinions 跳过失败 agent）
- error rate ≥ 0.4：触发运行时降级——跳 R2/R3，用幸存 R1 做 R4（synthesizer 收到不完整 R1），`confidence_cap=40`，watchlist 标注 `council_degraded: true` + `degraded_reason: "high_agent_error_rate"`

**为何 0.4**：当前 4 位投资大师，≥2 失败（50%）即说明非偶发（限流/模型故障），继续辩论意义不大；用动态比 `failed_count / active_agent_count` 而非硬编码「5 agent ≥2」，因未来张坤加入变 5 agent 时逻辑无需改（4 agent 阈值=≥2，5 agent 阈值=≥2）。保守阈值，待实测。

### D7：structural 不确定性标注——只标 structural，粗标

**问题**：Kimi 三层不确定性（parameter/model/structural）分解的价值在防优化陷阱——若把 structural（不可消除）误当 model（可改善），会死调参数。但 parameter vs model 的细分让 LLM 自评不靠谱。

**决策**：分歧报告 `divergence_source` 只做粗标：
- `structural: "low"/"medium"/"high"`——存在不可预测外部因素（政策/黑天鹅/管理层个人行为）时标 high，**high 时 R4 直接标「不可解决」，不再强求收敛**
- `parameter`/`model`：粗标或省略（LLM 自评不靠谱，不强求）

**为何不全做**：parameter（数据不完整）vs model（哲学差异）的区分对 LLM 是元认知负担，输出不稳定。structural 标注有价值（直接决定是否终止辩论），其余可省。

### D8：Brier 校准——只标注不做计算

**问题**：Kimi 主张「校准 > 准确率」，conviction 80 分的票后来涨没涨要回溯。但当前无推荐历史样本，且 conviction 是主观分非概率，Brier Score 概念上别扭（Brier 评概率估计，conviction 是确信度非概率）。

**决策**：watchlist 输出加 `calibration_status: "uncalibrated"` 固定标注（诚实声明 conviction 未校准）。实际 Brier 回溯是 Phase 3 事（积累样本后），本 change 不做计算。

**为何不硬上 Brier**：无样本 + 概念别扭 + ROI 低。标注未校准是零成本的诚实，足够。

### D9：L4 分歧追踪——暂缓，仅预留 schema

**问题**：Kimi 主张分歧需时间收敛，新数据到来后重跑 L3 对比分歧度。但当前全市场没跑过、watchlist 6/7 全 null，L4 分歧追踪是空中楼阁。

**决策**：本 change 不实现 L4 分歧追踪逻辑。仅在 `SynthesizerOutput`/watchlist 预留 `divergence_*` 字段，供 L4 后续消费（L4 何时做独立工作项，依赖全市场跑通 + watchlist 稳定）。

## Risks / Trade-offs

- **[分流阈值误判]** → 该辩论的分歧被跳过（低分歧误跳 R2/R3）。缓解：默认值保守（signal_consensus ≥0.8 才跳，宁可多跑一轮）+ 标注「待校准」+ §6 质量门监控跳轮比例，实测后调。
- **[新证据字段在 21 字段底座上无物可引（已知局限，f3 范畴）]** → L3 输入仅 21 个纯量化字段（实证见 2026-07-10 Explore），R2 引「新维度」只能凑低信息字段或编造。本 change 的缓解是把 D2 从 hard gate 降为 soft warning（详见 D2 scope 调整），**不彻底解决**——根治需 f3-l3-research-dossier 把 L3 输入升级为含定性维度的结构化研究档案。降级后的残留风险：soft warning 无强制力，R2 可能仍复读 R1（无新证据也无穷尽声明）；缓解靠 D3（DA 事实回查）+ f2 的 R2 可见 R1 的辩论可见性约束兜底，f3 落地后升 hard gate。
- **[DA 仲裁退化成文字游戏]** → DA 只评估 agent 文字不真回查 features。缓解：D3 强制 DA prompt 要求事实回查 + §6 `verify_da_fact_check` 拦截 DA 引用了 features 中不存在的数据点；首次落地人工验证 DA 输出确含 features 比对。**已知局限**：features 仅 21 量化字段，DA 想回查的定性维度（如 600009 的资本开支/扣点率）features 里没有，DA 事实回查只能覆盖 agent 引用的量化指标真假，覆盖不到 DA/agent 从训练知识调取的定性事实——这部分根治需 f3。
- **[SynthesizerOutput 加字段 LLM 不稳定输出]** → R4 整体校验失败。缓解：6 个新字段全选填 + 缺失时 `calibration_status` 等降级为默认值 + 不进 `__post_init__` 必填校验，避免破坏现有 final_verdict 链路（与 f1 N1「不改 L3 schema」原则调和）。
- **[L2 降级 vs L3 fail-fast 边界模糊]** → L2 guard 与 L3 guard 共用 `input_assembly`，降级逻辑互相污染。缓解：D5 明确 L2 降级是 `scout/batch.py` 层逻辑（confidence_cap+watch），L3 fail-fast 是 `council/debate.py` 层逻辑（入口门槛不变），不在同一函数混用。
- **[conviction std 不可靠]** → 不同 agent 对「75 分」主观锚定不同，std 失真。缓解：D1 以 signal_consensus 为主，conviction std 仅辅助（仅 signal 一致时用）。

## Migration Plan

无破坏性迁移——所有 schema 字段选填向后兼容，老 watchlist/debate 文件可正常解析（缺失新字段走默认值）。`_parse_debate_markdown` 解析老 debate 文件时新字段缺失返回 None，不报错。

部署顺序：schema 字段 → 分歧度量化函数（纯 Python）→ debate.py 分流 → R2 prompt + DA prompt + Synthesizer prompt → 质量门校验函数 → L2 降级。每步独立可测，回滚按反序。

## Open Questions

- 分流阈值（D1 的 0.8/0.6/10/20）需 MVP 实测校准——本 change 用保守默认值落地，实测后是否需独立 change 调参？
- L3 运行时降级（D6）的 40% error rate 阈值是否过严/过松？需真实限流场景验证。
- DA 事实回查（D3）要求 DA 对每个 agent 的每条 key_metrics 回查，token 成本上升——是否只抽查关键 agent 或关键数据点？
