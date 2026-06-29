"""Scout 质量保证 — 24h 缓存含输入快照（design.md §3.3, tasks 4.1-4.5）.

缓存策略（design.md §3.3）：
- TTL=24h（与 L0 DAILY_PRICE 档位一致）
- 同交易日不重跑（cache 命中直接复用）
- 缓存包含输入特征快照（区分"数据变了" vs "模型飘了"）
- {date} 子目录隔离不同交易日结果（跨日不覆盖，支持对比诊断）

缓存结构：
{
    "verdict": "watch",
    "confidence": 72,
    "one_liner": "...",
    "red_flags": [...],
    "green_flags": [...],
    "anti_trap_flags": [...],
    "input_snapshot": {"pe_ttm": 38.5, "pb": 8.2, ...},
    "timestamp": "2026-06-29T10:30:00"
}

与 CacheManager 的关系：
ScoutCache 独立实现，不扩展 CacheManager._DIM_TTL。原因：
- L2 缓存路径结构不同（含 {date} 子目录）
- L2 缓存 TTL 语义不同（跨日保留 vs 24h 过期）
- L2 缓存需存储 input_snapshot（诊断用途）
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path


class ScoutCache:
    """Scout 结果缓存（24h TTL，含输入特征快照，按日隔离）."""

    def __init__(self, base_dir: str | Path = "data/cache"):
        self.base = Path(base_dir)
        self.base.mkdir(parents=True, exist_ok=True)

    def _path(self, ticker: str, date_str: str) -> Path:
        """缓存路径：data/cache/{ticker}/{date}/l2_scout.json."""
        d = self.base / ticker / date_str
        d.mkdir(parents=True, exist_ok=True)
        return d / "l2_scout.json"

    def get(self, ticker: str, date_str: str) -> dict | None:
        """读缓存；过期（>24h）/缺失/损坏返回 None.

        Args:
            ticker: 股票代码
            date_str: 日期字符串（ISO 格式，如 "2026-06-29"）

        Returns:
            缓存 dict（含 verdict/confidence/input_snapshot 等），或 None
        """
        p = self._path(ticker, date_str)
        if not p.exists():
            return None

        # TTL=24h（86400 秒）
        age = time.time() - p.stat().st_mtime
        if age > 86400:
            return None

        try:
            with p.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def set(self, ticker: str, date_str: str, result: dict, input_snapshot: dict) -> None:
        """原子写缓存（含输入特征快照）.

        Args:
            ticker: 股票代码
            date_str: 日期字符串（ISO 格式）
            result: LLM 输出结果（verdict/confidence/flags 等）
            input_snapshot: 输入特征快照（pe_ttm/pb/roe_3y 等）

        缓存结构：
        {
            "verdict": ...,
            "confidence": ...,
            "one_liner": ...,
            "red_flags": [...],
            "green_flags": [...],
            "anti_trap_flags": [...],
            "input_snapshot": {...},
            "timestamp": "2026-06-29T10:30:00"
        }
        """
        p = self._path(ticker, date_str)
        tmp = p.with_suffix(".tmp")

        cache_data = {
            **result,
            "input_snapshot": input_snapshot,
            "timestamp": datetime.now().isoformat(),
        }

        try:
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(cache_data, f, ensure_ascii=False, default=str)
            os.replace(tmp, p)  # 原子替换
        except OSError:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            raise

    def clear(self, ticker: str | None = None, date_str: str | None = None) -> int:
        """清理缓存文件.

        Args:
            ticker: 指定 ticker；None 清全部
            date_str: 指定日期；None 清该 ticker 下全部日期

        Returns:
            删除的文件数
        """
        deleted = 0
        if ticker is None:
            # 清全部
            for p in self.base.rglob("l2_scout.json"):
                try:
                    p.unlink()
                    deleted += 1
                except OSError:
                    pass
            # 清理空目录
            for d in sorted(self.base.rglob("*"), reverse=True):
                if d.is_dir() and not any(d.iterdir()):
                    try:
                        d.rmdir()
                    except OSError:
                        pass
        else:
            ticker_dir = self.base / ticker
            if not ticker_dir.exists():
                return 0
            if date_str:
                p = ticker_dir / date_str / "l2_scout.json"
                if p.exists():
                    try:
                        p.unlink()
                        deleted += 1
                    except OSError:
                        pass
            else:
                for p in ticker_dir.rglob("l2_scout.json"):
                    try:
                        p.unlink()
                        deleted += 1
                    except OSError:
                        pass
        return deleted
