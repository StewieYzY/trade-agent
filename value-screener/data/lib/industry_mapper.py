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


def build_industry_map() -> dict[str, str]:
    """构建全市场 ticker→industry 映射.

    主选：东财 stock_board_industry_name_em + stock_board_industry_cons_em。
    兜底：同花顺 stock_board_industry_name_ths + stock_board_industry_index_ths（行业指数成分）。
    两个源都失败 → 返回空 dict（不阻塞下游，basic.py industry 字段返回 None）。
    """
    # 先查缓存
    cached = _load_cache()
    if cached is not None:
        return cached

    mapping: dict[str, str] = {}

    # 主选：东财
    try:
        import akshare as ak  # type: ignore
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
            except (KeyError, ValueError, AttributeError):
                # 单行业失败不阻塞
                continue
        if mapping:
            _save_cache(mapping)
            return mapping
    except (KeyError, ValueError, AttributeError):
        pass  # 东财整体失败，试同花顺

    # 兜底：同花顺行业板块（stock_board_industry_name_ths 可用）
    # 注意：stock_board_industry_cons_ths 在当前 akshare 版本不存在，
    # stock_board_industry_index_ths 返回指数 K 线不是成分股 → 同花顺兜底不可用。
    # 保留框架，后续 akshare 新增 cons_ths 可直接替换。

    # 全部失败：返回空 dict（不抛，basic.py industry 字段返回 None）
    if mapping:
        _save_cache(mapping)
    return mapping


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
