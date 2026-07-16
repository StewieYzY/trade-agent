## 1. 实验脚手架（D1，不改主代码）

- [ ] 1.1 建 `value-screener/scripts/repro_out/crosstalk_exp.py`：构造 D1 控制变量矩阵 4 组对照（组1 features 充足×prompt 保留×弱模型 / 组2 features 缺失×prompt 保留×弱模型 / 组3 features 缺失×prompt 剥离×弱模型 / 组4 features 缺失×prompt 保留×强模型）。组1 用 600009.SH 真实 dossier；组2 构造空 features 复刻 600519 旧 bug 条件；组3 用函数级 patch / 复制改写构造剥离案例锚定的 prompt 版本（**不改 `council/prompt.py` 主文件**）；组4 env 切换强模型。**Verify**：脚本能跑通 4 组构造，主 prompt.py git diff 为空（未污染）✓
- [ ] 1.2 实验脚本采集观测指标：显性串台率（`detect_circular_reference` 命中数/4）、隐性串台率（采样 core_thesis 含「其他/另一位/共识/也看好/大家」等不点名措辞）、同质化率（`compute_citation_divergence` Jaccard，信息增量口径）、凭空数字率（`verify_r1_feature_grounding` 命中率）。每 agent 每指标落盘到 `repro_out/crosstalk_exp_data.json`。**Verify**：4 组数据结构齐全，指标可读取 ✓
- [ ] 1.3 确认强模型可得性（组4 前置）：查 `.env` 是否有 `LLM_MODEL_HEAVY` 强模型（gpt-4 级）配置。若无，design §Open Questions 降级为只验证 A（组1-3），B 留待补，实验报告标注。**Verify**：env 配置核实结论记录 ✓

## 2. 跑实验出报告（D1 结论）

- [ ] 2.1 跑 D1 4 组实验（或组1-3 若组4 不可得），落盘原始产出到 `repro_out/crosstalk_exp_raw/`。**Verify**：4 组（或 3 组）R1 产出齐全可复现 ✓
- [ ] 2.2 写 `repro_out/crosstalk_exp_report.md`：4 组指标对比表 + A/B 结论判读（组3↓且组4不降→主因A / 组4↓且组3不降→主因B / 都降→混合记降幅比 / 都不降→两假设皆否）。**Verify**：结论明确分叉到 A/B/混合/皆否四态之一，附降幅数据 ✓
- [ ] 2.3 报告标注「修复（改 prompt 架构 / 换模型）开独立 f3d change，不在本 change 实施」，并按结论分叉预写 f3d 的 change 名（A→f3d-r1-crosstalk-prompt-fix / B→f3d-r1-crosstalk-model-fix / 混合→f3d 双管 / 皆否→f3e 新假设）。**Verify**：报告含 f3d 立项指引 ✓

## 3. D2 接线——质量门接主流程断路器（TDD，最敏感步骤）

- [ ] 3.1 先写测试 `tests/test_r1_crosstalk_breaker.py`：构造 R1 含显性环形引用（buffett core_thesis="munger 看好"）的 mock 产出，断言 `run_debate` 在 R1 后 hard fail 阻断（不进 R2，不写"成功"watchlist JSON，抛错或标记 `quality_gate_failed`）；构造无环形真实产出（复用 600009 真实 R1），断言通过断路器进入分流。**Verify**：测试 fail（`run_debate` 现 R1 后无断路器）✓
- [ ] 3.2 先写测试：断言凭空数字 + 隐性串台只 soft warning 不阻断（构造含凭空 ROE 32% 的 R1，断言 `run_debate` 仍产出 JSON，quality 字段记 warning）；断言运行时降级（R1<4 agent）下显性环形仍 hard fail（降级豁免 R3 跳过不豁免串台铁证）。**Verify**：测试 fail ✓
- [ ] 3.3 改 `council/debate.py::run_debate`：R1 所有 agent gather 完成后、分歧度分流前，插入断路器段——对每 agent 调 `detect_circular_reference` + `verify_r1_feature_grounding`；显性环形命中走 hard fail（参照 `insufficient_data` 的 fail-fast error 路径，不进 R2/R3/R4 省 LLM 成本 AD-03）；凭空数字/隐性走 soft warning 记入 CouncilResult/产出。核实 `run_debate` 现有 error 路径（`insufficient_data` 抛 ValueError 还是标记字段）保持一致。**Verify**：3.1 测试 pass（hard fail 阻断 + 真实产出通过）✓
- [ ] 3.4 3.2 测试 pass（soft warning 不阻断 + 降级下仍拦显性）。**Verify**：soft/降级两条路径行为正确 ✓
- [ ] 3.5 跑现有 council 测试套件确认无回归：`pytest tests/test_council_*.py tests/test_debate*.py`，f1/f2/f3a 已有测试仍 pass（断路器只在 R1 后触发，不影响 R2-R4 编排、缓存、降级、分流逻辑；600009 真实产出基线通过）。**Verify**：全套 pass，无回归（修复测试 patch 目标失效等接入点变更）✓

## 4. D3 隐性串台采样评估

- [ ] 4.1 在 D1 组2（features 缺失，复刻 bug 条件）产出上跑隐性串台采样：按采样规则（core_thesis 含「其他/另一位/共识/也看好/大家/都看好」等不点名引用）统计隐性串台占比。**Verify**：组2 隐性串台占比数据落盘 ✓
- [ ] 4.2 据占比决定是否升级语义检测：占比 > 阈值（待实验定）→ design §Open Questions 记「需开独立 change 升级语义级检测」；占比低 → 字符串匹配够用，不动。**Verify**：决策记录入 design/crosstalk_exp_report ✓

## 5. 收尾

- [ ] 5.1 跑全套测试 `pytest value-screener/tests/`，确认所有测试 pass（含 f1/f2/f3a 已有 + f3c 新增断路器测试），无回归。**Verify**：全套 pass ✓
- [ ] 5.2 回填 design.md Open Questions：D1 强模型可得性确认结果、组3 prompt 剥离边界（删了哪些段）、D2 hard fail 的 error 路径选择（抛错 vs 标记 `quality_gate_failed`）、D3 隐性串台阈值实测、A/B 结论 + 是否动摇 AD-09（呈递 architect）。**Verify**：Open Questions 标注实测结果 ✓
- [ ] 5.3 准备 archive：`openspec validate --changes f3c-r1-crosstalk-root-cause` + `openspec status --change f3c-r1-crosstalk-root-cause` 确认 isComplete=true，按 `opsx:archive` 流程归档。**Verify**：status isComplete=true ✓
- [ ] 5.4 据 5.2 的 A/B 结论，开 f3d 修复 change（按 2.3 预写的 change 名）。本 change 不含修复实施。**Verify**：f3d proposal 建出（或皆否时开 f3e）✓
