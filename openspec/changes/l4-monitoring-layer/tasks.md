## 1. Setup

- [ ] 1.1 创建 `value-screener/monitor/` 包结构：`__init__.py` / `weekly.py` / `diff.py` / `catalyst.py` / `alert.py`
- [ ] 1.2 在 `cli.py` 注册 `monitor` Typer 子命令组（`monitor_app = typer.Typer()` + `app.add_typer`），占位 `weekly` / `watchlist` / `diff` / `history` 四个子命令（函数体 `raise NotImplementedError`）

## 2. Watchlist 聚合（watchlist-aggregation spec）

- [ ] 2.1 实现 `monitor/aggregation.py`：`aggregate_watchlist(run_date, l1_output_file, scout_cache, watchlist_dir)` 函数，读取 L1 产出文件（检查文件存在性，>7 天报错提示"请先跑 `screen`"）+ L2 cache + L3 per-ticker JSON，聚合为 §7 结构
- [ ] 2.2 L3 null 字段防御：`conviction`/`consensus_summary`/`dissent_points`/`pending_verification` 为 null 时保留 null，`final_verdict` 为 null 时标记 `unknown`，`key_variables` 为 null/空时设为 null
- [ ] 2.3 watchlist 健康检查：L3 文件存在但四个字段全 null 时标记 `l3_incomplete: true`
- [ ] 2.4 stage 字段计算：有 L3 verdict → `l3`；L2 deep_dive → `l2`；L2 pass/reject 或无 L2 → `l1`
- [ ] 2.5 pe_percentile_5y 补充：对 `stage >= l2` 的 candidate 调用 `ValuationFetcher().fetch_with_fallback(ticker)` 补充 `pe_percentile_5y` 字段，fetch 失败 → `pe_percentile_5y: null`，不阻断聚合。`stage=l1` 的 candidate 留 null。fetch_with_fallback 配合 L0 CacheManager，L1 刚跑过时命中缓存零网络
- [ ] 2.6 按日归档写入 `watchlist/{date}.json`，同日幂等覆盖
- [ ] 2.7 编写测试：mock L1 output file + ScoutCache + L3 JSON + ValuationFetcher，验证聚合输出结构、null 防御、健康检查、stage 计算、pe_percentile_5y 补充（含 fetch 失败用例）

## 3. Diff 引擎（watchlist-diff spec）

- [ ] 3.1 实现 `monitor/diff.py`：`compute_diff(current, previous)` 函数，检测 7 种 diff 类型（added/removed/l1_score_changed/stage_upgraded/stage_downgraded/verdict_changed/valuation_low），每种带严重度标记
- [ ] 3.2 首次运行处理：无上一快照时 diff 报告标注"首次运行，无历史对比"
- [ ] 3.3 触发 L2 重评估逻辑：candidate 新增 或 `l1_score` 变化 > 15 → 返回需重跑 L2 的 ticker 列表
- [ ] 3.4 触发 L3 深研逻辑：`l2_verdict` 翻转为 `deep_dive` → 返回需重跑 L3 的 ticker 列表
- [ ] 3.5 历史轨迹查询：`history(ticker, date_from, date_to)` 函数，遍历 `watchlist/*.json` 快照，输出 Markdown 表格（日期 | l1_score | stage | l3_verdict | pe_percentile），快照数 > 50 时提示缩小范围
- [ ] 3.6 编写测试：构造 current/previous 两个快照 dict，验证 7 种 diff 类型检测、触发阈值、首次运行降级、历史轨迹查询

## 4. 催化事件检测（catalyst-detection spec）

- [ ] 4.1 实现 `monitor/catalyst.py`：`detect_catalysts(ticker, current_features, previous_features)` 函数，MVP 阶段**基本面催化维度为空**（仅输出 placeholder 提示），只检测风险信号（质押率急升 >5ppt）。注意：`pe_percentile_5y` 边际变化是 diff 信号（`valuation_low`），不是催化事件
- [ ] 4.2 质押率急升检测：`pledge_ratio` 周环比上升 > 5ppt 时触发风险信号
- [ ] 4.3 预留 `_llm_catalyst_check()` 函数 + 7 条 TODO 注释（财报/分红/行业政策/管理层变动/减持/业绩预告差/审计意见变更）
- [ ] 4.4 编写测试：mock current/previous features dict，验证质押率急升检测

## 5. 提醒系统（monitoring-alerts spec）

- [ ] 5.1 实现 `monitor/alert.py`：`generate_alerts(candidates, diff_report, catalyst_report)` 函数，生成三类提醒（估值提醒 / 风险扫描 / key_variable 提醒）。**MVP 阶段估值提醒暂停**：输出 placeholder `"⏸️ 估值提醒暂不可用——基本面催化事件数据源待补齐（event-fetcher TODO）"`
- [ ] 5.2 AD-02 双条件框架代码保留：`valuation_alert` 函数签名和逻辑骨架保留，但 MVP 阶段实际输出为 placeholder（不生成 🟢 提醒）
- [ ] 5.3 风险事件扫描：质押率急升硬规则提醒 + 3 条 TODO（减持/业绩预告差/审计意见变更）
- [ ] 5.4 key_variables 提醒：非 null 非空时列出 `💡 结合近期动态核对是否发生变化` 提示 + TODO 注释（自动检测预留）
- [ ] 5.5 what_would_change_my_mind 适用范围区分：`stage=l3` 标注"核对催化与 key_variables 相关性"，`stage=l1/l2` 标注"催化作为 L3 加分项"
- [ ] 5.6 提醒不自动触发 L3：估值提醒和风险扫描只产出文本，不调用 council
- [ ] 5.7 错误处理：L2 重跑失败时跳过该 ticker 并标注"L2 评估失败"；催化检测数据缺失时跳过该信号不报错
- [ ] 5.8 编写测试：mock candidates + diff + catalyst 报告，验证 AD-02 双条件、风险扫描、key_variable 提醒、适用范围区分、错误处理

## 6. Weekly 主循环（weekly.py）

- [ ] 6.1 实现 `monitor/weekly.py`：`async run_weekly(l1_output_file=None)` 异步函数，编排完整主循环：读取 L1 产出文件（>7 天报错提示跑 `screen`）→ 聚合 watchlist → diff → 条件触发 L2 → 条件触发 L3 → 催化检测 → 估值提醒 → 风险扫描 → key_variable 提醒
- [ ] 6.2 触发 L2 重评估：`await scout_batch()` 对 diff 指定的 ticker 重跑（绕过 24h 缓存），失败时跳过该 ticker
- [ ] 6.3 触发 L3 深研：`await run_debate()` 对 diff 指定的 ticker 跑深研
- [ ] 6.4 周报生成：汇总 diff 报告 + 催化事件 + 三类提醒 + watchlist 健康检查结果，输出结构化 Markdown 文本（按 design.md 周报格式）
- [ ] 6.5 成本日志：记录本次运行触发的 L2/L3 调用数量和估算成本
- [ ] 6.6 编写测试：mock L1/L2/L3 调用，验证主循环编排顺序、触发阈值、成本日志、错误处理

## 7. CLI 集成（monitor-cli spec）

- [ ] 7.1 实现 `monitor weekly` 子命令：调用 `run_weekly()`，支持 `--output` 写入文件 + `--force-l2` 强制重跑 + `--l1-file` 指定 L1 产出文件路径
- [ ] 7.2 实现 `monitor watchlist` 子命令：查看最新或指定日期 watchlist，支持 `--json` 原始输出和 `--date` 指定日期
- [ ] 7.3 实现 `monitor diff` 子命令：查看最新或指定日期 diff 报告
- [ ] 7.4 实现 `monitor history` 子命令：查询单只股票历史轨迹，支持 `--from` / `--to` 日期范围
- [ ] 7.5 CLI 集成测试：用 Typer CliRunner 验证四个子命令的参数解析和输出

## 8. 集成验证

- [ ] 8.1 端到端冒烟：用 L1/L2/L3 已有的真实数据跑一次完整 `monitor weekly`，验证周报产出
- [ ] 8.2 watchlist 聚合验证：检查 `watchlist/{date}.json` 结构符合 L4 聚合规范（§7 子集 + L2/L3 扩展），null 字段正确处理
- [ ] 8.3 成本验证：确认 L4 轻量监控本身无 LLM 调用（¥0），触发 L2/L3 成本在日志中单独列
