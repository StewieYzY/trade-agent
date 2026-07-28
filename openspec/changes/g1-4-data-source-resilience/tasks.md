## 1. 基线确认与契约承接

- [ ] 1.1 确认基线在干净 `main@227478d`，canonical `data-minimum-contract` spec strict ✓ 已在 main
- [ ] 1.2 确认本 child 在独立分支 `feat/g1-4-data-source-resilience`，不污染 main
- [ ] 1.3 重读 canonical `data-minimum-contract` spec §4 禁止清单 + 归档 design D9 六项修复，确认承接边界（只实现 runtime，不改契约 requirement）

## 2. industry_mapper 失败显式化 + fallback（解 5533→18 根因，D1，优先级最高）

- [ ] 2.1 红测：写测试验证 `build_industry_map()` 东财失败时当前返空 dict `{}`（证明 bug）
- [ ] 2.2 红测：写测试验证 `generate_g1_4_sample._fetch_industry_map` 当前吞异常返 `{}`（证明 5533→18 根因）
- [ ] 2.3 最小实现：`build_industry_map` 东财失败时 fallback 到 `ak.stock_individual_info_em` 逐只查行业（不用同花顺 cons_ths）
- [ ] 2.4 fallback 也失败时返 `status=source_failed` + `attempted_sources` 结构（不返空 dict）
- [ ] 2.5 修 `_fetch_industry_map` 不吞 `source_failed`，透传给 G1-4 validation_gate
- [ ] 2.6 绿测 + 回归 `test_screener_stats` 等 G1-1 既有测试不破
- [ ] 2.7 commit D1

## 3. risk.pledge_ratio fallback + pledge_status 三态（D2）

- [ ] 3.1 红测：写测试验证 `pledge_ratio` 当前 `None` 不区分 `record_not_found` vs `source_failed`
- [ ] 3.2 红测：写测试验证 `risk.py:38` 注释「视为 0」与代码返 None 不符
- [ ] 3.3 验证 akshare 单只接口可用性，定 fallback provider 源（implementer 验证后定）
- [ ] 3.4 最小实现：`_fetch_pledge_ratio` 返结构区分三态（source_failed/record_not_found/invalid_value）
- [ ] 3.5 `fetch()` 返回值加 `pledge_status` 字段，主选 `_LazyTable` 复用与 `fallback_providers` 链保留
- [ ] 3.6 下游 safety_margin 按三态处理：record_not_found→满分、source_failed→0+manual
- [ ] 3.7 绿测 + 回归 `test_screener`/`test_screener_stats` safety 相关断言
- [ ] 3.8 commit D2

## 4. valuation fallback 标 present_but_degraded（D3）

- [ ] 4.1 红测：写测试验证 `_fallback_cninfo` 当前把全表均值赋给 `pe_ttm` 当真值
- [ ] 4.2 最小实现：fallback 路径 `pe_ttm` 标 `present_but_degraded` + provenance `source=fallback_cninfo_full_market_mean`（不删 fallback 能力）
- [ ] 4.3 下游 factor PE 行业折价/PE×PB 子项退出排名保诊断
- [ ] 4.4 绿测 + 回归 `test_screener_stats` value 子项断言
- [ ] 4.5 commit D3

## 5. H2 缺失 not_evaluable 不误杀（D4）

- [ ] 5.1 红测：写测试验证 H2 当前 `len([])<3` 判 FAIL 排除 financials 缺失的股票（证明误杀）
- [ ] 5.2 最小实现：financials 缺失或 `years` 空 → H2 输出 `not_evaluable`（加 `not_evaluable_gates` 列表）
- [ ] 5.3 `years` 有值但 `len<3` 保留 FAIL 语义（区分「数据缺失」与「确实不足 3 年」）
- [ ] 5.4 返回结构加 `not_evaluable_gates`，与 `pass`/`failed_gates` 向后兼容
- [ ] 5.5 绿测 + 回归 `test_screener` H2 既有断言（若需更新因契约行为变更，commit 说明）
- [ ] 5.6 commit D4

## 6. heat_filter 缺失 not_evaluable 不静默放行（D5）

- [ ] 6.1 红测：写测试验证 `check_heat_filter` 当前 kline 缺失/不足 60 日 `return {"pass": True}`（证明静默放行）
- [ ] 6.2 最小实现：kline 缺失/不足 60 日 → 返 `{"pass": False, "not_evaluable": True, "reason": ...}`
- [ ] 6.3 `not_evaluable` ticker 不计入 `after_heat_filter` 放行
- [ ] 6.4 返回结构加 `not_evaluable` bool + `reason`，与 `pass`/`failed_filters` 向后兼容
- [ ] 6.5 绿测 + 回归 `test_screener`/`test_screener_stats` heat 既有断言
- [ ] 6.6 commit D5

## 7. F-Score 缺失 not_evaluable 不转 0（D6）

- [ ] 7.1 红测：写测试验证 `compute_f_score` 当前 financials 缺失返 0（`factor_scores.py:297`）
- [ ] 7.2 红测：写测试验证 `_score_linear_decay` 当前 `value is None → return 0.0`（`factor_scores.py:41-42`）
- [ ] 7.3 最小实现：`compute_f_score` financials 缺失返 `None`（非 0）
- [ ] 7.4 `factor_scores.py:297` `f_score = compute_f_score(financials) if financials else None`
- [ ] 7.5 quality/value 子项 `if not scores: return 0.0` → 返 `None` + 标 degraded
- [ ] 7.6 `_score_linear_decay` `value is None → return None`，composite 聚合跳过 None 子项（权重不重分配）
- [ ] 7.7 `stock_features._f` 的 `default=0.0` 保留（F-Score 9 项内部比率分母处理，不影响整体返 None）
- [ ] 7.8 绿测 + 回归 `test_screener_stats` composite/f_score 断言（若需更新因契约行为变更，commit 说明）
- [ ] 7.9 commit D6

## 8. 全量验证与 review gate

- [ ] 8.1 全量 `pytest` 通过（含 G1-1/G1-2/G1-3 既有测试不回归）
- [ ] 8.2 `openspec validate g1-4-data-source-resilience --strict` 通过
- [ ] 8.3 确认六项修复均落 `not_evaluable`/`present_but_degraded`/`pledge_status`/`source_failed` 状态，可用率五拆可计算
- [ ] 8.4 停下交用户 review；通过后回 G1-4 重跑真实样本 Gate（G1-4 child 推进，不勾 umbrella 4.1/4.2，不 archive G1-4，不开 G2 runtime）
