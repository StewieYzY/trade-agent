"""f3a §1.1/1.2: MainBusinessFetcher 单元测试（D2 决策 (c)，纯数据层零 LLM）.

主营构成 fetcher，分产品/行业/地区营收占比。主选 stock_zygc_em（per-symbol），
兜底 stock_zyjs_ths。两个接口均 per-symbol（非全市场表，无需 _LazyTable）。
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.fetchers.fetch_main_business import MainBusinessFetcher


# ── 构造 mock DataFrame（模拟 akshare 真实返回结构）──────────────


def _zygc_em_df() -> pd.DataFrame:
    """模拟 stock_zygc_em 返回：分类类型=按行业/按产品/按地区."""
    return pd.DataFrame([
        # 按行业分类
        {"股票代码": "600009", "报告日期": "2025-12-31", "分类类型": "按行业分类",
         "主营构成": "航空及相关服务收入", "主营收入": 1.255e10, "收入比例": 0.94,
         "主营成本": 9.39e9, "成本比例": 0.97, "主营利润": 3.17e9, "利润比例": 0.86, "毛利率": 0.25},
        {"股票代码": "600009", "报告日期": "2025-12-31", "分类类型": "按行业分类",
         "主营构成": "其他收入", "主营收入": 7.9e8, "收入比例": 0.06,
         "主营成本": 2.86e8, "成本比例": 0.03, "主营利润": 5.06e8, "利润比例": 0.14, "毛利率": 0.64},
        # 按产品分类
        {"股票代码": "600009", "报告日期": "2025-12-31", "分类类型": "按产品分类",
         "主营构成": "航空及相关服务收入", "主营收入": 1.258e10, "收入比例": 0.94,
         "主营成本": None, "成本比例": None, "主营利润": None, "利润比例": None, "毛利率": None},
    ])


def _zyjs_ths_df() -> pd.DataFrame:
    """模拟 stock_zyjs_ths 返回：主营业务/产品类型/产品名称."""
    return pd.DataFrame([{
        "股票代码": "600009",
        "主营业务": "航空运输地面服务及其他相关业务。",
        "产品类型": "航空、相关服务",
        "产品名称": "航空、相关服务",
        "经营范围": "民用机场运营……",
    }])


# ── 主选成功路径 ────────────────────────────────────────────────


class TestMainBusinessFetch:
    def test_fetch_returns_revenue_breakdown(self):
        """主选 stock_zygc_em 成功 → 返回 dict 含分行业/产品营收占比."""
        fetcher = MainBusinessFetcher()
        with patch("data.fetchers.fetch_main_business.ak.stock_zygc_em",
                   return_value=_zygc_em_df()):
            data = fetcher.fetch("600009")
        assert data["code"] == "600009"
        # 应含分行业 + 分产品 营收占比结构
        assert "by_industry" in data or "by_product" in data
        # 行业维度含具体主营构成 + 收入比例
        by_industry = data.get("by_industry", [])
        assert isinstance(by_industry, list)
        assert len(by_industry) >= 1
        first = by_industry[0]
        assert "name" in first
        assert "revenue" in first
        assert "revenue_ratio" in first

    def test_fetch_groups_by_classification_type(self):
        """按行业/产品/地区 三类分类各自分组."""
        fetcher = MainBusinessFetcher()
        with patch("data.fetchers.fetch_main_business.ak.stock_zygc_em",
                   return_value=_zygc_em_df()):
            data = fetcher.fetch("600009")
        # 有按行业 + 按产品两类
        assert "by_industry" in data
        assert "by_product" in data
        assert len(data["by_industry"]) == 2
        assert len(data["by_product"]) == 1

    def test_dim_attribute(self):
        """dim 类属性 = main_business."""
        assert MainBusinessFetcher.dim == "main_business"

    def test_fetch_with_fallback_all_fail_returns_error(self):
        """主选 + 兜底全失败 → 返 {__error__: True} 不抛."""
        fetcher = MainBusinessFetcher()
        with patch("data.fetchers.fetch_main_business.ak.stock_zygc_em",
                   side_effect=KeyError("zygc empty")), \
             patch("data.fetchers.fetch_main_business.ak.stock_zyjs_ths",
                   side_effect=KeyError("zyjs empty")):
            data = fetcher.fetch_with_fallback("600009")
        assert data.get("__error__") is True
        assert data.get("dim") == "main_business"
        assert "main_business" in data.get("error", "")

    def test_fallback_zyjs_ths_when_zygc_fails(self):
        """主选 stock_zygc_em 失败 → 兜底 stock_zyjs_ths 成功 → 返回主营业务文本."""
        fetcher = MainBusinessFetcher()
        with patch("data.fetchers.fetch_main_business.ak.stock_zygc_em",
                   side_effect=KeyError("zygc empty")), \
             patch("data.fetchers.fetch_main_business.ak.stock_zyjs_ths",
                   return_value=_zyjs_ths_df()):
            data = fetcher.fetch_with_fallback("600009")
        # 兜底成功 → 非 __error__
        assert data.get("__error__") is not True
        assert data["code"] == "600009"
        # 兜底来源至少含主营业务描述
        assert "main_business_text" in data or "business_scope" in data

    def test_fetch_empty_df_raises(self):
        """主选返空 DataFrame → 抛 KeyError（由 fetch_with_fallback 转兜底）."""
        fetcher = MainBusinessFetcher()
        empty = pd.DataFrame()
        with patch("data.fetchers.fetch_main_business.ak.stock_zygc_em",
                   return_value=empty), \
             patch("data.fetchers.fetch_main_business.ak.stock_zyjs_ths",
                   return_value=_zyjs_ths_df()):
            data = fetcher.fetch_with_fallback("600009")
        # 兜底成功
        assert data.get("__error__") is not True
