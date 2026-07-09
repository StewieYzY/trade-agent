# Tasks

> 依赖：proposal.md / design.md / specs/（4 个 delta：council-debate / da-and-synthesizer / debate-quality-gate / scout-agent）
> 实施顺序：schema 字段（§1，纯 dataclass 改动，零 LLM）→ 分歧度量化（§2，纯 Python 函数）→ debate.py 分流+降级（§3）→ prompt 改造（§4，R2/DA/Synthesizer）→ 质量门校验函数（§5）→ L2 降级（§6）→ 真实验证（§7）
> 每个 task 标注验证方式（Verify），遵循 TDD：先写测试，再改代码

## 1. Schema 字段新增（D4，纯 dataclass，零 LLM 调用）

- [ ] 1.1 先写测试 `tests/test_council_schema.py`（扩展现有文件）：断言 `AgentOutput.from_json` 能解析含 `new_evidence`/`evidence_exhausted` 的 JSON，且缺失时填默认（`[]`/`false`）不报错。**Verify**：测试 fail（字段未实现）✓ 待
- [ ] 1.2 在 `council/schema.py` 的 `AgentOutput` dataclass 加 `new_evidence: list[str] = field(default_factory=list)` + `evidence_exhausted: bool = False`，`from_dict` 校验列类型，`known_fields` 集合更新避免透传到 extra。**Verify**：测试 pass，老输出（无新字段）仍能解析 ✓ 待
- [ ] 1.3 先写测试：断言 `SynthesizerOutput.from_json` 能解析含 `divergence_level`/`divergence_score`/`key_disagreements`/`confidence_adjustment`/`divergence_source`/`calibration_status` 的 JSON，缺失填默认，**不进 `__post_init__` 必填校验**（选填向后兼容）。**Verify**：测试 fail ✓ 待
- [ ] 1.4 在 `SynthesizerOutput` 加 6 个分歧报告字段（`divergence_level: str | None = None` 等，`confidence_adjustment: float = 0.0`，`calibration_status: str = "uncalibrated"`），`from_dict` 解析 + 类型校验，缺字段走默认。**Verify**：测试 pass，老 watchlist JSON 仍能解析 ✓ 待

## 2. 分歧度量化函数（D1，纯 Python，零 LLM）

- [ ] 2.1 先写测试 `tests/test_council_divergence.py`（新文件）：构造 R1 AgentOutput 列表，断言 `compute_divergence(round1)` 返回正确 `{signal_consensus, conviction_std, level}`——全员 bullish+std<10 → "low"；3:1+std=15 → "medium"；2:2 → "high"；全不同 → "extreme"。**Verify**：测试 fail（函数未实现）✓ 待
- [ ] 2.2 在 `council/debate.py`（或新 `council/divergence.py`）实现 `compute_divergence(round1: list[AgentOutput]) -> dict`：`signal_consensus` = 多数 signal 计数/总数；`conviction_std` = statistics.stdev（agent 数 <2 时返回 0）；`level` 按 D1 阈值映射。**Verify**：测试 pass ✓ 待
- [ ] 2.3 加边界测试：单 agent 列表、空列表、conviction 全相同（std=0）、signal 全 skip。**Verify**：边界场景不崩溃，返回合理 level ✓ 待

## 3. debate.py 分流 + 运行时降级（D1/D5/D6）

- [ ] 3.1 先写测试 `tests/test_council_debate.py`（扩展现有文件，mock call_llm）：构造 R1 全员一致的 mock 返回，断言 `run_debate` 跳过 R2/R3（round2/round3 为 None），只调 R4。**Verify**：测试 fail（当前固定跑 4 轮）✓ 待
- [ ] 3.2 在 `run_debate` R1 后插入分歧度分流：`divergence = compute_divergence(round1)`，按 level 决定跳 R2/R3（low/extreme 跳），写入辩论记录。**Verify**：测试 pass，低分歧场景 LLM 调用次数减少（R2×4+R3×1 省掉）✓ 待
- [ ] 3.3 先写测试：R2 后 ≥3 agent 标 `evidence_exhausted=true` 时，断言 `run_debate` 跳 R3。**Verify**：测试 fail ✓ 待
- [ ] 3.4 在 R2 后聚合 `evidence_exhausted`，≥3 则跳 R3。**Verify**：测试 pass ✓ 待
- [ ] 3.5 先写测试：R1 用 `return_exceptions=True` 收集，≥2/5 抛异常时断言触发运行时降级（跳 R2/R3、confidence_cap=40、watchlist 标 `council_degraded`）。**Verify**：测试 fail ✓ 待
- [ ] 3.6 改 R1 的 `asyncio.gather` 为 `gather(*tasks, return_exceptions=True)`，统计 error rate，≥40% 触发降级路径；R2 other_opinions 跳过异常 agent。**Verify**：测试 pass，个别失败容忍 + 多数失败降级两条路径都覆盖 ✓ 待
- [ ] 3.7 在 `_write_council_output` 透传 `divergence_*` 字段 + `council_degraded`/`degraded_reason`（若有）到 watchlist JSON。**Verify**：watchlist JSON 含新字段 ✓ 待

## 4. Prompt 改造（D2/D3，R2 + DA + Synthesizer）

- [ ] 4.1 在 `council/prompt.py` 的各 agent `build_*_prompt` 输出格式段加 `new_evidence`/`evidence_exhausted` 字段说明。**Verify**：prompt 文本含新字段说明 ✓ 待
- [ ] 4.2 在 `_build_user_message`（R2 路径）加强制新证据约束：「你必须引用至少一个 R1 未讨论的数据维度，否则声明 evidence_exhausted=true」。**Verify**：R2 user message 含约束文本 ✓ 待
- [ ] 4.3 改 `build_da_prompt`：加仲裁职责（评估各 agent 引用数据点真实性 + 回查 features 实际值）+ `evidence_quality_assessment`/`recommendation` 输出结构。**Verify**：prompt 含事实回查约束 + 新输出结构 ✓ 待
- [ ] 4.4 改 `build_synthesizer_prompt`：加「基于 DA 的 evidence_quality_assessment 和 recommendation 做最终判断」+ 分歧报告输出要求（divergence_level/key_disagreements/confidence_adjustment/divergence_source/calibration_status）+ structural 高标「不可解决」约束。**Verify**：prompt 含 DA 仲裁依赖 + 分歧报告字段 + structural 约束 ✓ 待
- [ ] 4.5 写测试 `tests/test_council_prompt.py`（扩展现有）：断言 `build_da_prompt`/`build_synthesizer_prompt` 返回含新增约束关键词。**Verify**：测试 pass ✓ 待

## 5. 质量门校验函数（§6 扩展，复用 f1 的反向校验）

- [ ] 5.1 先写测试 `tests/test_r2_new_evidence.py`（新文件）：构造 R2 AgentOutput，`new_evidence` 非空 → 通过；`evidence_exhausted=true` → 通过；两者皆无 → 拦截；`new_evidence` 含凭空数字 → 拦截（复用 `verify_r1_feature_grounding` 逻辑）。**Verify**：测试 fail ✓ 待
- [ ] 5.2 在 `council/verify_quality_gate.py` 实现 `verify_r2_new_evidence(output, features) -> tuple[bool, list[str]]`，复用 `verify_r1_feature_grounding` 的数字提取+匹配对 `new_evidence` 做反向校验。**Verify**：测试 pass ✓ 待
- [ ] 5.3 先写测试 `tests/test_divergence_report.py`（新文件）：构造 SynthesizerOutput，`divergence_level` 非空 + `calibration_status="uncalibrated"` → 通过；high 缺 `key_disagreements` → 拦截；缺 `divergence_level` → 拦截。**Verify**：测试 fail ✓ 待
- [ ] 5.4 实现 `verify_divergence_report(syn_output) -> tuple[bool, list[str]]`。**Verify**：测试 pass ✓ 待
- [ ] 5.5 先写测试 `tests/test_da_fact_check.py`（新文件）：构造 DA AgentOutput，`extra.evidence_quality_assessment` 非空 → 通过；缺失 → 拦截；`recommendation` 引用不存在 agent_id → 拦截。**Verify**：测试 fail ✓ 待
- [ ] 5.6 实现 `verify_da_fact_check(da_output, agent_ids=None) -> tuple[bool, list[str]]`，缺省动态读 `AGENT_REGISTRY.keys()`（复用 f1 P3 修复模式）。**Verify**：测试 pass ✓ 待
- [ ] 5.7 在 `verify_quality_gate` CLI 的 quality gate 段接入三个新校验，输出汇总。**Verify**：CLI 输出含新校验结果 ✓ 待

## 6. L2 优雅降级（D5，scout 层）

- [ ] 6.1 先写测试 `tests/test_scout_input_assembly.py`（扩展现有）：构造 features name/industry/market_cap 齐全但 pe_ttm=None，断言进入降级模式（返回 `degraded: true` + `degraded_reason`）而非 fail-fast。**Verify**：测试 fail（当前 financials 不齐走 insufficient_data fail-fast）✓ 待
- [ ] 6.2 在 `scout/input_assembly.py` 或 `scout/batch.py` 加 L2 降级逻辑：critical_fields 齐全但 financials_floor 不齐时，返回降级标记而非 error。**Verify**：测试 pass ✓ 待
- [ ] 6.3 在 `scout/batch.py` 降级处理：`confidence` 上限 50、`verdict` 强制 "watch"、标注 `degraded`，结果不进 deep_dive 短名单。**Verify**：降级票不进 deep_dive，watchlist/usage_summary 仍累加 ✓ 待
- [ ] 6.4 确认 L3 入口 fail-fast（`financials_floor`）不受 L2 降级影响——L2 降级是 scout 层、L3 fail-fast 是 council 层，不互相污染。**Verify**：council 层 `assemble_council_features` 仍 fail-fast（f1 行为不变），scout 层走降级 ✓ 待

## 7. 真实验证（G，需 LLM env）

> 依赖 §1-6 完成。用真实票验证，不 mock。

- [ ] 7.1 对 600009.SH（唯一真实完整产出基准）重跑全天团，验证：低/中分歧分流正确触发、R2 含 new_evidence 或 evidence_exhausted、DA 输出含 evidence_quality_assessment 且事实回查正确、R4 输出含分歧报告字段。**Verify**：质量门（含新校验）全 pass，与 600009 旧产出对比信息增量 ✓ 待
- [ ] 7.2 实测 token 节省：低分歧场景跳 R2/R3 后，对比 f1 的全 4 轮 token 消耗，记录节省比例。**Verify**：token usage 汇总写入辩论记录，节省比例记录到 `scripts/repro_out/divergence_skip_savings.md` ✓ 待
- [ ] 7.3 DA 事实回查真实性验证：人工检查 DA 的 `evidence_quality_assessment` 是否真的比对 features 实际值（而非纯文字评估）。**Verify**：DA 输出含具体 features 值比对（如"buffett 引用 ROE 32% 但 features.roe_3y=18.2 → inaccurate"）✓ 待

## 8. 收尾

- [ ] 8.1 跑 `pytest value-screener/tests/` 全套测试，确认无回归（尤其 schema 加字段后老测试 + debate 分流改动后 integration 测试）。**Verify**：测试全 pass（已知 pre-existing 的 test_cli_council.py rounds 字段不符不计）✓ 待
- [ ] 8.2 更新 `design/deviation-analysis-2026-07-01.md` 或 `design/kimi-worldcup-learnings.md` 标注借鉴落地状态（完全借鉴 2 项 + 部分借鉴 7 项的落地情况）。**Verify**：文档状态与实际一致 ✓ 待
- [ ] 8.3 准备 archive：确认 proposal/design/specs/tasks 一致，spec scenario 与实现对齐。**Verify**：可进入 `opsx:archive` ✓ 待
