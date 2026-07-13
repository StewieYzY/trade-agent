"""主营构成 fetcher · main_business 维度（f3a §1，D2 决策 (c)，纯数据层零 LLM）.

契约：
  fetch(ticker) -> {
    "code": "600009",
    "by_industry": [{"name","revenue","revenue_ratio","gross_margin"}],   # 按行业
    "by_product":  [...],                                                  # 按产品
    "by_region":   [...],                                                  # 按地区（若有）
    "main_business_text": str,   # 主营业务文本（兜底来源，zyjs_ths）
    "business_scope": str,       # 经营范围（兜底来源，zyjs_ths）
    "report_date": str | None,   # 报告日期（取 zygc_em 最新报告期）
  }

数据源（均 per-symbol，非全市场表，无需 _LazyTable）：
  主选 stock_zygc_em(symbol="SH600009")：东财主营构成，分行业/产品/地区营收占比 + 毛利率
  兜底 stock_zyjs_ths(symbol="600009")：同花顺主营业务/产品类型/经营范围（文本为主，无财务占比）

异常收窄：不 except Exception，只捕获 KeyError/ValueError/AttributeError。
fetch_with_fallback 全失败返 {__error__: True} 不抛（由 dossier 分层 fail-fast 决定阻断）。
"""
from __future__ import annotations

import akshare as ak  # type: ignore

from .base import BaseFetcher
from ..lib.market_router import parse_ticker
from ..lib.utils import to_float as _to_float


# 分类类型 → 输出键
_CLASS_TYPE_MAP = {
    "按行业": "by_industry",
    "按产品": "by_product",
    "按地区": "by_region",
}


def _zygc_symbol(ticker: str) -> str:
    """stock_zygc_em 需要 SH/SZ 前缀 + 6 位代码（如 'SH600009'）.

    parse_ticker("600009") → full="600009.SH"，取后缀做前缀。
    """
    ti = parse_ticker(ticker)
    ex = ti.full.split(".")[-1] if "." in ti.full else "SH"
    return f"{ex}{ti.code}"


def _parse_zygc(df) -> dict:
    """stock_zygc_em DataFrame → 分行业/产品/地区 营收占比结构."""
    out: dict[str, list] = {}
    report_date = None
    if df is None or len(df) == 0:
        raise KeyError("stock_zygc_em empty")
    # 找报告日期列（取最新一行）
    date_col = next((c for c in df.columns if "报告日期" in str(c) or "报告期" in str(c)), None)
    if date_col is not None:
        dates = df[date_col].dropna().astype(str).tolist()
        report_date = max(dates) if dates else None

    type_col = next((c for c in df.columns if "分类类型" in str(c)), None)
    name_col = next((c for c in df.columns if "主营构成" in str(c) and "类型" not in str(c)), None)
    rev_col = next((c for c in df.columns if "主营收入" in str(c)), None)
    ratio_col = next((c for c in df.columns if "收入比例" in str(c)), None)
    gm_col = next((c for c in df.columns if "毛利率" in str(c)), None)

    if type_col is None or name_col is None:
        raise KeyError("stock_zygc_em missing 分类类型/主营构成 columns")

    for _, row in df.iterrows():
        ctype = str(row[type_col]) if type_col in df.columns else ""
        out_key = None
        for prefix, key in _CLASS_TYPE_MAP.items():
            if prefix in ctype:
                out_key = key
                break
        if out_key is None:
            continue
        out.setdefault(out_key, []).append({
            "name": str(row[name_col]),
            "revenue": _to_float(row[rev_col]) if rev_col in df.columns else None,
            "revenue_ratio": _to_float(row[ratio_col]) if ratio_col in df.columns else None,
            "gross_margin": _to_float(row[gm_col]) if gm_col in df.columns else None,
        })
    return {"breakdown": out, "report_date": report_date}


def _fallback_zyjs_ths(code: str) -> dict:
    """兜底：stock_zyjs_ths 主营业务/产品类型/经营范围（文本为主）."""
    df = ak.stock_zyjs_ths(symbol=code)
    if df is None or len(df) == 0:
        raise KeyError(f"stock_zyjs_ths empty for {code}")
    r = df.iloc[0]
    biz_col = next((c for c in df.columns if "主营业务" in str(c)), None)
    scope_col = next((c for c in df.columns if "经营范围" in str(c)), None)
    ptype_col = next((c for c in df.columns if "产品类型" in str(c)), None)
    return {
        "code": code,
        "main_business_text": str(r[biz_col]) if biz_col else None,
        "product_type": str(r[ptype_col]) if ptype_col else None,
        "business_scope": str(r[scope_col]) if scope_col else None,
    }


class MainBusinessFetcher(BaseFetcher):
    dim = "main_business"

    def fetch(self, ticker: str) -> dict:
        """主选 stock_zygc_em，分行业/产品/地区营收占比."""
        # ticker 可能是 600009 或 600009.SH，统一取 6 位代码
        code = parse_ticker(ticker).code
        df = ak.stock_zygc_em(symbol=_zygc_symbol(ticker))
        parsed = _parse_zygc(df)
        breakdown = parsed["breakdown"]
        if not breakdown:
            raise KeyError(f"stock_zygc_em no breakdown rows for {code}")
        result = {"code": code, "report_date": parsed["report_date"]}
        result.update(breakdown)
        return result

    fallback_providers = [_fallback_zyjs_ths]
