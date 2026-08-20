## 1. 冻结输入与身份

- [x] 1.1 冻结 600519/600900 历史失败快照，绑定 ticker/run_id/source hash/payload hash。
  **Verify**：`f3f_*_failure_snapshot.json` 已落盘，source hash `244d063b…be7d4b`、fixture hash 与 input snapshot hash 在 envelope 中绑定。
- [x] 1.2 写 RED 测试覆盖 ticker/source hash/fixture hash/run_id mismatch fail-closed。
  **Verify**：RED 阶段 `ModuleNotFoundError` 干净失败；修复后 `test_mismatch_branch_fails_closed_without_llm` 通过，`call_llm` 未 await，四类 mismatch 全 fail-closed。

## 2. 最小 fixture/dry-run harness

- [x] 2.1 回放历史 R1 输出，证明显性串台可被 `detect_circular_reference` 识别。
  **Verify**：600519 四 agent 环形串台、600900 单 agent munger 引用均被识别，`explicit_crosstalk_rate=1.0`。
- [x] 2.2 dry-run 验证历史 `insufficient_data` 输入在当前路径下 fail-closed，不达 LLM。
  **Verify**：`verify_historical_input_path` 返回 `fail_closed_ok`/`llm_reachable=false`，测试用 `AsyncMock` 断言 `call_llm` 未调用。
- [x] 2.3 生成确定性 fixture 报告，记录根因路径与残余风险，不宣称 G2 passed。
  **Verify**：`f3f_failure_repro_fixture_*/f3f_failure_repro_report.md` 已生成，含 fixture/live/implicit/G2 边界，不含 `capability passed`。

## 3. 验证与边界

- [x] 3.1 focused/full tests、compileall、OpenSpec strict、git diff check 通过。
  **Verify**：focused 12 passed；全量 1075 passed；compileall exit 0；`openspec validate --all --strict` 31 passed；`git diff --check` exit 0。
- [x] 3.2 独立 review 后 archive；不 merge、不 push、不宣称 G2 capability passed。
  **Verify**：review 无未解决 P0/P1；archive 成功；G2 1.3 记录为有界诊断闭环，不宣称 G2 capability passed。
