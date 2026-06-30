## ADDED Requirements

### Requirement: monitor weekly 子命令
系统 SHALL 提供 `monitor weekly` 子命令运行 weekly_monitor 主循环。

#### Scenario: 运行 weekly_monitor
- **WHEN** 调用 `python cli.py monitor weekly`
- **THEN** 执行完整主循环：读取 L1 产出文件 → 聚合 watchlist → diff → 条件触发 L2/L3 → 估值提醒 → 风险扫描 → key_variable 提醒，输出周报文本

#### Scenario: L1 产出文件检查
- **WHEN** 调用 `python cli.py monitor weekly` 但 L1 产出文件不存在或过期（> 7 天）
- **THEN** 报错退出，提示"请先跑 `screen` 更新 L1 数据"

#### Scenario: 指定输出文件
- **WHEN** 调用 `python cli.py monitor weekly --output report.md`
- **THEN** 将周报写入 `report.md`，同时打印到 stdout

#### Scenario: 强制重跑 L2
- **WHEN** 调用 `python cli.py monitor weekly --force-l2`
- **THEN** 对所有 candidate 强制重跑 L2（绕过 diff 阈值判断）
- **AND** 输出预估成本警告：`⚠️ 强制重跑 L2：{N} 只 × ¥0.01 = ¥{cost}，确认继续？（--yes 跳过确认）`

### Requirement: monitor watchlist 子命令
系统 SHALL 提供 `monitor watchlist` 子命令查询聚合 watchlist。

#### Scenario: 查看最新 watchlist
- **WHEN** 调用 `python cli.py monitor watchlist`
- **THEN** 输出最新 `watchlist/{date}.json` 的内容（格式化打印）

#### Scenario: 查看指定日期 watchlist
- **WHEN** 调用 `python cli.py monitor watchlist --date 2026-06-30`
- **THEN** 输出 `watchlist/2026-06-30.json` 的内容

#### Scenario: 输出为 JSON
- **WHEN** 调用 `python cli.py monitor watchlist --json`
- **THEN** 输出原始 JSON（不格式化）

### Requirement: monitor diff 子命令
系统 SHALL 提供 `monitor diff` 子命令查询 diff 报告。

#### Scenario: 查看最新 diff
- **WHEN** 调用 `python cli.py monitor diff`
- **THEN** 对比最新 `watchlist/{date}.json` 与上一快照，输出 diff 报告

#### Scenario: 对比指定日期
- **WHEN** 调用 `python cli.py monitor diff --date 2026-06-30`
- **THEN** 对比 `watchlist/2026-06-30.json` 与上一快照

### Requirement: monitor history 子命令
系统 SHALL 提供 `monitor history` 子命令查询单只股票历史轨迹。

#### Scenario: 查询历史轨迹
- **WHEN** 调用 `python cli.py monitor history {ticker}`
- **THEN** 输出该 ticker 在所有快照中的 `l1_score` 走势、`stage` 变化、`l3_verdict` 变化、`pe_percentile_5y` 走势

#### Scenario: 指定日期范围
- **WHEN** 调用 `python cli.py monitor history {ticker} --from 2026-06-01 --to 2026-06-30`
- **THEN** 只输出指定日期范围内的轨迹

### Requirement: CLI 子命令注册
系统 SHALL 在 `cli.py` 中注册 `monitor` 子命令组。

#### Scenario: monitor 子命令组存在
- **WHEN** 调用 `python cli.py --help`
- **THEN** 帮助信息中包含 `monitor` 子命令组

#### Scenario: monitor 子命令帮助
- **WHEN** 调用 `python cli.py monitor --help`
- **THEN** 列出 `weekly`/`watchlist`/`diff`/`history` 四个子命令及其说明
