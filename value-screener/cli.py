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

import typer

app = typer.Typer(help="value-screener 数据采集 CLI")


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
    """采集单只股票指定维度数据，输出 JSON."""
    fetcher = _get_fetcher(dim)
    data = fetcher.fetch_with_fallback(ticker)
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


if __name__ == "__main__":
    app()
