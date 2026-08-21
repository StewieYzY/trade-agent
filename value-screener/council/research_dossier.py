"""L3 结构化研究档案层（f3a §2，D1/D4/D5，纯 Python，零 LLM 调用）.

build_research_dossier(symbol, core_snapshot=None) 组装分层 dossier：
  {
    "core_snapshot": {...21 量化字段...},        # 全员共享（来自 assemble_council_features）
    "research_dossier": {                         # 角色分发
      "main_business": {...分产品/行业/地区营收占比...},
      "peers": {...peer_avg_pe, 行业排名...},
      "capex_proxy": {...CONSTRUCT_LONG_ASSET...},
      "research": {...consensus_eps, target_price, buy_rating_pct, coverage_count...},
      "degraded_fields": [...缺失的降级维度名...],
    },
    "pledge": float | None,                       # 芒格治理代理（从 risk cache 读）
  }

分层 fail-fast（D5）：
  - core_snapshot 含 error → 向上传播 ValueError（不组装 dossier）
  - main_business 缺失 → fail-fast（core+main_business 是核心）
  - peers/research/capex_proxy 缺失 → 降级标注记入 degraded_fields（不阻断）

不污染 L2 快管线：assemble_snapshot 不变，capex/pledge 由 dossier 读已采 cache，不进 input_assembly。
"""
from __future__ import annotations

from council.features import assemble_council_features


def _is_error(data) -> bool:
    """fetch_with_fallback 全失败返 {__error__: True}."""
    return isinstance(data, dict) and data.get("__error__") is True


def _read_cache(ticker: str, dim: str) -> dict | None:
    """从 CacheManager 读已采 cache（financials/risk），miss 返 None.

    复用 risk fetcher 读 financials goodwill 的模式。
    """
    try:
        from data.cache.manager import CacheManager
        cache = CacheManager()
        data = cache.get(ticker, dim)
        if isinstance(data, dict) and not _is_error(data) and "error" not in data:
            return data
    except (KeyError, ValueError, OSError, AttributeError):
        pass
    return None


def _build_capex_proxy(financials: dict | None) -> dict | None:
    """从 financials cache 读 CONSTRUCT_LONG_ASSET，取 [-1] 最新期 + 序列."""
    if not financials:
        return None
    cash_flow = financials.get("cash_flow", {}) or {}
    cla = cash_flow.get("CONSTRUCT_LONG_ASSET", [])
    if not isinstance(cla, list) or not cla:
        return None
    # 过滤 None，取有效值
    valid = [v for v in cla if v is not None]
    if not valid:
        return None
    return {
        "series": valid,
        "latest": valid[-1],
        "years": financials.get("years", []),
    }


def _fetch_main_business(ticker: str) -> dict:
    """调 MainBusinessFetcher.fetch_with_fallback."""
    from data.fetchers.fetch_main_business import MainBusinessFetcher
    return MainBusinessFetcher().fetch_with_fallback(ticker)


def _fetch_peers(ticker: str) -> dict:
    """调 PeersFetcher.fetch_with_fallback."""
    from data.fetchers.fetch_peers import PeersFetcher
    return PeersFetcher().fetch_with_fallback(ticker)


def _fetch_research(ticker: str) -> dict:
    """调 ResearchFetcher.fetch_with_fallback."""
    from data.fetchers.fetch_research import ResearchFetcher
    return ResearchFetcher().fetch_with_fallback(ticker)


def build_research_dossier(
    symbol: str,
    core_snapshot: dict | None = None,
    *,
    retrieved_at: str | None = None,
    now=None,
    stale_after_days: int = 730,
) -> dict:
    """组装分层研究档案（L3 专用结构化研究档案层）.

    Args:
        symbol: 股票代码（如 "600009" 或 "600009.SH"）
        core_snapshot: 21 量化字段 dict。缺省时调 assemble_council_features(symbol) 采集。

    Returns:
        分层 dossier dict（含 core_snapshot + research_dossier + pledge，以及
        fact_contract + quality_status + quality_reasons）。

    Raises:
        ValueError: core_snapshot 不足（insufficient_data）或 main_business 缺失（核心 fail-fast）。
    """
    # 1. core_snapshot：缺省采集，含 error 向上传播 fail-fast
    if core_snapshot is None:
        core_snapshot = assemble_council_features(symbol)
    if not isinstance(core_snapshot, dict) or "error" in core_snapshot:
        # f1 P4 修复保持：传播完整 guard 上下文（critical_fields/financials_floor/missing_ratio
        # + missing_fields + guard_detail + 可操作下一步），便于用户判断重采。
        if isinstance(core_snapshot, dict):
            missing = core_snapshot.get("missing_fields", [])
            guard = core_snapshot.get("guard", "unknown")
            guard_detail = core_snapshot.get("guard_detail", "")
            raise ValueError(
                f"insufficient_data [{guard}]: 缺失字段 {missing}。"
                f"{guard_detail}。再重跑 council。"
            )
        raise ValueError(
            f"core_snapshot insufficient_data: core_snapshot 不是有效 dict（{type(core_snapshot).__name__}）"
        )

    # 2. 读已采 cache（capex + pledge 零成本接入，不新建 fetcher）
    financials = _read_cache(symbol, "financials")
    risk = _read_cache(symbol, "risk")
    pledge = risk.get("pledge_ratio") if isinstance(risk, dict) else None

    # 3. main_business：核心维度，缺失 fail-fast
    main_business = _fetch_main_business(symbol)
    if _is_error(main_business):
        raise ValueError(
            f"main_business fetch failed for {symbol}（core+main_business 是核心，无主营构成不深研）"
        )

    # 4. peers/research/capex_proxy：非核心，缺失降级标注
    degraded_fields: list[str] = []
    if not _is_error(main_business) and not any(
        key in main_business for key in ("by_industry", "by_product", "by_region")
    ):
        # 主营只剩文本兜底，没有可追溯的数值主营构成，必须让 prompt/事实契约
        # 都看到降级，不能当作正常 clean 主营事实展示。
        degraded_fields.append("main_business")

    peers = _fetch_peers(symbol)
    if _is_error(peers):
        degraded_fields.append("peers")
        peers = {"__error__": True, "reason": "peers fetch failed（industry 缺失或 cons_em 空）"}

    research = _fetch_research(symbol)
    if _is_error(research):
        degraded_fields.append("research")
        research = {"__error__": True, "reason": "research fetch failed"}
    elif isinstance(research, dict) and research.get("coverage_count", 0) == 0:
        # 小票无研报：不标 degraded（research 字段存在只是空），但记录 coverage_count=0
        # 注：D5 决策 research 缺失降级；coverage=0 算「有字段但无数据」，仍保留供 agent 引用
        pass

    capex_proxy = _build_capex_proxy(financials)
    if capex_proxy is None:
        degraded_fields.append("capex_proxy")
        capex_proxy = {"__error__": True, "reason": "CONSTRUCT_LONG_ASSET 未采或为空"}

    dossier = {
        "core_snapshot": core_snapshot,
        "research_dossier": {
            "main_business": main_business,
            "peers": peers,
            "capex_proxy": capex_proxy,
            "research": research,
            "degraded_fields": degraded_fields,
        },
        "pledge": pledge,
    }

    from council.fact_grounding import build_fact_contract, derive_quality_status

    fact_contract = build_fact_contract(
        dossier,
        ticker=symbol,
        retrieved_at=retrieved_at,
        now=now,
        stale_after_days=stale_after_days,
        fail_closed=False,
    )
    high_severity_failures = [
        fact
        for fact in fact_contract.get("facts", [])
        if fact.get("severity") == "high"
        and not fact.get("traceable")
    ]
    if high_severity_failures or fact_contract.get("high_severity_invalid_count"):
        from council.fact_grounding import FactContractError

        details = "; ".join(
            f"{fact.get('fact_key')}: {fact.get('reason') or 'untraceable'}"
            for fact in high_severity_failures
        )
        details = details or "; ".join(
            fact_contract.get("high_severity_invalid_reasons", [])
        )
        raise FactContractError(f"high severity facts fail closed: {details}")
    quality_status, quality_reasons = derive_quality_status(fact_contract)
    dossier["fact_contract"] = fact_contract
    dossier["quality_status"] = quality_status
    dossier["quality_reasons"] = quality_reasons
    return dossier
