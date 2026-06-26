"""数据采集共享工具 · 供各 fetcher 复用.

借鉴 UZI data_sources.py（1463 行）的 provider chain + 三级容错模式，
修工程债：except Exception 收窄为 httpx.TimeoutException / KeyError / 具体异常。

本模块只放共享 helper（tencent qt 报价、A 股名称映射）；各维度 fetcher 的
provider chain 在各自 fetcher.fetch_with_fallback 内编排（design.md §1.3）。
"""
from __future__ import annotations

import httpx

_QT_URL = "https://qt.gtimg.cn/q={symbol}"
_HEADERS = {"User-Agent": "Mozilla/5.0"}


def fetch_price_tencent_qt(code6: str, market: str = "A") -> dict:
    """腾讯 qt 逐只报价 → {name, price, pe_ttm?, pb?, market_cap_raw?, ...}.

    兜底 provider（不需 key，UZI 验证过稳定性）。失败返回 {}（不抛），
    异常收窄为 httpx.TimeoutException / httpx.HTTPError。
    """
    if market == "A":
        prefix = "sh" if code6.startswith(("60", "688", "900", "689")) else "sz"
        symbol = f"{prefix}{code6}"
    elif market == "H":
        symbol = f"hk{code6.zfill(5)}"
    elif market == "U":
        symbol = f"us{code6}"
    else:
        return {}
    try:
        r = httpx.get(_QT_URL.format(symbol=symbol), timeout=8.0, headers=_HEADERS)
        if r.status_code != 200:
            return {}
        text = r.content.decode("gbk", errors="replace")
        if "=" not in text or '"' not in text:
            return {}
        content = text.split("=", 1)[1].strip().rstrip(";").strip().strip('"')
        parts = content.split("~")
        if len(parts) < 35:
            return {}

        def _f(idx: int) -> float | None:
            try:
                v = parts[idx].strip()
                return float(v) if v and v != "-" else None
            except (ValueError, IndexError):
                return None

        out: dict = {
            "name": parts[1] if parts[1] else None,
            "price": _f(3),
            "prev_close": _f(4),
            "change_pct": _f(32),
            "high": _f(33),
            "low": _f(34),
        }
        if len(parts) > 39:
            pe = _f(39)
            if pe is not None:
                out["pe"] = pe
        if len(parts) > 45:
            total_mcap_yi = _f(45)
            if total_mcap_yi is not None:
                out["market_cap"] = round(total_mcap_yi * 1e8, 2)
        if len(parts) > 46:
            pb = _f(46)
            if pb is not None:
                out["pb"] = pb
        return {k: v for k, v in out.items() if v is not None}
    except (httpx.TimeoutException, httpx.HTTPError):
        return {}


_A_NAME_MAP: dict[str, str] | None = None


def get_a_share_name_map() -> dict[str, str]:
    """ak.stock_info_a_code_name() → {code: name} 全市场名称映射（懒加载+缓存）.

    供 basic fetcher 兜底与名称解析。异常收窄，失败返回 {}。
    """
    global _A_NAME_MAP
    if _A_NAME_MAP is not None:
        return _A_NAME_MAP
    try:
        import akshare as ak  # type: ignore
        df = ak.stock_info_a_code_name()
        if df is None or len(df) == 0:
            _A_NAME_MAP = {}
            return _A_NAME_MAP
        code_col = next((c for c in df.columns if "代码" in str(c)), df.columns[0])
        name_col = next((c for c in df.columns if "名称" in str(c) or "简称" in str(c)),
                        df.columns[1])
        _A_NAME_MAP = {
            str(r[code_col]).zfill(6): str(r[name_col])
            for _, r in df.iterrows()
        }
    except (KeyError, ValueError, AttributeError):
        _A_NAME_MAP = {}
    return _A_NAME_MAP
