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

from data.lib.identity import canonical_code


class ScoutCache:
    """Scout 结果缓存（24h TTL，含输入特征快照，按日隔离）.

    g1-canonical-run-identity: cache 路径用 canonical_code（纯数字）建目录，
    消除 600519/600519.SH 双目录分裂；cache entry 绑定 run_id/profile_version/
    input_ticker_set_hash（继承自 L1，纯 L2 单跑用 fallback run_id）。
    身份与 cache key 分离：canonical_ticker 带后缀作身份/输出 key，
    canonical_code 纯数字作 cache 目录（与 CacheManager._normalize_ticker D3 对齐）。
    """

    def __init__(self, base_dir: str | Path = "data/cache"):
        self.base = Path(base_dir)
        self.base.mkdir(parents=True, exist_ok=True)

    def _path(self, ticker: str, date_str: str) -> Path:
        """缓存路径：data/cache/{canonical.code}/{date}/l2_scout.json.

        g1-canonical-run-identity: 用 canonical_code（纯数字）建目录，
        使 600519.SH / 600519 / 600519.sh 都命中同一目录（消除分裂）。
        """
        code = canonical_code(ticker)
        d = self.base / code / date_str
        d.mkdir(parents=True, exist_ok=True)
        return d / "l2_scout.json"

    def get(self, ticker: str, date_str: str,
            profile_version: str | None = None) -> dict | None:
        """读缓存；过期（>24h）/缺失/损坏返回 None.

        g1-canonical-run-identity-repair (D1): cache hit 只校验 TTL + profile_version，
        MUST NOT 校验 run_id。run_id 降级为 cache entry 的 provenance 元数据（只写只读不判）。
        - profile_version 不同（规则 bump）→ miss（不复用旧规则 verdict）
        - legacy cache 无 profile_version 字段且调用方传入 profile_version → miss
          （无法证明规则版本兼容，避免新规则 run 静默复用规则版本不明的旧 verdict）
        - 不传 profile_version → 维持原 TTL-only 行为（向后兼容）

        Args:
            ticker: 股票代码
            date_str: 日期字符串（ISO 格式，如 "2026-06-29"）
            profile_version: g1-canonical-run-identity 当前规则版本（可选，传入则校验兼容）

        Returns:
            缓存 dict（含 verdict/confidence/input_snapshot/run_id provenance 等），或 None
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
                cached = json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

        # g1-canonical-run-identity-repair (D1): 只校验 profile_version（cache compatibility guard）。
        # run_id 不参与 hit 判定（降级 provenance）。
        # 调用方传 profile_version 时：
        #   - cache entry 的 profile_version 与之不同 → miss（规则变了）
        #   - cache entry 无 profile_version（legacy）→ miss（无法证明兼容）
        if profile_version is not None:
            if cached.get("profile_version") != profile_version:
                return None
        return cached

    def set(self, ticker: str, date_str: str, result: dict, input_snapshot: dict,
            run_id: str | None = None,
            profile_version: str | None = None,
            input_ticker_set_hash: str | None = None) -> None:
        """原子写缓存（含输入特征快照 + run identity 绑定）.

        Args:
            ticker: 股票代码（canonical_ticker 或纯数字，内部用 canonical_code 归一建目录）
            date_str: 日期字符串（ISO 格式）
            result: LLM 输出结果（verdict/confidence/flags 等）
            input_snapshot: 输入特征快照（pe_ttm/pb/roe_3y 等，既有诊断用途保留）
            run_id: g1-canonical-run-identity 继承自 L1 的 run_id（可选，纯 L2 单跑用 fallback）
            profile_version: g1-canonical-run-identity 继承的规则版本
            input_ticker_set_hash: g1-canonical-run-identity 输入集合 hash

        缓存结构：
        {
            "verdict": ...,
            "confidence": ...,
            "one_liner": ...,
            "red_flags": [...],
            "green_flags": [...],
            "anti_trap_flags": [...],
            "input_snapshot": {...},
            "timestamp": "2026-06-29T10:30:00",
            "run_id": ...,          # g1-canonical-run-identity
            "profile_version": ...,
            "input_ticker_set_hash": ...
        }
        """
        p = self._path(ticker, date_str)
        tmp = p.with_suffix(".tmp")

        cache_data = {
            **result,
            "input_snapshot": input_snapshot,
            "timestamp": datetime.now().isoformat(),
        }
        # g1-canonical-run-identity: 绑定 run identity（仅在调用方传入时写入，
        # 不传则不写该字段——向后兼容既有调用方，task 6 起 scout_batch 会显式传）
        if run_id is not None:
            cache_data["run_id"] = run_id
        if profile_version is not None:
            cache_data["profile_version"] = profile_version
        if input_ticker_set_hash is not None:
            cache_data["input_ticker_set_hash"] = input_ticker_set_hash

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
            # g1-canonical-run-identity: 用 canonical_code 定位目录（与 _path 对齐），
            # 传 600519.SH / 600519 / 600519.sh SHALL 都命中 600519/ 目录。
            ticker_dir = self.base / canonical_code(ticker)
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
