## 1. 失败测试先行（TDD Red）

- [x] 1.1 新增测试 `test_dcf_dimension_mismatch_excluded`：构造公司级 FCF 数据（亿元量级），证明旧实现会将企业价值与每股价格直接比较产生错误安全边际；新实现中 DCF 不参与排序，`dcf_note` 为 `"dcf_dimension_mismatch"`
- [x] 1.2 新增测试 `test_safety_margin_only_pledge_when_dcf_excluded`：证明 DCF 被排除后，安全边际 100% 由质押率构成（质押率 30% → 安全边际 = 75.0）
- [x] 1.3 新增测试 `test_dcf_note_insufficient_data`：FCF 不足 2 期时，`dcf_note` 为 `"insufficient_data"`
- [x] 1.4 新增测试 `test_dcf_note_calculation_error`：模拟 DCF 计算抛出 ValueError，`dcf_note` 为 `"calculation_error"`，排序继续
- [x] 1.5 新增测试 `test_unexpected_exception_propagates`：模拟 DCF 计算抛出 AttributeError，异常向上传播不被静默捕获
- [x] 1.6 运行测试确认全部 RED

## 2. 实现修复

- [x] 2.1 修改 `_compute_safety_margin_score()`：移除 DCF 参与加权的逻辑，安全边际子项 100% 由质押率构成
- [x] 2.2 收窄异常处理：将 `except Exception` 改为 `except (ValueError, ZeroDivisionError, TypeError)`，并将异常信息记录到 `dcf_note`
- [x] 2.3 在 `_compute_safety_margin_score()` 中生成 `dcf_note` 字符串，说明 DCF 未参与排序的原因
- [x] 2.4 修改 `compute_factor_scores()` 返回结构，新增 `dcf_note` 字段

## 3. 测试通过验证（TDD Green）

- [x] 3.1 运行新增测试确认全部 GREEN
- [x] 3.2 运行 `pytest tests/test_screener.py -q` 确认现有测试无回归
- [x] 3.3 运行 `pytest -q` 确认全量测试通过

## 4. 排序关键指标审计

- [x] 4.1 扫描 ROE 计算：确认分母（权益）为零或负时跳过，不产生无穷大
- [x] 4.2 扫描 F-Score：确认 0-9 整数输出，归一化到 0-100 无单位错误
- [x] 4.3 扫描 PE/PB：确认负值或零值被正确降级处理
- [x] 4.4 记录审计结论到 design.md 或测试注释

## 5. OpenSpec 验证与归档准备

- [x] 5.1 运行 `openspec validate l1-numeric-correctness --type spec --strict`、`openspec validate quantitative-screener --type spec --strict` 和 `openspec validate g1-fast-personal-value-screening --strict` 确认 canonical specs 与 umbrella artifacts 完整（已归档 child 名称不再作为 active change 被 CLI 接受）
- [x] 5.2 运行 `git diff --check` 确认无空白错误
- [x] 5.3 确认本 change 推进 G1 umbrella milestone 1.1 和 1.2
