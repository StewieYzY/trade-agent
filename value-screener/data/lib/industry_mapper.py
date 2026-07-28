"""A 股全市场行业映射 · ticker → industry.

构建策略（主选东财行业板块，兜底同花顺）：
  1. stock_board_industry_name_em() 拿行业列表（~70 个）
  2. 每个行业 stock_board_industry_cons_em(symbol=行业名) 拿成分股代码
  3. 构建 {ticker: industry} dict

缓存：STATIC TTL（7d），首次构建约 2-3 分钟（70 行业 × 2s 延迟），之后缓存复用。
basic.py 通过 _LazyTable 复用此映射，intra-batch 只构建一次。

异常收窄：单行业采集失败不阻塞其他行业，跳过并记录；全部失败返回空 dict。

R2 增强：计算行业中位 PE，支持 L1 估值因子的行业折价策略。
"""
from __future__ import annotations

import json
import random
import time
from pathlib import Path
from statistics import median

from ..cache.manager import STATIC


# R2: 行业中位 PE 计算的最小样本数
MIN_INDUSTRY_SAMPLES = 5


_CACHE_FILE = Path("data/cache/_industry_map.json")


class IndustryMapResult(dict):
    """行业映射结果（dict 子类）+ 失败显式化状态.

    g1-4-data-source-resilience D1: 承接 canonical data-minimum-contract §4
    「industry_mapper 静默空 dict」禁止项。状态绑本 result 对象（→绑
    _lazy_industry._df 实例），每次 loader 调用产新 result（重置），
    reset() 清 _df 连带清状态——不污染下一次 batch。

    status:
    - available: 东财完整成功
    - partial: 部分行业成功（covered_industries / failed_industries 记录）
    - source_failed: 东财全部失败（attempted_sources 记录尝试过的来源）
    """

    def __init__(self, mapping=None, *, status="available",
                 attempted_sources=None, covered_industries=None, failed_industries=None):
        super().__init__(mapping or {})
        self.status = status
        self.attempted_sources = attempted_sources or []
        self.covered_industries = covered_industries or []
        self.failed_industries = failed_industries or []

    def __repr__(self):
        return (f"IndustryMapResult(size={len(self)}, status={self.status}, "
                f"attempted_sources={self.attempted_sources}, "
                f"covered={len(self.covered_industries)}, failed={len(self.failed_industries)})")


def _load_cache() -> dict | None:
    """读缓存；过期/损坏返回 None."""
    if not _CACHE_FILE.exists():
        return None
    try:
        age = time.time() - _CACHE_FILE.stat().st_mtime
        if age > STATIC:
            return None
        with _CACHE_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _save_cache(mapping: dict) -> None:
    """原子写缓存."""
    _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _CACHE_FILE.with_suffix(".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(mapping, f, ensure_ascii=False)
        import os
        os.replace(tmp, _CACHE_FILE)
    except OSError:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def build_industry_map() -> "IndustryMapResult":
    """构建全市场 ticker→industry 映射.

    g1-4-data-source-resilience D1: 不再静默返空 dict。东财失败时显式标
    source_failed（带 attempted_sources + 失败原因），部分行业成功标 partial
    （covered/failed_industries）。承接 canonical data-minimum-contract §4
    「industry_mapper 静默空 dict」禁止项。不硬编码未经验证的 fallback 源。

    返回 IndustryMapResult（dict 子类，.get(ticker) 兼容，可选读 status）。
    """
    # 先查缓存
    cached = _load_cache()
    if cached is not None:
        # 缓存命中：重建为 IndustryMapResult（cache 存普通 dict，status 丢失）
        return IndustryMapResult(cached, status="available", attempted_sources=["cache"])

    mapping: dict[str, str] = {}
    covered_industries: list[str] = []
    failed_industries: list[str] = []
    attempted_sources: list[str] = []

    # 主选：东财
    try:
        import akshare as ak  # type: ignore
        attempted_sources.append("eastmoney")
        boards = ak.stock_board_industry_name_em()
        for i, row in boards.iterrows():
            industry = str(row["板块名称"])
            # 反爬：请求间随机延迟 1.5-3s（行业列表接口限流严格）
            time.sleep(random.uniform(1.5, 3.0))
            try:
                cons = ak.stock_board_industry_cons_em(symbol=industry)
                if cons is not None and len(cons) > 0:
                    code_col = next((c for c in cons.columns if "代码" in str(c)), None)
                    if code_col:
                        for code in cons[code_col].tolist():
                            mapping[str(code).zfill(6)] = industry
                    covered_industries.append(industry)
                else:
                    failed_industries.append(industry)
            except (KeyError, ValueError, AttributeError):
                # 单行业失败不阻塞，但显式记录
                failed_industries.append(industry)
                continue
        if mapping:
            _save_cache(mapping)
            status = "available" if not failed_industries else "partial"
            return IndustryMapResult(mapping, status=status,
                                     attempted_sources=attempted_sources,
                                     covered_industries=covered_industries,
                                     failed_industries=failed_industries)
    except (KeyError, ValueError, AttributeError, ImportError) as e:
        # 东财整体失败：显式标 source_failed，不静默返空 dict
        if not attempted_sources:
            attempted_sources.append("eastmoney")
        return IndustryMapResult({}, status="source_failed",
                                 attempted_sources=attempted_sources,
                                 failed_industries=failed_industries)

    # 兜底：同花顺行业板块（stock_board_industry_cons_ths 在当前 akshare 不存在，
    # 不硬编码未经验证的 fallback）。东财部分成功但 mapping 空也归 source_failed。
    if mapping:
        _save_cache(mapping)
        return IndustryMapResult(mapping, status="partial" if failed_industries else "available",
                                  attempted_sources=attempted_sources,
                                  covered_industries=covered_industries,
                                  failed_industries=failed_industries)
    return IndustryMapResult({}, status="source_failed",
                             attempted_sources=attempted_sources or ["eastmoney"],
                             failed_industries=failed_industries)


def get_industry(ticker: str, mapping: dict | None = None) -> str | None:
    """查单只股票行业；mapping 为 None 时自动构建."""
    if mapping is None:
        mapping = build_industry_map()
    return mapping.get(ticker)


def compute_industry_median_pe(all_data: dict[str, dict]) -> dict[str, float]:
    """计算各行业 PE 中位数.

    Args:
        all_data: {ticker: {"basic": {...}, ...}} 全市场采集数据

    Returns:
        {industry: median_pe} 行业 PE 中位数映射，仅包含样本数 >= MIN_INDUSTRY_SAMPLES 的行业

    过滤逻辑：
    - 跳过 fetch 失败（basic 含 __error__）
    - 跳过 industry=None
    - 跳过 pe <= 0（亏损股）
    - 样本数 < MIN_INDUSTRY_SAMPLES 的行业被丢弃
    """
    industry_pe_map = {}

    for ticker, ticker_data in all_data.items():
        basic = ticker_data.get("basic", {})

        # 跳过 fetch 失败
        if "__error__" in basic:
            continue

        industry = basic.get("industry")
        pe = basic.get("pe")

        # 跳过无行业或 PE 无效
        if industry is None or pe is None or pe <= 0:
            continue

        # 收集 PE 数据
        if industry not in industry_pe_map:
            industry_pe_map[industry] = []
        industry_pe_map[industry].append(pe)

    # 计算中位数，过滤样本数不足的行业
    result = {}
    for industry, pe_list in industry_pe_map.items():
        if len(pe_list) >= MIN_INDUSTRY_SAMPLES:
            result[industry] = median(pe_list)

    return result
