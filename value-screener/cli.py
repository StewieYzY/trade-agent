"""value-screener CLI entry point.

子命令（design.md §6.2, tasks 11.x）：
  fetch      采集单只股票单维度数据，输出 JSON
  batch      从文件读 ticker 列表，批量采集全维度
  cache-clear 按 ticker/dim 清理缓存文件
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(help="value-screener 数据采集 CLI")

# L4 监控层子命令组（tasks 1.2 占位，后续 task 7.x 实现）
monitor_app = typer.Typer(name="monitor", help="L4 监控层：weekly 主循环、watchlist 聚合、diff、历史轨迹")
app.add_typer(monitor_app)


@monitor_app.command(name="weekly")
def monitor_weekly(
    l1_file: str = typer.Option(None, "--l1-file", help="L1 产出文件路径"),
    output: str = typer.Option(None, "--output", help="周报 JSON 输出路径"),
    force_l2: bool = typer.Option(False, "--force-l2", help="强制重跑 L2（忽略 diff 阈值）"),
    force_l3: bool = typer.Option(False, "--force-l3", help="强制重跑 L3（忽略 diff 阈值）"),
):
    """L4 主循环：聚合 → diff → 触发 L2/L3 → 催化检测 → 提醒."""
    import asyncio
    from monitor.weekly import run_weekly

    if force_l2:
        typer.echo("⚠️  强制重跑 L2 模式：将忽略 diff 阈值，成本可能上升")
    if force_l3:
        typer.echo("⚠️  强制重跑 L3 模式：将忽略 diff 阈值，成本显著上升")
        # 估算成本：假设 20 只股票，每只 ¥40
        estimated_cost = 20 * 40
        if not typer.confirm(f"预估成本 ¥{estimated_cost}（20 只 × ¥40），是否继续？"):
            typer.echo("已取消")
            raise typer.Exit()

    report = asyncio.run(run_weekly(
        l1_output_file=l1_file,
        force_l2=force_l2,
        force_l3=force_l3,
    ))

    if output:
        Path(output).write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        typer.echo(f"周报已写入：{output}")


@monitor_app.command(name="watchlist")
def monitor_watchlist(
    date: str = typer.Option(None, "--date", help="指定日期（YYYY-MM-DD），缺省最新"),
    json_output: bool = typer.Option(False, "--json", help="输出原始 JSON"),
):
    """查看最新或指定日期 watchlist."""
    from monitor.diff import get_latest_watchlist

    watchlist_dir = Path("watchlist")

    if date:
        file_path = watchlist_dir / f"{date}.json"
        if not file_path.exists():
            raise typer.BadParameter(f"watchlist 不存在：{date}")
        with file_path.open(encoding="utf-8") as f:
            data = json.load(f)
    else:
        result = get_latest_watchlist(watchlist_dir)
        if not result:
            raise typer.BadParameter("watchlist 目录为空，请先运行 monitor weekly")
        date, data = result

    if json_output:
        typer.echo(json.dumps(data, ensure_ascii=False))
    else:
        typer.echo(f"📋 Watchlist {date}")
        typer.echo(f"  L1 candidates: {data.get('l1_candidates', 0)}")
        typer.echo(f"  L2 shortlist: {data.get('l2_shortlist', 0)}")
        typer.echo(f"  生成时间：{data.get('generated_at', 'unknown')}")
        typer.echo(f"\nCandidates (top 10):")
        for c in data.get("candidates", [])[:10]:
            typer.echo(f"  {c['ticker']} [{c.get('stage', 'l1')}] score={c.get('l1_score', 'N/A')}")


@monitor_app.command(name="diff")
def monitor_diff(
    date: str = typer.Option(None, "--date", help="指定日期（YYYY-MM-DD），缺省最新"),
):
    """查看最新或指定日期 diff 报告."""
    from monitor.diff import get_latest_watchlist, get_previous_watchlist, compute_diff

    watchlist_dir = Path("watchlist")

    if date:
        file_path = watchlist_dir / f"{date}.json"
        if not file_path.exists():
            raise typer.BadParameter(f"watchlist 不存在：{date}")
        with file_path.open(encoding="utf-8") as f:
            current = json.load(f)
        current_date = date
    else:
        result = get_latest_watchlist(watchlist_dir)
        if not result:
            raise typer.BadParameter("watchlist 目录为空")
        current_date, current = result

    previous = get_previous_watchlist(current_date, watchlist_dir)
    diff_report = compute_diff(current, previous)

    typer.echo(f"📊 Diff Report {current_date}")
    if diff_report.get("first_run"):
        typer.echo("  首次运行，无历史对比")
    else:
        typer.echo(f"  新增：{len(diff_report['added'])}")
        typer.echo(f"  移除：{len(diff_report['removed'])}")
        typer.echo(f"  l1_score 变化：{len(diff_report['l1_score_changed'])}")
        typer.echo(f"  stage 升级：{len(diff_report['stage_upgraded'])}")
        typer.echo(f"  stage 降级：{len(diff_report['stage_downgraded'])}")
        typer.echo(f"  verdict 变化：{len(diff_report['verdict_changed'])}")
        typer.echo(f"  估值触及低位：{len(diff_report['valuation_low'])}")
        typer.echo(f"\n触发条件：")
        typer.echo(f"  L2 重评估：{len(diff_report['l2_triggers'])} 只")
        typer.echo(f"  L3 深研：{len(diff_report['l3_triggers'])} 只")


@monitor_app.command(name="history")
def monitor_history(
    ticker: str = typer.Argument(..., help="股票代码（如 600519.SH）"),
    date_from: str = typer.Option(None, "--from", help="起始日期（YYYY-MM-DD）"),
    date_to: str = typer.Option(None, "--to", help="截止日期（YYYY-MM-DD）"),
):
    """查询单只股票历史轨迹."""
    from monitor.diff import history

    records = history(ticker, date_from, date_to)

    if not records:
        typer.echo(f"无历史记录：{ticker}")
        return

    typer.echo(f"📈 {ticker} 历史轨迹")
    typer.echo("")
    typer.echo("| 日期 | l1_score | stage | l3_verdict | pe_percentile |")
    typer.echo("|------|----------|-------|------------|---------------|")
    for r in records:
        typer.echo(
            f"| {r['date']} | {r.get('l1_score', 'N/A')} | "
            f"{r.get('stage', 'l1')} | {r.get('l3_verdict', 'N/A')} | "
            f"{r.get('pe_percentile_5y', 'N/A')} |"
        )


def _get_fetcher(dim: str):
    from data.fetchers.basic import BasicFetcher
    from data.fetchers.financials import FinancialsFetcher
    from data.fetchers.kline import KlineFetcher
    from data.fetchers.valuation import ValuationFetcher
    from data.fetchers.risk import RiskFetcher
    table = {
        "basic": BasicFetcher,
        "financials": FinancialsFetcher,
        "kline": KlineFetcher,
        "valuation": ValuationFetcher,
        "risk": RiskFetcher,
    }
    if dim not in table:
        raise typer.BadParameter(f"unknown dim: {dim}，可选 {list(table.keys())}")
    return table[dim]()


@app.command()
def fetch(ticker: str, dim: str = "basic"):
    """采集单只股票指定维度数据，输出 JSON 并写入缓存."""
    from data.cache.manager import CacheManager
    fetcher = _get_fetcher(dim)
    data = fetcher.fetch_with_fallback(ticker)

    # 成功时写入缓存（与 batch 行为一致）
    if isinstance(data, dict) and not data.get("__error__"):
        cache = CacheManager()
        cache.set(ticker, dim, data)

    typer.echo(json.dumps(data, ensure_ascii=False, default=str, indent=2))


@app.command()
def batch(tickers_file: str, dims: str = "basic,financials,kline,valuation,risk"):
    """从文件读 ticker 列表（每行一个），批量采集全维度."""
    from data.lib.batch_fetcher import BatchFetcher
    p = Path(tickers_file)
    if not p.exists():
        raise typer.BadParameter(f"tickers file not found: {tickers_file}")
    tickers = [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    dim_list = [d.strip() for d in dims.split(",") if d.strip()]
    bf = BatchFetcher()
    results = bf.fetch_all(tickers, dim_list)
    typer.echo(json.dumps(results, ensure_ascii=False, default=str, indent=2))


@app.command(name="cache-clear")
def cache_clear(ticker: str = typer.Option(None, "--ticker", help="指定 ticker，缺省清全部"),
                dim: str = typer.Option(None, "--dim", help="指定维度，缺省清该 ticker 全部维度")):
    """按 ticker/dim 清理缓存文件."""
    from data.cache.manager import CacheManager
    cm = CacheManager()
    n = cm.clear(ticker=ticker, dim=dim)
    typer.echo(json.dumps({"deleted": n, "ticker": ticker, "dim": dim}, ensure_ascii=False))


@app.command()
def screen(
    tickers: str = typer.Option(None, "--tickers", help="ticker 列表文件路径（每行一个），缺省从全市场快照取"),
    output: str = typer.Option(None, "--output", help="输出 JSON 文件路径，缺省输出到 stdout"),
    debug: bool = typer.Option(False, "--debug", help="调试模式，输出每道漏斗的中间结果"),
    exclude_cyclicals: bool = typer.Option(False, "--exclude-cyclicals", help="排除周期股"),
):
    """L1 量化筛选：全市场 A 股 → ~200 只候选池."""
    from data.fetchers.basic import BasicFetcher

    # 1. 确定 ticker 列表
    if tickers:
        p = Path(tickers)
        if not p.exists():
            raise typer.BadParameter(f"tickers file not found: {tickers}")
        ticker_list = [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    else:
        # 从全市场快照取所有代码
        bf = BasicFetcher()
        spot = bf._lazy_spot.get()
        if spot is None or len(spot) == 0:
            raise typer.BadParameter("全市场快照为空，无法获取 ticker 列表")
        code_col = next((c for c in spot.columns if "代码" in str(c)), spot.columns[0])
        ticker_list = [str(c).zfill(6) for c in spot[code_col].tolist()]

    typer.echo(f"开始筛选 {len(ticker_list)} 只股票...")

    # 2. 调用 screen_a_shares
    from screener.main import screen_a_shares
    result = screen_a_shares(ticker_list, exclude_cyclicals=exclude_cyclicals)

    # 3. 输出结果
    output_json = json.dumps(result, ensure_ascii=False, default=str, indent=2)

    if output:
        Path(output).write_text(output_json, encoding="utf-8")
        typer.echo(f"结果已写入到 {output}")
    else:
        typer.echo(output_json)

    # 4. 调试模式输出统计
    if debug:
        stats = result.get("stats", {})
        typer.echo("\n=== 筛选统计 ===")
        typer.echo(f"总数: {stats.get('total', 0)}")
        typer.echo(f"通过 Hard Gates: {stats.get('after_hard_gates', 0)}")
        typer.echo(f"通过 Factor Scores (top 300): {stats.get('after_factors', 0)}")
        typer.echo(f"通过 Heat Filter: {stats.get('after_heat_filter', 0)}")
        typer.echo(f"\nHard Gates 排除统计:")
        for gate, count in stats.get("excluded_by_gates", {}).items():
            typer.echo(f"  {gate}: {count}")


@app.command()
def scout(
    input_file: Annotated[str, typer.Option("--input", help="L1 输出 JSON 文件路径（S5 schema）")],
    output: Annotated[str | None, typer.Option("--output", help="L2 短名单 JSON 输出路径，缺省输出到 stdout")] = None,
    force: Annotated[bool, typer.Option("--force", help="跳过缓存，强制重新调用 LLM")] = False,
):
    """L2 Scout Agent: L1 候选池 ~200 只 → ~20 只 deep_dive 短名单.

    环境变量（必填）：
    - LLM_API_KEY: LLM API 密钥
    - LLM_API_BASE: LLM API base URL（如 https://api.openai.com）
    - LLM_MODEL: 模型名称（如 gpt-4o-mini）

    成本估算：~¥0.01/只，200 只 ~¥2/轮（80% 缓存命中后 ~¥0.4/轮）。
    Top-20 cap 确保 L3 成本在 AD-03 预算内（¥400-1200）。
    """
    import asyncio
    from pathlib import Path

    # 1. 读取 L1 输出
    p = Path(input_file)
    if not p.exists():
        raise typer.BadParameter(f"L1 output file not found: {input_file}")

    try:
        l1_data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        raise typer.BadParameter(f"Failed to read L1 output: {e}")

    candidates = l1_data.get("candidates", [])
    if not candidates:
        raise typer.BadParameter("L1 output has no candidates")

    typer.echo(f"读取 L1 输出：{len(candidates)} 只候选")

    # 2. 调用 scout_batch（异步，返回 (shortlist, usage_summary)，P1 修复）
    from scout.batch import scout_batch
    shortlist, usage_summary = asyncio.run(scout_batch(candidates, force=force))

    # 3. 输出结果（P1 修复：shortlist + usage_summary 一起写，供成本分析用全量调用数据）
    output_payload = {"shortlist": shortlist, "usage_summary": usage_summary}
    output_json = json.dumps(output_payload, ensure_ascii=False, indent=2)

    if output:
        Path(output).write_text(output_json, encoding="utf-8")
        typer.echo(f"结果已写入到 {output}")
    else:
        typer.echo(output_json)

    typer.echo(f"L2 筛选完成：{len(shortlist)}/{len(candidates)} 只 deep_dive（top-20 cap）")

    # f1-deviation-fix §7 / P1 修复：AD-03 成本实测——汇总**所有** LLM 调用（非仅 deep_dive）
    call_count = usage_summary.get("call_count", 0)
    cache_hits = usage_summary.get("cache_hits", 0)
    total_prompt = usage_summary.get("prompt_tokens", 0)
    total_completion = usage_summary.get("completion_tokens", 0)
    total_tokens = usage_summary.get("total_tokens", 0)
    typer.echo(
        f"Token usage（本次实跑）：LLM 调用 {call_count} 次，cache 命中 {cache_hits} 次，"
        f"prompt={total_prompt}，completion={total_completion}，total={total_tokens}"
    )
    if total_tokens:
        est_cost = total_tokens / 1000 * 0.001
        typer.echo(f"  费用估算：≈¥{est_cost:.4f}（按 ¥0.001/1k token）"
                   f"；等效全量调用数 = {call_count + cache_hits}")


def _normalize_ticker(ticker: str) -> str:
    """规范化 ticker：6 位数字自动补后缀.

    规则（A 股惯例）：
    - 6/9 开头 → .SH（上交所）
    - 0/3 开头 → .SZ（深交所）
    - 已有后缀 → 保持不变
    """
    ticker = ticker.strip().upper()
    if "." in ticker:
        return ticker
    if len(ticker) != 6 or not ticker.isdigit():
        raise typer.BadParameter(
            f"invalid ticker: {ticker!r}, expected 6-digit code (e.g., 600519)"
        )
    if ticker[0] in ("6", "9"):
        return f"{ticker}.SH"
    if ticker[0] in ("0", "3"):
        return f"{ticker}.SZ"
    raise typer.BadParameter(
        f"unknown exchange for ticker: {ticker!r}, expected 6/9 → SH or 0/3 → SZ"
    )


@app.command()
def council(
    ticker: str = typer.Option(None, "--ticker", help="股票代码（6 位数字，自动补 .SH/.SZ）"),
    calibrate: bool = typer.Option(False, "--calibrate", help="跑校准测试"),
    force: bool = typer.Option(False, "--force", help="跳过缓存，强制重跑 LLM"),
):
    """L3 天团深研：巴菲特单 agent 对单股做深度研判.

    环境变量（必填）：
    - LLM_API_KEY: LLM API 密钥
    - LLM_API_BASE: LLM API base URL
    - LLM_MODEL_HEAVY: 重度推理模型（R1-3）
    - LLM_MODEL_MODERATE: 中度推理模型（R4）

    成本估算：单股单 agent ~¥0.675/只（仅 R1 调用）。
    """
    import asyncio

    if calibrate:
        from council.calibrate import run_calibration
        passed = asyncio.run(run_calibration())
        raise typer.Exit(code=0 if passed else 1)

    if not ticker:
        raise typer.BadParameter("must provide --ticker or --calibrate")

    normalized = _normalize_ticker(ticker)
    typer.echo(f"L3 Council: {normalized}")

    from council.debate import run_debate
    from datetime import date
    result = asyncio.run(run_debate(normalized, force=force))

    typer.echo(result.to_json())
    typer.echo(f"\n辩论记录已写入 debate/{normalized.split('.')[0]}/{date.today().isoformat()}.md")


if __name__ == "__main__":
    app()
