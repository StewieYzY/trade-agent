"""缓存管理 · CacheManager.

六档 TTL 常量；CacheManager.get/set/is_expired；
原子写 json.dump→.tmp→os.replace；目录 data/cache/{ticker}/{dim}.json。
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

INTRADAY = 5 * 60
DAILY = 2 * 3600
QUARTERLY = 24 * 3600
DAILY_PRICE = 24 * 3600
DAILY_RISK = 24 * 3600
STATIC = 7 * 24 * 3600

_DIM_TTL: dict[str, int] = {
    "basic": DAILY,
    "financials": QUARTERLY,
    "kline": DAILY_PRICE,
    "valuation": DAILY_PRICE,
    "risk": DAILY_RISK,
    "features": QUARTERLY,
    "industry": STATIC,
    "main_business": QUARTERLY,
    "peers": DAILY_PRICE,
    "research": DAILY,
}

_REPORT_SEASON_TTL = 12 * 3600


def _is_report_season() -> bool:
    return time.localtime().tm_mon in (5, 9, 11)


class CacheManager:
    """每只股票每维度独立缓存（cache/{ticker}/{dim}.json）."""

    def __init__(self, base_dir: str | Path = "data/cache"):
        self.base = Path(base_dir)
        self.base.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def normalize_ticker(ticker: str) -> str:
        """统一 normalize ticker key 为纯 6 位数字（去除 .SH / .SZ 后缀）."""
        return ticker.split(".")[0]

    @staticmethod
    def _normalize_ticker(ticker: str) -> str:
        """向后兼容的私有别名；新代码使用 normalize_ticker."""
        return CacheManager.normalize_ticker(ticker)

    def _path(self, ticker: str, dim: str) -> Path:
        """返回缓存路径，不创建目录。读路径和预检必须无副作用。"""
        return self.base / self.normalize_ticker(ticker) / f"{dim}.json"

    def _ttl(self, dim: str) -> int:
        if dim == "financials" and _is_report_season():
            return _REPORT_SEASON_TTL
        return _DIM_TTL.get(dim, DAILY)

    def is_expired(self, ticker: str, dim: str) -> bool:
        """缓存不存在或超过 TTL → True."""
        path = self._path(ticker, dim)
        if not path.exists():
            return True
        return time.time() - path.stat().st_mtime > self._ttl(dim)

    @staticmethod
    def is_valid_payload(dim: str, payload: Any) -> bool:
        """检查 G1 维度的最低本地计算结构合同."""
        if not isinstance(payload, dict) or payload.get("__error__") is True:
            return False
        contracts = {
            "basic": lambda p: all(k in p for k in ("code", "name", "price", "pe", "pb", "market_cap")),
            "financials": lambda p: (
                isinstance(p.get("years"), list)
                and isinstance(p.get("income"), dict)
                and isinstance(p.get("balance_sheet"), dict)
                and isinstance(p.get("cash_flow"), dict)
            ),
            "kline": lambda p: all(
                isinstance(p.get(k), list) and len(p[k]) > 0
                for k in ("dates", "close", "volume", "turnover_rate")
            ),
            "valuation": lambda p: all(
                k in p for k in ("pe_ttm", "pb", "pe_percentile_5y", "pb_percentile_5y")
            ),
            "risk": lambda p: "pledge_ratio" in p and "pledge_status" in p,
        }
        validator = contracts.get(dim)
        if validator is None:
            return isinstance(payload, dict)
        return bool(validator(payload))

    def get(
        self,
        ticker: str,
        dim: str,
        *,
        allow_stale: bool = False,
        validate: bool = False,
    ) -> dict | None:
        """读缓存；默认保持历史语义，受控 stale 读取可显式开启结构校验."""
        path = self._path(ticker, dim)
        if not path.exists():
            return None
        path = self._path(ticker, dim)
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (json.JSONDecodeError, OSError):
            return None
        if validate and not self.is_valid_payload(dim, payload):
            return None
        if not allow_stale and time.time() - path.stat().st_mtime > self._ttl(dim):
            return None
        return payload

    def set(self, ticker: str, dim: str, data: dict) -> None:
        """原子写：json.dump 到 .tmp → os.replace 到目标路径."""
        path = self._path(ticker, dim)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, default=str)
            os.replace(temporary, path)
        except OSError:
            if temporary.exists():
                temporary.unlink(missing_ok=True)
            raise

    def clear(self, ticker: str | None = None, dim: str | None = None) -> int:
        """按 ticker/dim 清理缓存文件，返回删除数."""
        if ticker:
            directory = self.base / self._normalize_ticker(ticker)
            if not directory.exists():
                return 0
            if dim:
                path = directory / f"{dim}.json"
                if path.exists():
                    path.unlink()
                    return 1
                return 0
            count = 0
            for path in directory.glob("*.json"):
                path.unlink()
                count += 1
            return count

        count = 0
        for path in self.base.rglob("*.json"):
            path.unlink()
            count += 1
        return count
