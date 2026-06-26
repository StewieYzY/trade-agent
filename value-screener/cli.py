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


if __name__ == "__main__":
    app()
