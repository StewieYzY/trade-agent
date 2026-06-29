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

    # 2. 调用 scout_batch（异步）
    from scout.batch import scout_batch
    shortlist = asyncio.run(scout_batch(candidates, force=force))

    # 3. 输出结果
    output_json = json.dumps(shortlist, ensure_ascii=False, indent=2)

    if output:
        Path(output).write_text(output_json, encoding="utf-8")
        typer.echo(f"结果已写入到 {output}")
    else:
        typer.echo(output_json)

    typer.echo(f"L2 筛选完成：{len(shortlist)}/{len(candidates)} 只 deep_dive（top-20 cap）")


if __name__ == "__main__":
    app()
