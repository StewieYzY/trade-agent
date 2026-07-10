## Why

`design/kimi-worldcup-learnings.md` 从 Kimi 2026 世界杯 Multi-Agent 报告提炼了两套机制——**辩论协议**（分歧度量化、分级响应、强制新证据、第三方仲裁、分歧报告、时间收敛）和**校准降级**（校准 > 准确率、可量化降级条件、三层不确定性分解、优雅降级）。f1-deviation-fix 已修掉 L3 的 P0 根因（数据层 guard 放行致幻觉），但那堵的是「数据没进去」的漏洞；**数据进去之后，辩论本身仍可能退化**——固定 4 轮无脑跑完（低分歧也跑 R2/R3 浪费 heavy-model token）、R2 易复读 R1、DA 挑刺但不做事实校验、R4 强行收敛抹平分歧。借鉴 Kimi 的协议设计能同时压成本（低分歧跳轮）、提质量（新证据结构化信号防退化、分歧报告保留不确定性）、护诚实（structural 不可解决标出来而非死辩论）。这是 AD-09「辩论产生信息增量」假设从「修了能跑」到「跑得有价值」的演进。

> **scope 调整（2026-07-10）**：实证（Explore 验证）显示 L3 输入仅 21 个纯量化字段，R2 无新维度可引——「强制新证据」硬约束会触发「编造-校验-拦截」死循环。故 D2 从 hard gate 降为 soft warning（字段保留作 f3-l3-research-dossier 的 enabling carrier，f3 补定性维度后升回 hard gate）。信息基底不足属 f3 范畴，本 change 不解决。详见 design.md D2。

## What Changes

**完全借鉴（纯赚、契合串行架构、解决真问题）**：

1. **分歧度作为元信号**（辩论要点 1）：R1 后纯 Python 后处理算 `signal 一致性比例 + conviction 标准差`，分流决定后续路径——低分歧跳 R2/R3 直接 R4 收敛，省 ~60% heavy-model token。**以 signal 一致性为主、conviction std 为辅**（conviction 是主观 0-100 分且从未校准，单独用不可靠）。
2. **新证据字段（soft signal，非 hard gate）**（辩论要点 3，**scope 调整 2026-07-10**）：`AgentOutput` schema 加 `new_evidence`（本轮引用数据点列表）+ `evidence_exhausted`（是否已穷尽可用数据）字段；R2 prompt 加**鼓励性**引导「如 R1 未充分覆盖某些维度请列 new_evidence，否则声明 evidence_exhausted」（非「必须」硬约束）；≥3 agent 标 `evidence_exhausted=true` 时跳 R3。质量门 `verify_r2_new_evidence` 降为 soft warning（不阻断）。**为何降级**：L3 输入仅 21 纯量化字段，R2 无新维度可引，硬约束只触发编造或凑数；字段保留为 f3（补定性维度后）的 enabling carrier，届时升回 hard gate。直击辩论退化为复读——这是 f1 没覆盖的 Kimi MVP② 缺口。

**部分借鉴（方向对，需改造 / 有前置依赖 / 与已有决策冲突）**：

3. **分级响应 Level 映射**（辩论要点 2）：分流框架借鉴，但 Kimi 的 15%/30%/50% 阈值是世界杯概率场景调的，**先按保守默认值落地，标注「待 MVP 实测校准」**；Level 4「暂停预测等人工审查」在 trade-agent 无意义（本就辅助决策、不自动下单，人工是默认态不是降级态）→ 降级为「输出 `final_signal: "neutral"` + `divergence_level: "extreme"` + 分歧报告 + 标注需关注」（**不引入 `conflict` 枚举值**，守 f1 N1「不改 L3 schema 语义」——分歧信息靠 divergence_level 表达，见 spec review #1 调整）。
4. **DA 升级为仲裁**（辩论要点 4）：DA 职责从「找盲点」扩展为「评估各 agent 证据质量 + 给出倾向性裁决」。**关键改造**：DA 的 user message 已注入 `features`（`_call_da` 现有实现），但 DA prompt 未要求做事实回查——现在要求 DA 对 agent 引用的数据点回查 features 真假（agent 说"ROE 32%"，DA 能比对 features 实际值），不只 LLM 评 LLM 文字。R4 synthesizer 基于 DA 仲裁报告而非自行综合。
5. **产出改分歧报告**（辩论要点 5）：**增量添加** `divergence_level` / `divergence_score` / `key_disagreements` / `confidence_adjustment` 字段到 `SynthesizerOutput` + watchlist 输出，**不替换** `final_verdict`/`consensus_summary`（与 deviation-analysis §2.5 已拍板的「schema 语义不改」调和——分歧报告是叠加层，不是替换层）。
6. **降级触发器 + 降级行为**（校准要点 2、4）：**分场景**——L2（200 只快筛）走优雅降级（数据不足时 `confidence_cap=50` + 强制 `watch`，继续跑不 fail 整批）；L3（单只深研）走 fail-fast 更诚实（600900 复读茅台就是数据缺失还硬出结论的后果，f1 的 `financials_floor` 已是 L3 fail-fast 触发器，本 change 补 L3 运行时降级：agent error rate ≥40% 时跳 R2/R3 只做 R1+R4 + confidence_cap=40）。**不照搬 Kimi「系统永远有输出」**。
7. **三层不确定性分解**（校准要点 3）：**只做 structural 标注**——L3 分歧报告标注 `divergence_source`（parameter/model/structural），structural 高（政策/黑天鹅/不可预测外部因素）时直接标「不可解决」省得死辩论；parameter vs model 的细分让 LLM 自评不靠谱，粗标或省略。
8. **Brier Score 回溯校准**（校准要点 1）：**只建认知不做计算**——watchlist 输出加 `calibration_status: "uncalibrated"` 标注（conviction 主观分从未校准），实际 Brier 回溯是 Phase 3 事（无推荐历史样本，且 conviction 是主观分非概率，概念上别扭）。
9. **L4 分歧追踪**（辩论要点 6）：**暂缓**——依赖 L3 稳定产出 + 持续数据更新流，当前全市场没跑过、watchlist 6/7 全 null，做分歧追踪是空中楼阁。本 change 仅在 schema 预留 `divergence_*` 字段供 L4 后续消费。

## Capabilities

### New Capabilities
<!-- 本 change 不引入新 capability，全部是对已有 capability的 delta -->
（无）

### Modified Capabilities
- `council-debate`: R1 后新增分歧度量化分流（低分歧跳 R2/R3 省 token）+ R2 新证据 soft 信号（`new_evidence`/`evidence_exhausted` 字段 + 鼓励性引导，非 hard gate）+ AgentOutput 加字段 + SynthesizerOutput 加分歧报告增量字段（`divergence_level`/`divergence_score`/`key_disagreements`/`confidence_adjustment`/`divergence_source`/`calibration_status`）+ 运行时降级（agent error rate 触发跳轮 + confidence_cap）
- `da-and-synthesizer`: DA 职责从「找盲点」升级为「仲裁」——DA prompt 加事实回查约束（对 agent 引用数据点比对 features 真假）+ 输出加 `evidence_quality_assessment`；R4 synthesizer 基于 DA 仲裁报告而非自行综合
- `debate-quality-gate`: 质量门新增「R2 新证据校验（soft warning，不阻断，f3 后升 hard）」（`new_evidence` 非空或显式 `evidence_exhausted` → 通过；两者皆无或疑似编造 → 记 warning 不拦截）+ 「分歧报告完整性校验」（`divergence_level`/`key_disagreements` 非空）+ 「DA 仲裁事实回查校验」（DA 的 `evidence_quality_assessment` 引用的数据点能在 features 找到来源）
- `scout-agent`: L2 新增优雅降级模式——数据不足时（financials_floor 不齐但 basic 命中）从 fail-fast 改为 `confidence_cap=50` + 强制 `watch` + 标注 `degraded`，继续跑完整批不中断（区别于 L3 的 fail-fast）

## Impact

**受影响代码**：
- `value-screener/council/schema.py` — `AgentOutput` 加 `new_evidence`/`evidence_exhausted` 字段（选填，向后兼容）；`SynthesizerOutput` 加 6 个分歧报告增量字段（选填，向后兼容）
- `value-screener/council/debate.py` — 新增分歧度量化函数（纯 Python，R1 后调）；`run_debate` 加分流逻辑（低分歧跳 R2/R3）；R2 路径 evidence_exhausted 聚合跳 R3；运行时降级（agent error rate）
- `value-screener/council/prompt.py` — R2 prompt 加**鼓励性**新证据引导（非硬约束）；`build_da_prompt` 加事实回查 + 仲裁职责；`build_synthesizer_prompt` 加分歧报告输出要求
- `value-screener/council/verify_quality_gate.py` — 新增 `verify_r2_new_evidence` + `verify_divergence_report` + `verify_da_fact_check` 校验函数
- `value-screener/council/agents.py` — 无改动（DA/synthesizer 不进 registry，不变）
- `value-screener/scout/input_assembly.py` / `scout/batch.py` — L2 降级模式（confidence_cap=50 + watch，区别于 L3 fail-fast）

**依赖**：无新依赖（纯 Python 后处理 + prompt 调整 + schema 字段，复用现有 `call_llm`/`asyncio.gather`）

**风险**：
- 分流阈值（低分歧跳轮的 signal 一致性/conviction std 边界）需 MVP 实测校准，默认值偏保守（宁可多跑一轮不可误跳）——阈值不合理会让该辩论的分歧被跳过，误标值标「待校准」
- DA 仲裁若只做文字评估不真回查 features，会退化成 LLM 评 LLM 文字游戏——靠 §6 质量门 `verify_da_fact_check` 拦截，但首次落地需真实验证 DA 确实读了 features
- `SynthesizerOutput` 加字段若 LLM 不稳定输出，需全部选填 + 缺失时降级标注，避免 R4 整体校验失败（与 f1 N1「不改 L3 schema」原则调和：增量选填不破坏现有 final_verdict 链路）
- L2 降级 vs L3 fail-fast 的分场景决策若实现时边界模糊（如 L2 guard 与 L3 guard 共用 input_assembly），需明确 L2 降级是 scout 层逻辑、L3 fail-fast 是 council 层逻辑，不互相污染
