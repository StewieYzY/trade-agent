"""top20 CLI 离线预检测试.

derive 声明「离线、无 provider/LLM 调用」；allow_stale 只复用结构有效的本地缓存，
缓存缺失时 screen_a_shares 会退回 provider 抓取。因此 derive 必须先做缓存温暖度
预检：不完整即拒绝（exit 2），绝不静默发起抓取。
"""
from __future__ import annotations

import json

from typer.testing import CliRunner

from cli import app
from data.lib.identity import compute_input_ticker_set_hash
from screener.main import G1_QUANT_DIMENSIONS

runner = CliRunner()

PAYLOADS = {
    "basic": {"code": "x", "name": "n", "price": 1, "pe": 1, "pb": 1, "market_cap": 1},
    "financials": {"years": ["2025"], "income": {}, "balance_sheet": {}, "cash_flow": {}},
    "kline": {"dates": ["2026-08-11"], "close": [1], "volume": [1], "turnover_rate": [1]},
    "valuation": {"pe_ttm": 1, "pb": 1, "pe_percentile_5y": 1, "pb_percentile_5y": 1},
    "risk": {"pledge_ratio": None, "pledge_status": "record_not_found"},
}


def _write_warm_cache(base, code: str) -> None:
    for dim in G1_QUANT_DIMENSIONS:
        d = base / code
        d.mkdir(parents=True, exist_ok=True)
        payload = dict(PAYLOADS[dim])
        if dim == "basic":
            payload["code"] = code
        (d / f"{dim}.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_pinned_bundle(path, tickers: list[str]) -> None:
    n = len(tickers)
    bundle = {
        "schema_version": "g1-full-market-performance-cost.v2",
        "run_id": "7887d515-157d-4d17-bcb5-fab54c7fbee3",
        "profile_version": "g1-2026-07-21",
        "input_ticker_set_hash": compute_input_ticker_set_hash(tickers),
        "input_tickers": list(tickers),
        "run_date": "2026-08-12",
        "coverage": "full_market",
        "funnel": {
            "total": n,
            "after_hard_gates": n,
            "after_factors": n,
            "after_heat_filter": n,
            "l2_input": n,
        },
        "hard_gate_passed": True,
        "gate_passed": True,
    }
    path.write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")


def test_derive_refuses_cold_cache_without_touching_provider(monkeypatch, tmp_path):
    """缓存不完整 → exit 2 拒绝，且 MUST NOT 进入 screen_a_shares（provider 路径）."""
    monkeypatch.chdir(tmp_path)
    tickers = ["600001.SH", "600002.SH"]
    bundle_path = tmp_path / "pinned.json"
    _write_pinned_bundle(bundle_path, tickers)

    reached = []

    def _screen_a_shares_boom(*args, **kwargs):
        reached.append(True)
        raise AssertionError("cold cache 下不得进入 screen_a_shares（会触发 provider 抓取）")

    monkeypatch.setattr("screener.main.screen_a_shares", _screen_a_shares_boom)

    result = runner.invoke(app, ["top20", "derive", "--pinned", str(bundle_path)])
    assert result.exit_code == 2
    assert reached == []
    assert "离线预检失败" in result.output
    assert not (tmp_path / "data/evidence/g1-top20-style-review/top20_derivation.json").exists()


def test_derive_proceeds_when_cache_warm(monkeypatch, tmp_path):
    """缓存全暖 → 预检放行，进入（stub 的）L1 再派生并产出 derivation 与复核模板."""
    monkeypatch.chdir(tmp_path)
    tickers = ["600001.SH"]
    _write_warm_cache(tmp_path / "data" / "cache", "600001")
    bundle_path = tmp_path / "pinned.json"
    _write_pinned_bundle(bundle_path, tickers)

    fake_l1 = {
        "run_id": "derivation-run-warm",
        "run_date": "2026-08-13",
        "profile_version": "g1-2026-07-21",
        "input_ticker_set_hash": compute_input_ticker_set_hash(tickers),
        "candidates": [{
            "ticker": "600001.SH",
            "factor_scores": {"composite": 88.0},
            "anti_trap": {"score": 95.0, "flags": []},
            "adjusted_composite": 83.6,
        }],
        "stats": {
            "total": 1,
            "after_hard_gates": 1,
            "after_factors": 1,
            "after_heat_filter": 1,
            "excluded_by_gates": {},
        },
    }
    monkeypatch.setattr("screener.main.screen_a_shares", lambda *a, **k: fake_l1)

    result = runner.invoke(app, ["top20", "derive", "--pinned", str(bundle_path)])
    assert result.exit_code == 0, result.output
    out_dir = tmp_path / "data/evidence/g1-top20-style-review"
    derivation = json.loads((out_dir / "top20_derivation.json").read_text(encoding="utf-8"))
    assert derivation["status"] == "derived"
    assert len(derivation["top20"]) == 1
    template = json.loads((out_dir / "user_review_template.json").read_text(encoding="utf-8"))
    assert len(template["reviews"]) == 1
    assert template["reviews"][0]["label"] is None
