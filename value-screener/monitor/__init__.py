"""L4 监控层 — weekly_monitor 主循环、watchlist 聚合、diff 引擎、催化检测、提醒系统.

模块结构（design.md 决策 2-5）：
- aggregation.py: watchlist 聚合（L1/L2/L3 三路产出 → watchlist/{date}.json）
- diff.py: 增量 diff 检测 + 历史轨迹查询
- catalyst.py: 催化事件检测（MVP 阶段基本面催化维度为空，仅风险信号）
- alert.py: 提醒系统（估值提醒 MVP 暂停 + 风险扫描 + key_variable 提醒）
- weekly.py: weekly_monitor 主循环编排
"""
