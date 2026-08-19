## 1. 实验脚手架（D1，不改主代码）

- [x] 1.1 建 D1 四组脚手架，并通过冻结 dossier 输入校验；prompt 剥离使用函数级复制改写，不修改 `council/prompt.py`。**Verify**：脚手架测试 7 passed ✓
- [x] 1.2 采集显性/隐性串台、Jaccard、凭空数字指标，保存 per-agent raw/output/hash/usage 与 group aggregate。**Verify**：live bundle 四组 raw 产出齐全 ✓
- [x] 1.3 使用 `value-screener/.env` 确认 weak/heavy 模型配置；不落盘 key。**Verify**：16 次调用按组成功使用 weak/heavy model ✓

## 2. 跑实验出报告（D1 结论）

- [x] 2.1 跑 D1 四组 live R1 实验，使用冻结的 600009.SH dossier，四组4/4成功，原始产出落盘 `repro_out/crosstalk_exp_live_20260819/`。**Verify**：四组 R1 产出齐全 ✓
- [x] 2.2 写 live 报告：显性串台四组0、group2隐性0、Jaccard 与凭空数字率指标齐全；按显性串台四态判读为皆否/新假设。**Verify**：报告含 source hash、输入边界和指标表 ✓
- [x] 2.3 报告明确 prompt/model 修复须开独立 f3d/f3e，不在本 change 实施。**Verify**：报告含分叉边界 ✓

## 3. D2 接线——质量门接主流程断路器（TDD，最敏感步骤）

- [x] 3.1 先写测试 `tests/test_r1_crosstalk_breaker.py`：构造 R1 含显性环形引用（buffett core_thesis="munger 看好"）的 mock 产出，断言 `run_debate` 在 R1 后 hard fail 阻断（不进 R2，不写"成功"watchlist JSON，抛错或标记 `quality_gate_failed`）；构造无环形真实产出（复用 600009 真实 R1），断言通过断路器进入分流。**Verify**：测试 fail（`run_debate` 现 R1 后无断路器）✓ 已完成（DID NOT RAISE 干净红灯）
- [x] 3.2 先写测试：断言凭空数字 + 隐性串台只 soft warning 不阻断（构造含凭空 ROE 32% 的 R1，断言 `run_debate` 仍产出 JSON，quality 字段记 warning）；断言运行时降级（R1<4 agent）下显性环形仍 hard fail（降级豁免 R3 跳过不豁免串台铁证）。**Verify**：测试 fail ✓ 已完成（降级测试初版 mock 脆弱先 xfail，接线后重写为可控 call_agent mock 正式 pass）
- [x] 3.3 改 `council/debate.py::run_debate`：R1 所有 agent gather 完成后、分歧度分流前，插入断路器段——对每 agent 调 `detect_circular_reference` + `verify_r1_feature_grounding`；显性环形命中走 hard fail（参照 `insufficient_data` 的 fail-fast error 路径，不进 R2/R3/R4 省 LLM 成本 AD-03）；凭空数字/隐性走 soft warning 记入 CouncilResult/产出。核实 `run_debate` 现有 error 路径（`insufficient_data` 抛 ValueError 还是标记字段）保持一致。**Verify**：3.1 测试 pass（hard fail 阻断 + 真实产出通过）✓ 已完成（断路器插 round1 分离后、error_rate 前；**延迟 import** `detect_circular_reference`/`verify_r1_feature_grounding` 打破 `debate↔verify_quality_gate` 循环依赖——f1 留的潜在陷阱，f1 没在 debate.py 用检测器没暴露，f3c 接线撞上；error 路径选 raise ValueError 与 insufficient_data 一致；r1_quality_warnings soft 暂记 list）
- [x] 3.4 3.2 测试 pass（soft warning 不阻断 + 降级下仍拦显性）。**Verify**：soft/降级两条路径行为正确 ✓ 已完成（5/5 断路器测试 pass：显性环形阻断/无环形通过/凭空 soft/隐性 soft/降级下仍拦）
- [x] 3.5 跑现有 council 测试套件确认无回归：`pytest tests/test_council_*.py tests/test_debate*.py`，f1/f2/f3a 已有测试仍 pass（断路器只在 R1 后触发，不影响 R2-R4 编排、缓存、降级、分流逻辑；600009 真实产出基线通过）。**Verify**：全套 pass，无回归（修复测试 patch 目标失效等接入点变更）✓ 已完成（council 核心 47 全绿；全套 324 passed + 1 xpassed；10 failed 全为预存 akshare 环境缺失，与接线无关——f3a fetcher 依赖 akshare 本地未装）

## 4. D3 隐性串台采样评估

- [x] 4.1 在 D1 group2 live 产出上按词表采样，隐性串台占比0.00。**Verify**：group2 raw/report 已记录 ✓
- [x] 4.2 以 >0.25 为建议线；group2=0.00，保持字符串检测，不升级语义检测。**Verify**：报告已记录 ✓

## 5. 收尾

- [x] 5.1 跑全套测试 `pytest value-screener/tests/`，确认所有测试 pass（含 f1/f2/f3a 已有 + f3c 新增断路器测试），无回归。**Verify**：全套 pass（1048 passed）✓
- [x] 5.2 回填 design.md Open Questions：D1 强模型可得性确认结果、组3 prompt 剥离边界（删了哪些段）、D2 hard fail 的 error 路径选择（抛错 vs 标记 `quality_gate_failed`）、D3 隐性串台阈值实测、A/B 结论 + 是否动摇 AD-09（呈递 architect）。**Verify**：Open Questions 标注实测结果 ✓
- [x] 5.3 准备 archive：`openspec validate --changes f3c-r1-crosstalk-root-cause` + `openspec status --change f3c-r1-crosstalk-root-cause` 确认 isComplete=true，按 `opsx:archive` 流程归档。**Verify**：status isComplete=true ✓
- [x] 5.4 据 5.2 的 A/B 结论，开 f3d 修复 change（按 2.3 预写的 change 名）。本 change 不含修复实施。**Verify**：皆否时已建立独立 f3e proposal ✓
