## 1. OpenSpec child 建立

- [x] 1.1 创建 `openspec/changes/g1-full-market-performance-cost/` 含 proposal、design、tasks、specs delta。
- [x] 1.2 写清隶属 `g1-fast-personal-value-screening`、只负责 M3 §5 工程 Gate、不替代 `g1-top20-style-review`、不宣称 G1 passed。

## 2. RED 测试

- [x] 2.1 写 evidence module 失败测试：`run_full_market_evidence` 返回含 `timing.total_elapsed_seconds`、`timing.l1_elapsed_seconds`、`timing.l2_elapsed_seconds` 的结构。
- [x] 2.2 写可用率测试：关键字段（ticker/f_score/adjusted_composite/pe_ttm/pb/pledge_ratio）可用率独立计算，缺字段时可用率下降并标记。
- [x] 2.3 写成本测试：实测成本和等效全量成本双口径均存在，预算阈值 ≤¥2。
- [x] 2.4 写未处理异常测试：`failure_summary["unhandled_exceptions"]` 非 0 时 `gate_passed=false`。
- [x] 2.5 写漏斗/降级/失败分布测试：evidence bundle 含完整漏斗、降级分布、失败分布和运行配置字段。
- [x] 2.6 写 gate_passed 判定测试：四维度（耗时 ≤15min、可用率 ≥95%、成本 ≤¥2、异常 =0）全达标才为 true。
- [x] 2.7 写 pledge_ratio 语义测试：record_not_found/source_failed 均保持 `None + pledge_status`，record_found 保留原值；evidence 可用率按 status 判定。
- [x] 2.8 写缓存温暖度预检测试：evidence bundle 含 cache_status 字段。
- [x] 2.9 写 review P2 回归测试：预检真实逻辑、save/failure bundle、elapsed/cost Gate 失败分支、L2 cache-hit 外推。

## 3. 最小实现

- [x] 3.1 新增 `value-screener/performance/run_evidence.py`，实现 `run_full_market_evidence(tickers, exclude_cyclicals, force_l2)` 包裹 screen_a_shares + scout_batch。
- [x] 3.2 实现分阶段耗时采集（L1/L2 各计时）。
- [x] 3.3 实现关键字段可用率独立计算。
- [x] 3.4 实现成本双口径（实测 + 等效全量）。
- [x] 3.5 实现 gate_passed 判定逻辑。
- [x] 3.6 实现 evidence bundle JSON 输出到 `data/evidence/` 路径。
- [x] 3.7 修复 `screen_a_shares` candidate 投影：保持 `pledge_ratio=None + pledge_status` canonical 语义。
- [x] 3.8 实现缓存温暖度预检 `_check_cache_warmth`。
- [x] 3.9 实现 status-aware field availability、coverage/ticker_source/evidence_notes。
- [x] 3.10 修复预检私有 `_path` 副作用、cache_base 未生效和 warm_cache/L2 cache 语义混用。
- [x] 3.11 增加 evidence schema_version 与精确 input_tickers，支持证据重放。
- [x] 3.12 修复 CacheManager 读路径 mkdir 副作用，仅写入时创建目录。

## 4. 真实运行与证据口径

- [x] 4.1 用真实已缓存 ticker 子集执行 partial-market warm-cache L1+L2 运行（560 只及后续小样本，非 fixture、非 mock）。
- [x] 4.2 evidence bundle 实现明确保存 `schema_version`、精确 `input_tickers`、`coverage`、`ticker_source`、`cache_status`、L2 cache-hit 口径和 `evidence_notes`。
- [x] 4.3 首次运行失败证据保留；此前 `2026-08-11_2b861f26.json` 的 560 只结论降级为历史 partial-market 证据，不作为修复后或 full-market Gate 通过证据。
- [ ] 4.4a 缓存刷新后重新生成修复后 partial-market evidence bundle；未完成前不引用旧 bundle 的 Gate 数字。
- [ ] 4.4 完整沪深集合（预计约 5208 只，北交所不在本 child scope）缓存预热完成后，执行 `coverage=full_market` warm-cache L1+L2 运行。
- [x] 4.4b 预热编排脚本（`scripts/prewarm_driver.py`）：主预热退出后补缺口 → 最后真实重取 basic（basic TTL=2h，先刷会在运行前过期）→ 全暖终检通过后执行证据运行；不暖则中止并记录缺口，不跑污染运行。universe 实时 akshare 重试 3 次，失败兜底已生成快照（`data/universe_full.json`），口径写入日志与 `ticker_source`。
- [ ] 4.5 以 full-market bundle 独立验证耗时、可用率、L2 首次调用成本/等效成本和未处理异常；未满足时保留失败证据，不勾选 umbrella 5.2。

## 5. 验证与收口

- [x] 5.1 运行 focused pytest（evidence module 测试，30 条）转绿。
- [x] 5.2 运行全量回归 `pytest value-screener/tests -q`（820 passed，零回归）。
- [x] 5.3 运行 `compileall -q value-screener`。
- [x] 5.4 运行 `openspec validate --all --strict`。
- [x] 5.5 运行 `git diff --check` 和 `git status --short --branch`。
- [x] 5.6 完成独立 CR；P1/P2 findings 已修复并重新验证。
- [x] 5.7 完成二次独立 CR，确认 P1/P2 无回归；二次 CR 新增 P1/P2 已修复并复验。
