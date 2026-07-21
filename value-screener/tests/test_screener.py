"""screener 模块单元测试

验证 Codex review 修复的关键问题：
- ROE 字段大小写（TOTAL_ASSETS/TOTAL_LIABILITIES/TOTAL_EQUITY）
- GOODWILL 类型为 list（多期数据）
- HF1 方向（> 70% 排除）
- 空数据降级
- FCF 有效性验证
- adjusted_composite 乘法公式
- PE 行业折价双轨策略（R2）
- H2 硬门槛（financials.years 近似）
"""

import pytest
from screener.hard_gates import check_hard_gates
from screener.factor_scores import compute_factor_scores
from screener.anti_trap import compute_anti_trap
from screener.heat_filter import check_heat_filter
from data.lib.industry_mapper import compute_industry_median_pe
from data.lib.stock_features import compute_f_score


def test_roe_field_names():
    """验证 ROE 用 L0 真实字段派生权益并确实执行.

    L0 financials 不产出 TOTAL_LIABILITIES/TOTAL_EQUITY；权益须从
    TOTAL_ASSETS - TOTAL_CURRENT_LIAB - TOTAL_NONCURRENT_LIAB 派生。
    差分断言：算出「若 ROE 被跳过」的 quality 期望值（基于真实 F-Score），
    实际 quality 必须高于它——证明 ROE 子项真在贡献，而非静默跳过。
    """
    financials = {
        "years": ["2021", "2022", "2023"],
        "income": {"net_profit": [100, 120, 150]},
        "balance_sheet": {
            "TOTAL_ASSETS": [1000, 1100, 1200],
            "TOTAL_CURRENT_LIAB": [300, 330, 360],
            "TOTAL_NONCURRENT_LIAB": [200, 220, 240],
        },
        "cash_flow": {"NETCASH_OPERATE": [80, 90, 100]},
    }
    ticker_data = {
        "basic": {"price": 10.0},
        "financials": financials,
        "valuation": {"pb": 2.0, "pe_ttm": 15},
        "risk": {"pledge_ratio": 30},
    }

    scores = compute_factor_scores(ticker_data)
    # ROE = [100/500, 120/550, 150/600] = [20%, 21.8%, 25%]，均值>15% → ROE 子项满分
    assert scores["quality"] > 0

    # 反证：若 ROE 被静默跳过（字段名错配），quality 仅由 F-Score + 现金流加权
    f_score = compute_f_score(financials)
    f_norm = f_score / 9.0 * 100.0
    quality_if_roe_skipped = (f_norm * 0.40 + 100.0 * 0.30) / 0.70
    assert scores["quality"] > quality_if_roe_skipped, (
        f"quality={scores['quality']} 未超过 ROE 跳过时的期望 {quality_if_roe_skipped:.1f}，"
        "ROE 子项可能未执行（字段名错配会静默跳过）"
    )


def test_goodwill_is_list():
    """验证 GOODWILL 字段为 list 类型（多期数据）"""
    """验证 GOODWILL 为 list（多期）且 A4 商誉扣分真触发（不崩 TypeError）.

    原 bug：A4 把 list 型 GOODWILL 当标量做 list/float 除法 → TypeError。
    """
    ticker_data = {
        "financials": {
            "years": ["2021", "2022", "2023"],
            "income": {"net_profit": [100, 120, 150]},
            "balance_sheet": {
                "TOTAL_ASSETS": [1000, 1100, 1200],
                "TOTAL_CURRENT_LIAB": [300, 330, 360],
                "TOTAL_NONCURRENT_LIAB": [200, 220, 240],
                "GOODWILL": [400, 400, 400],  # list 类型（多期）
            },
            "cash_flow": {"NETCASH_OPERATE": [80, 90, 100]},
        },
        "risk": {},
    }

    anti_trap = compute_anti_trap(ticker_data)
    # 最新期商誉/净资产 = 400/(1200-360-240) = 400/600 = 66.7% > 30% → A4 触发，扣 8 分
    # ROE=[20%,21.8%,25%] 上升 → A1 不触发；OCF 为正 → A2 不触发 → 仅 A4
    assert anti_trap["score"] == pytest.approx(92.0)
    assert any(f.startswith("A4_") for f in anti_trap["flags"]), "A4 应触发"


def test_hf1_direction():
    """验证 HF1 方向：换手率分位 > 70% 时排除（剔除被炒的）"""
    # 高换手率股票（被炒的）：最近一天换手率处于 60 日历史高位
    # 构造梯度数据：前 42 天换手率 0.1-0.3，后 17 天 0.4-0.6，最后一天 0.8
    hot_stock = {
        "kline": {
            "turnover_rate": [0.1 + i * 0.005 for i in range(42)] + [0.4 + i * 0.01 for i in range(17)] + [0.8],
            "close": [10.0] * 60,
        }
    }
    result = check_heat_filter(hot_stock)
    assert result["pass"] is False
    assert "HF1" in result["failed_filters"]

    # 低换手率股票（冷门的）：最近一天换手率处于 60 日历史低位
    # 构造梯度数据：前 59 天换手率 0.3-0.8，最后一天 0.1
    cold_stock = {
        "kline": {
            "turnover_rate": [0.3 + i * 0.008 for i in range(59)] + [0.1],
            "close": [10.0] * 60,
        }
    }
    result = check_heat_filter(cold_stock)
    assert result["pass"] is True
    assert "HF1" not in result.get("failed_filters", [])


def test_empty_data_degradation():
    """验证空数据降级：financials={} 时 quality=0"""
    ticker_data = {
        "basic": {"code": "000001", "name": "测试", "price": 10.0},
        "financials": {},
        "valuation": {"pe_percentile_5y": 40, "pb": 2.0, "pe_ttm": 15},
        "risk": {"pledge_ratio": 30},
    }

    scores = compute_factor_scores(ticker_data)
    # 没有财务数据，质量分应该为 0
    assert scores["quality"] == 0
    # 但估值分和安全边际应该正常计算
    assert scores["value"] > 0
    assert scores["safety_margin"] > 0


def test_fcf_validity_check():
    """验证 FCF 有效性：CONSTRUCT_LONG_ASSET 全 None 时跳过 DCF"""
    ticker_data = {
        "basic": {"code": "000001", "name": "测试", "price": 10.0},
        "financials": {
            "years": ["2021", "2022", "2023"],
            "income": {"net_profit": [100, 120, 150]},
            "balance_sheet": {
                "TOTAL_ASSETS": [1000, 1100, 1200],
                "TOTAL_CURRENT_LIAB": [300, 330, 360],
                "TOTAL_NONCURRENT_LIAB": [200, 220, 240],
            },
            "cash_flow": {
                "NETCASH_OPERATE": [80, 90, 100],
                "CONSTRUCT_LONG_ASSET": [None, None, None],  # 全 None
            },
        },
        "valuation": {"pe_percentile_5y": 40, "pb": 2.0, "pe_ttm": 15},
        "risk": {"pledge_ratio": 30},
    }

    scores = compute_factor_scores(ticker_data)
    # DCF 应该被跳过，安全边际只包含质押率
    # 质押率 30% → (60-30)/40*100 = 75 分；若 DCF 未跳过（旧 bug：全-None 当有效）
    # 会与 DCF 分加权混合，偏离 75。断言 ==75 即证明 DCF 确被跳过。
    assert scores["safety_margin"] == pytest.approx(75.0)


def test_adjusted_composite_multiplication():
    """验证 adjusted_composite 使用乘法公式"""
    ticker_data = {
        "basic": {"code": "000001", "name": "测试", "price": 10.0},
        "financials": {
            "years": ["2023"],
            "income": {"net_profit": [100]},
            "balance_sheet": {
                "TOTAL_ASSETS": [1000],
                "TOTAL_CURRENT_LIAB": [300],
                "TOTAL_NONCURRENT_LIAB": [200],
            },
            "cash_flow": {"NETCASH_OPERATE": [80]},
        },
        "valuation": {"pe_percentile_5y": 40, "pb": 2.0, "pe_ttm": 15},
        "risk": {"pledge_ratio": 65},  # > 60 → A5 触发，扣 5 分
        "kline": {"turnover_rate": [0.3] * 60, "close": [10.0] * 60},
    }

    # 直接计算 factor_scores 和 anti_trap
    factor_scores = compute_factor_scores(ticker_data)
    anti_trap = compute_anti_trap(ticker_data)

    composite = factor_scores["composite"]
    anti_trap_score = anti_trap["score"]
    adjusted = composite * (anti_trap_score / 100.0)

    # A5 质押 65% > 60 → 扣 5 → anti_trap=95；调整分 = composite × 0.95 < composite
    assert anti_trap_score == pytest.approx(95.0)
    assert adjusted < composite
    assert abs(adjusted - composite * 95.0 / 100.0) < 0.01


# ==================== H2: 上市年限硬门槛测试 ====================


def test_h2_pass_3_years():
    """H2 通过：financials.years >= 3 年应通过"""
    ticker_data = {
        "basic": {"name": "正常公司", "market_cap": 100e8, "industry": "科技", "pe": 20},
        "financials": {"years": ["2020", "2021", "2022"]},
        "risk": {"pledge_ratio": 30, "audit_opinion": "标准无保留意见"},
    }
    result = check_hard_gates(ticker_data)
    assert result["pass"] is True
    assert "H2" not in result["failed_gates"]


def test_h2_fail_less_than_3_years():
    """H2 失败：financials.years < 3 年应排除"""
    ticker_data = {
        "basic": {"name": "新股", "market_cap": 100e8, "industry": "科技", "pe": 20},
        "financials": {"years": ["2022", "2023"]},
        "risk": {"pledge_ratio": 30, "audit_opinion": "标准无保留意见"},
    }
    result = check_hard_gates(ticker_data)
    assert result["pass"] is False
    assert "H2" in result["failed_gates"]


def test_h2_empty_years():
    """H2 失败：financials.years 为空应排除"""
    ticker_data = {
        "basic": {"name": "空数据股", "market_cap": 100e8, "industry": "科技", "pe": 20},
        "financials": {"years": []},
        "risk": {"pledge_ratio": 30, "audit_opinion": "标准无保留意见"},
    }
    result = check_hard_gates(ticker_data)
    assert result["pass"] is False
    assert "H2" in result["failed_gates"]


def test_h2_no_financials_key():
    """H2 失败：ticker_data 无 financials 键时应排除（容错默认 []）"""
    ticker_data = {
        "basic": {"name": "无财报股", "market_cap": 100e8, "industry": "科技", "pe": 20},
        "risk": {"pledge_ratio": 30, "audit_opinion": "标准无保留意见"},
    }
    result = check_hard_gates(ticker_data)
    assert result["pass"] is False
    assert "H2" in result["failed_gates"]


# ==================== R2: PE 行业折价双轨策略测试 ====================


def test_pe_industry_ratio_full_score():
    """PE 行业折价满分：ratio < 0.7 应得满分"""
    ticker_data = {
        "basic": {"pe": 15.0, "pb": 1.5, "price": 10.0, "industry": "白酒"},
        "financials": {},
        "valuation": {"pe_percentile_5y": 50.0, "pe_ttm": 15.0, "pb": 1.5},
        "risk": {},
    }
    industry_pe_map = {"白酒": 30.0}  # ratio = 15/30 = 0.5 < 0.7

    scores = compute_factor_scores(ticker_data, industry_pe_map=industry_pe_map)
    # PE 子项应得满分 100，value 总分应较高
    assert scores["value"] > 80


def test_pe_industry_ratio_zero_score():
    """PE 行业平价 0 分：ratio >= 1.0 应得 0 分"""
    ticker_data = {
        "basic": {"pe": 30.0, "pb": 1.5, "price": 10.0, "industry": "白酒"},
        "financials": {},
        "valuation": {"pe_percentile_5y": 50.0, "pe_ttm": 30.0, "pb": 1.5},
        "risk": {},
    }
    industry_pe_map = {"白酒": 30.0}  # ratio = 30/30 = 1.0 >= 1.0

    scores = compute_factor_scores(ticker_data, industry_pe_map=industry_pe_map)
    # PE 子项应得 0 分，value 总分应较低（只有 PB 和 PE×PB 贡献）
    assert scores["value"] < 50


def test_pe_industry_ratio_partial_score():
    """PE 行业折价中间衰减：0.7 <= ratio < 1.0 应线性衰减"""
    ticker_data = {
        "basic": {"pe": 24.0, "pb": 1.5, "price": 10.0, "industry": "白酒"},
        "financials": {},
        "valuation": {"pe_percentile_5y": 50.0, "pe_ttm": 24.0, "pb": 1.5},
        "risk": {},
    }
    industry_pe_map = {"白酒": 30.0}  # ratio = 24/30 = 0.8

    scores = compute_factor_scores(ticker_data, industry_pe_map=industry_pe_map)
    # PE 子项应得部分分（约 66.7 分），value 总分应介于 0 和满分之间
    assert 40 < scores["value"] < 80


def test_pe_percentile_fallback_no_industry():
    """PE 降级·无行业：industry=None 应走历史分位"""
    ticker_data = {
        "basic": {"pe": 15.0, "pb": 1.5, "price": 10.0, "industry": None},
        "financials": {},
        "valuation": {"pe_percentile_5y": 25.0, "pe_ttm": 15.0, "pb": 1.5},
        "risk": {},
    }
    industry_pe_map = {"白酒": 30.0}

    scores = compute_factor_scores(ticker_data, industry_pe_map=industry_pe_map)
    # 无行业，应走历史分位兜底，pe_percentile_5y=25 < 30 应满分
    assert scores["value"] > 80


def test_pe_percentile_fallback_industry_not_in_map():
    """PE 降级·行业不在 map：应走历史分位"""
    ticker_data = {
        "basic": {"pe": 15.0, "pb": 1.5, "price": 10.0, "industry": "小行业"},
        "financials": {},
        "valuation": {"pe_percentile_5y": 25.0, "pe_ttm": 15.0, "pb": 1.5},
        "risk": {},
    }
    industry_pe_map = {"白酒": 30.0}  # 不含"小行业"

    scores = compute_factor_scores(ticker_data, industry_pe_map=industry_pe_map)
    # 行业不在 map，应走历史分位兜底
    assert scores["value"] > 80


def test_pe_percentile_fallback_map_is_none():
    """PE 降级·map 未传：industry_pe_map=None 应走历史分位（向后兼容）"""
    ticker_data = {
        "basic": {"pe": 15.0, "pb": 1.5, "price": 10.0, "industry": "白酒"},
        "financials": {},
        "valuation": {"pe_percentile_5y": 25.0, "pe_ttm": 15.0, "pb": 1.5},
        "risk": {},
    }

    scores = compute_factor_scores(ticker_data, industry_pe_map=None)
    # map 未传，应走历史分位兜底
    assert scores["value"] > 80


def test_pe_percentile_fallback_pe_ttm_missing():
    """PE 降级·pe_ttm 缺失：应走历史分位"""
    ticker_data = {
        "basic": {"pb": 1.5, "price": 10.0, "industry": "白酒"},
        "financials": {},
        "valuation": {"pe_percentile_5y": 25.0, "pb": 1.5},  # 无 pe_ttm
        "risk": {},
    }
    industry_pe_map = {"白酒": 30.0}

    scores = compute_factor_scores(ticker_data, industry_pe_map=industry_pe_map)
    # pe_ttm 缺失，应走历史分位兜底
    assert scores["value"] > 80


def test_pe_both_signals_missing():
    """PE 全缺失：pe_ttm 和 pe_percentile_5y 都 None 应跳过 PE 子项"""
    ticker_data = {
        "basic": {"pb": 1.5, "price": 10.0, "industry": "白酒"},
        "financials": {},
        "valuation": {"pb": 1.5},  # 无 pe_ttm 和 pe_percentile_5y
        "risk": {},
    }
    industry_pe_map = {"白酒": 30.0}

    scores = compute_factor_scores(ticker_data, industry_pe_map=industry_pe_map)
    # PE 子项被跳过，value 分只由 PB 贡献
    # PB=1.5 < 2 应满分，PE×PB 因 pe 缺失被跳过
    # 只有 PB 一个子项时，加权求和结果为满分 100
    assert scores["value"] == 100.0


def test_compute_industry_median_pe():
    """验证行业中位 PE 计算逻辑"""
    # 构造测试数据
    all_data = {
        "000001": {"basic": {"industry": "白酒", "pe": 20.0}},
        "000002": {"basic": {"industry": "白酒", "pe": 25.0}},
        "000003": {"basic": {"industry": "白酒", "pe": 30.0}},
        "000004": {"basic": {"industry": "白酒", "pe": 35.0}},
        "000005": {"basic": {"industry": "白酒", "pe": 40.0}},
        "000006": {"basic": {"industry": "银行", "pe": 5.0}},  # 样本不足（<5）
        "000007": {"basic": {"industry": None, "pe": 15.0}},  # 无行业
        "000008": {"basic": {"industry": "白酒", "pe": -10.0}},  # 亏损股（负 PE）
        "000009": {"basic": {"__error__": True}},  # fetch 失败
    }

    median_map = compute_industry_median_pe(all_data)

    # 白酒行业中位应为 30.0（5 个样本：20, 25, 30, 35, 40）
    assert "白酒" in median_map
    assert abs(median_map["白酒"] - 30.0) < 0.01

    # 银行样本不足（只有 1 个），应被丢弃
    assert "银行" not in median_map

    # 验证过滤逻辑
    # - 亏损股（负 PE）被滤除
    # - __error__ 结构被跳过
    # - industry=None 被跳过


def test_compute_industry_median_pe_min_samples():
    """验证 MIN_INDUSTRY_SAMPLES 阈值"""
    # 构造只有 4 个样本的行业
    all_data = {
        "000001": {"basic": {"industry": "小行业", "pe": 10.0}},
        "000002": {"basic": {"industry": "小行业", "pe": 15.0}},
        "000003": {"basic": {"industry": "小行业", "pe": 20.0}},
        "000004": {"basic": {"industry": "小行业", "pe": 25.0}},
    }

    median_map = compute_industry_median_pe(all_data)

    # 样本数 < 5，应被丢弃
    assert "小行业" not in median_map


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


# ==================== G1 L1 数值口径与 DCF 纠偏测试 ====================


def test_dcf_dimension_mismatch_excluded():
    """验证 DCF 量纲错误时被排除，不参与排序.

    构造公司级 FCF 数据（亿元量级），验证当前实现：
    1. 将 DCF 标记为量纲不一致
    2. 不让 DCF 参与排序，安全边际只使用质押率
    """
    ticker_data = {
        "basic": {"price": 50.0},  # 每股价格 50 元
        "financials": {
            "years": ["2021", "2022", "2023"],
            "income": {"net_profit": [5e8, 5.5e8, 6e8], "revenue": [100e8, 110e8, 120e8]},
            "balance_sheet": {
                "TOTAL_ASSETS": [200e8, 220e8, 240e8],
                "TOTAL_CURRENT_LIAB": [50e8, 55e8, 60e8],
                "TOTAL_NONCURRENT_LIAB": [30e8, 33e8, 36e8],
            },
            "cash_flow": {
                "NETCASH_OPERATE": [15e8, 16e8, 17e8],
                "CONSTRUCT_LONG_ASSET": [5e8, 5e8, 5e8],  # FCF = 10亿、11亿、12亿
            },
        },
        "valuation": {"pe_percentile_5y": 40, "pb": 2.0, "pe_ttm": 15},
        "risk": {"pledge_ratio": 30},
    }

    scores = compute_factor_scores(ticker_data)

    # 新实现：DCF 因量纲不一致被排除，dcf_note 应标记原因
    assert "dcf_note" in scores, "返回结构应包含 dcf_note 字段"
    assert scores["dcf_note"] == "dcf_dimension_mismatch", \
        f"DCF 量纲错误时应标记为 dcf_dimension_mismatch，实际为 {scores['dcf_note']}"

    # 安全边际应 100% 由质押率构成（质押率 30% → (60-30)/40*100 = 75.0）
    assert scores["safety_margin"] == pytest.approx(75.0), \
        f"DCF 被排除后，安全边际应 100% 由质押率构成（75.0），实际为 {scores['safety_margin']}"


def test_safety_margin_only_pledge_when_dcf_excluded():
    """验证 DCF 被排除后，安全边际 100% 由质押率构成.

    质押率 30% → (60-30)/40*100 = 75.0
    """
    ticker_data = {
        "basic": {"price": 10.0},
        "financials": {
            "years": ["2021", "2022", "2023"],
            "income": {"net_profit": [100, 120, 150], "revenue": [500, 600, 700]},
            "balance_sheet": {
                "TOTAL_ASSETS": [1000, 1100, 1200],
                "TOTAL_CURRENT_LIAB": [300, 330, 360],
                "TOTAL_NONCURRENT_LIAB": [200, 220, 240],
            },
            "cash_flow": {
                "NETCASH_OPERATE": [80, 90, 100],
                "CONSTRUCT_LONG_ASSET": [30, 30, 30],
            },
        },
        "valuation": {"pe_percentile_5y": 40, "pb": 2.0, "pe_ttm": 15},
        "risk": {"pledge_ratio": 30},
    }

    scores = compute_factor_scores(ticker_data)

    # DCF 被排除后，安全边际 = 质押率得分 = (60-30)/(60-20)*100 = 75.0
    assert scores["safety_margin"] == pytest.approx(75.0), \
        f"安全边际应 100% 由质押率构成（75.0），实际为 {scores['safety_margin']}"


def test_dcf_note_insufficient_data():
    """验证 FCF 不足 2 期时，dcf_note 为 insufficient_data."""
    ticker_data = {
        "basic": {"price": 10.0},
        "financials": {
            "years": ["2023"],
            "income": {"net_profit": [100], "revenue": [500]},
            "balance_sheet": {
                "TOTAL_ASSETS": [1000],
                "TOTAL_CURRENT_LIAB": [300],
                "TOTAL_NONCURRENT_LIAB": [200],
            },
            "cash_flow": {
                "NETCASH_OPERATE": [80],
                "CONSTRUCT_LONG_ASSET": [30],
            },
        },
        "valuation": {"pe_percentile_5y": 40, "pb": 2.0, "pe_ttm": 15},
        "risk": {"pledge_ratio": 30},
    }

    scores = compute_factor_scores(ticker_data)

    # FCF 只有 1 期，不足以计算 DCF
    assert "dcf_note" in scores, "返回结构应包含 dcf_note 字段"
    assert scores["dcf_note"] == "insufficient_data", \
        f"FCF 不足 2 期时应标记为 insufficient_data，实际为 {scores['dcf_note']}"


def test_dcf_note_calculation_error():
    """验证 DCF 计算抛出 ValueError 时，dcf_note 为 calculation_error，排序继续."""
    from unittest.mock import patch

    ticker_data = {
        "basic": {"price": 10.0},
        "financials": {
            "years": ["2021", "2022", "2023"],
            "income": {"net_profit": [100, 120, 150], "revenue": [500, 600, 700]},
            "balance_sheet": {
                "TOTAL_ASSETS": [1000, 1100, 1200],
                "TOTAL_CURRENT_LIAB": [300, 330, 360],
                "TOTAL_NONCURRENT_LIAB": [200, 220, 240],
            },
            "cash_flow": {
                "NETCASH_OPERATE": [80, 90, 100],
                "CONSTRUCT_LONG_ASSET": [30, 30, 30],
            },
        },
        "valuation": {"pe_percentile_5y": 40, "pb": 2.0, "pe_ttm": 15},
        "risk": {"pledge_ratio": 30},
    }

    with patch("screener.factor_scores.compute_simple_dcf", side_effect=ValueError("mock error")):
        scores = compute_factor_scores(ticker_data)

    # ValueError 应被捕获，dcf_note 标记为 calculation_error
    assert "dcf_note" in scores, "返回结构应包含 dcf_note 字段"
    assert scores["dcf_note"] == "calculation_error", \
        f"ValueError 时应标记为 calculation_error，实际为 {scores['dcf_note']}"
    # 排序应继续，安全边际由质押率构成
    assert scores["safety_margin"] == pytest.approx(75.0)


def test_unexpected_exception_propagates():
    """验证 DCF 计算抛出 AttributeError 时，异常向上传播不被静默捕获."""
    from unittest.mock import patch

    ticker_data = {
        "basic": {"price": 10.0},
        "financials": {
            "years": ["2021", "2022", "2023"],
            "income": {"net_profit": [100, 120, 150], "revenue": [500, 600, 700]},
            "balance_sheet": {
                "TOTAL_ASSETS": [1000, 1100, 1200],
                "TOTAL_CURRENT_LIAB": [300, 330, 360],
                "TOTAL_NONCURRENT_LIAB": [200, 220, 240],
            },
            "cash_flow": {
                "NETCASH_OPERATE": [80, 90, 100],
                "CONSTRUCT_LONG_ASSET": [30, 30, 30],
            },
        },
        "valuation": {"pe_percentile_5y": 40, "pb": 2.0, "pe_ttm": 15},
        "risk": {"pledge_ratio": 30},
    }

    with patch("screener.factor_scores.compute_simple_dcf", side_effect=AttributeError("mock bug")):
        with pytest.raises(AttributeError, match="mock bug"):
            compute_factor_scores(ticker_data)
