"""watchlist 聚合 — L1/L2/L3 三路产出 → watchlist/{date}.json."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from data.cache.manager import CacheManager
from data.fetchers.valuation import ValuationFetcher
from scout.quality import ScoutCache


def _compute_stage(l2_verdict: str | None, l3_verdict: str | None) -> str:
    """计算 candidate 的 stage 字段.

    规则（design.md 决策 2）：
    - 有 L3 verdict（包括 "unknown"）→ l3
    - L2 deep_dive → l2
    - L2 pass/reject 或无 L2 → l1

    注意：L3 verdict="unknown" 表示 L3 运行过但 verdict 为空（如 null），
    仍标记为 l3 以区分"运行过但失败"和"未运行"。
    """
    if l3_verdict is not None:  # 包括 "unknown"
        return "l3"
    if l2_verdict == "deep_dive":
        return "l2"
    return "l1"


def _read_l1_output(l1_output_file: str | None) -> dict[str, Any]:
    """读取 L1 产出文件，校验存在性和时效性."""
    if not l1_output_file:
        # 尝试从默认位置读取
        default_paths = [
            Path("output/l1_screening.json"),
            Path("l1_screening.json"),
        ]
        for p in default_paths:
            if p.exists():
                l1_output_file = str(p)
                break
        else:
            raise FileNotFoundError(
                "未找到 L1 产出文件，请指定 --l1-file 或先运行 L1 筛选"
            )

    p = Path(l1_output_file)
    if not p.exists():
        raise FileNotFoundError(f"L1 产出文件不存在：{l1_output_file}")

    # 检查时效性（>7 天警告）
    mtime = datetime.fromtimestamp(p.stat().st_mtime).date()
    age_days = (date.today() - mtime).days
    if age_days > 7:
        print(f"⚠️  L1 产出文件已 {age_days} 天未更新，建议重新运行 L1 筛选")

    with p.open(encoding="utf-8") as f:
        return json.load(f)


def _supplement_pe_percentile(
    candidates: list[dict[str, Any]],
    valuation_fetcher: ValuationFetcher | None = None,
    cache_manager: CacheManager | None = None,
) -> list[dict[str, Any]]:
    """对 stage >= l2 的 candidate 补充 pe_percentile_5y 字段.

    规则：
    - stage=l1 的 candidate：pe_percentile_5y=null
    - stage>=l2 的 candidate：先查 CacheManager（dim=valuation），命中直接用；
      miss 则调用 ValuationFetcher.fetch_with_fallback() 并写回缓存
    - fetch 失败：pe_percentile_5y=null，不阻断聚合

    L1 刚跑过时 CacheManager 已有 valuation 缓存，命中率高，实际网络请求少。
    """
    if valuation_fetcher is None:
        valuation_fetcher = ValuationFetcher()
    if cache_manager is None:
        cache_manager = CacheManager()

    for c in candidates:
        stage = c.get("stage", "l1")
        if stage == "l1":
            c["pe_percentile_5y"] = None
            continue

        ticker = c["ticker"]

        # 先查缓存
        cached = cache_manager.get(ticker, "valuation")
        if cached and "pe_percentile_5y" in cached:
            c["pe_percentile_5y"] = cached["pe_percentile_5y"]
            continue

        # 缓存未命中，走网络
        try:
            valuation_data = valuation_fetcher.fetch_with_fallback(ticker)
            if valuation_data and not valuation_data.get("__error__") and "pe_percentile_5y" in valuation_data:
                c["pe_percentile_5y"] = valuation_data["pe_percentile_5y"]
                # 写回缓存供后续复用
                cache_manager.set(ticker, "valuation", valuation_data)
            else:
                c["pe_percentile_5y"] = None
        except (ConnectionError, TimeoutError, OSError) as e:
            print(f"⚠️  {ticker} pe_percentile_5y 补充失败：{e}")
            c["pe_percentile_5y"] = None

    return candidates


def _read_l2_cache(ticker: str, scout_cache: ScoutCache) -> dict[str, Any] | None:
    """读取 ScoutCache 中的 L2 verdict（接受过期缓存）."""
    # 尝试最近 7 天的缓存
    for days_back in range(7):
        d = date.today() - timedelta(days=days_back)
        date_str = d.isoformat()
        cached = scout_cache.get(ticker, date_str)
        if cached:
            return {
                "l2_verdict": cached.get("verdict"),
                "l2_confidence": cached.get("confidence"),
            }
    return None


def _read_l3_output(ticker: str, run_date: str, watchlist_dir: Path) -> dict[str, Any] | None:
    """读取 L3 per-ticker JSON 文件."""
    # 尝试多种文件名模式
    patterns = [
        f"{run_date}_{ticker}.json",
        f"{run_date}_{ticker.replace('.', '_')}.json",
    ]

    for pattern in patterns:
        p = watchlist_dir / pattern
        if p.exists():
            with p.open(encoding="utf-8") as f:
                l3_data = json.load(f)

            # 提取关键字段，null 防御
            return {
                "l3_verdict": l3_data.get("final_verdict", "unknown") or "unknown",
                "l3_conviction": l3_data.get("conviction"),
                "key_variables": l3_data.get("key_variables") or None,
                "consensus_summary": l3_data.get("consensus_summary"),
                "dissent_points": l3_data.get("dissent_points"),
                "pending_verification": l3_data.get("pending_verification"),
            }
    return None


def _check_l3_incomplete(l3_data: dict[str, Any] | None) -> bool:
    """L3 健康检查：判断产出是否不完整.

    规则：L3 文件存在但 conviction/consensus_summary/dissent_points/pending_verification
    全部为 null → l3_incomplete=true
    """
    if not l3_data:
        return False

    null_fields = [
        l3_data.get("l3_conviction") is None,
        l3_data.get("consensus_summary") is None,
        l3_data.get("dissent_points") is None,
        l3_data.get("pending_verification") is None,
    ]
    return all(null_fields)


def aggregate_watchlist(
    run_date: str,
    l1_output_file: str | None = None,
    scout_cache: ScoutCache | None = None,
    watchlist_dir: str | Path = "watchlist",
) -> dict[str, Any]:
    """聚合 L1/L2/L3 三路产出为 watchlist/{date}.json.

    Args:
        run_date: 运行日期（YYYY-MM-DD）
        l1_output_file: L1 产出文件路径（可选，缺省从默认位置读取）
        scout_cache: ScoutCache 实例（可选，缺省创建新实例）
        watchlist_dir: watchlist 输出目录（默认 watchlist/）

    Returns:
        watchlist JSON 结构（符合 §7 子集 + L2/L3 扩展字段）

    Raises:
        FileNotFoundError: L1 产出文件不存在
    """
    if scout_cache is None:
        scout_cache = ScoutCache()

    watchlist_dir = Path(watchlist_dir)
    watchlist_dir.mkdir(parents=True, exist_ok=True)

    # 1. 读取 L1 产出
    l1_data = _read_l1_output(l1_output_file)
    l1_candidates = l1_data.get("candidates", [])

    # 2. 聚合每个 candidate
    candidates = []
    for l1_cand in l1_candidates:
        ticker = l1_cand["ticker"]

        # 读取 L2 缓存
        l2_data = _read_l2_cache(ticker, scout_cache)
        l2_verdict = l2_data["l2_verdict"] if l2_data else None
        l2_confidence = l2_data["l2_confidence"] if l2_data else None

        # 读取 L3 产出
        l3_data = _read_l3_output(ticker, run_date, watchlist_dir)
        l3_verdict = l3_data["l3_verdict"] if l3_data else None
        l3_conviction = l3_data["l3_conviction"] if l3_data else None
        key_variables = l3_data["key_variables"] if l3_data else None

        # 计算 stage
        stage = _compute_stage(l2_verdict, l3_verdict)

        # 构造 candidate 记录
        candidate = {
            "ticker": ticker,
            "name": l1_cand.get("name", ""),
            "stage": stage,
            "l1_score": l1_cand.get("adjusted_composite"),
            "f_score": l1_cand.get("f_score"),
            "pe_ttm": l1_cand.get("pe_ttm"),
            "pe_percentile_5y": None,  # 后续补充
            "pb": l1_cand.get("pb"),
            "pledge_ratio": l1_cand.get("pledge_ratio"),
            "l2_verdict": l2_verdict,
            "l2_confidence": l2_confidence,
            "l3_verdict": l3_verdict,
            "l3_conviction": l3_conviction,
            "key_variables": key_variables,
            "last_updated": run_date,
        }

        # L3 健康检查
        if l3_data and _check_l3_incomplete(l3_data):
            candidate["l3_incomplete"] = True

        candidates.append(candidate)

    # 3. 补充 pe_percentile_5y（仅对 stage >= l2）
    candidates = _supplement_pe_percentile(candidates)

    # 4. 构造 watchlist JSON
    watchlist = {
        "generated_at": datetime.now().isoformat(),
        "l1_candidates": len(candidates),
        "l2_shortlist": sum(1 for c in candidates if c["stage"] in ("l2", "l3")),
        "candidates": candidates,
    }

    # 5. 写入文件
    output_file = watchlist_dir / f"{run_date}.json"
    with output_file.open("w", encoding="utf-8") as f:
        json.dump(watchlist, f, ensure_ascii=False, indent=2)

    print(f"✓ watchlist 聚合完成：{output_file}")
    print(f"  - L1 candidates: {watchlist['l1_candidates']}")
    print(f"  - L2 shortlist: {watchlist['l2_shortlist']}")

    return watchlist
