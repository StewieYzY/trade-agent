"""g1-canonical-run-identity: CLI screen 命令输出 run identity 测试.

对应 scout-agent MODIFIED CLI Integration + run-identity / L1 生成。
验证 screen 命令输出结构顶层含 run_id/run_date/profile_version/input_ticker_set_hash。
"""
import sys
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from typer.testing import CliRunner
from cli import app

runner = CliRunner()


def _make_ticker_data():
    """构造能过 hard gates 的最小 ticker_data."""
    return {
        "basic": {
            "code": "600519", "name": "贵州茅台", "industry": "白酒",
            "pe": 25.0, "pb": 2.0, "price": 10.0, "market_cap": 100e8,
        },
        "financials": {
            "years": ["2020", "2021", "2022"],
            "income": {"net_profit": [100, 120, 150]},
            "balance_sheet": {
                "TOTAL_ASSETS": [1000, 1100, 1200],
                "TOTAL_CURRENT_LIAB": [300, 330, 360],
                "TOTAL_NONCURRENT_LIAB": [200, 220, 240],
            },
            "cash_flow": {"NETCASH_OPERATE": [80, 90, 100]},
        },
        "valuation": {"pe_percentile_5y": 40, "pb": 2.0, "pe_ttm": 25.0, "graham_number": 100},
        "risk": {"pledge_ratio": 30, "audit_opinion": "标准无保留意见"},
        "kline": {"turnover_rate": [0.3] * 60, "close": [10.0] * 60},
    }


def test_cli_screen_payload_carries_run_identity():
    """screen 命令输出结构顶层含 run identity 四字段（从 screen_a_shares 返回继承）.

    对应 run-identity spec: L1 生成 run_id 并写入输出；CLI screen 输出该结构。
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        # 用临时 tickers 文件（screen 命令 --tickers 读文件）
        tickers_path = Path(tmpdir) / "tickers.txt"
        tickers_path.write_text("600519\n", encoding="utf-8")
        output_path = Path(tmpdir) / "l1_output.json"

        fake_all_data = {"600519": _make_ticker_data()}
        # mock BatchFetcher（避免真实采集）+ date.today 固定 run_date
        from unittest.mock import MagicMock
        with patch("screener.main.BatchFetcher") as MockBF, \
             patch("screener.main.date") as mock_d:
            MockBF.return_value.fetch_all.return_value = fake_all_data
            mock_d.today.return_value.isoformat.return_value = "2026-07-21"
            result = runner.invoke(app, [
                "screen", "--tickers", str(tickers_path), "--output", str(output_path),
            ])

        assert result.exit_code == 0, result.stdout
        assert output_path.exists()
        l1_data = json.loads(output_path.read_text(encoding="utf-8"))
        # run identity 四字段（g1-canonical-run-identity L1 生成）
        assert l1_data.get("run_id"), "screen 输出 SHALL 含 run_id（非空）"
        assert l1_data.get("run_date") == "2026-07-21"
        assert l1_data.get("profile_version"), "SHALL 含 profile_version"
        assert l1_data.get("input_ticker_set_hash"), "SHALL 含 input_ticker_set_hash"


def test_cli_screen_output_run_scoped_same_day_not_overwrite():
    """g1-canonical-run-identity: 同日多次 screen 运行 SHALL 不互相覆盖（run-scoped 命名）.

    对应 scout-agent MODIFIED CLI Integration / run-identity 运行隔离:
    #### Scenario: Same-day multiple runs do not overwrite.
    同一 --output 路径，两次运行 run_id 不同（uuid4），第二次 SHALL 改写 run-scoped 文件名
    （{stem}.{run_id[:8]}.json），旧 run 的输出文件 SHALL 仍可读，MUST NOT 被覆盖。
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tickers_path = Path(tmpdir) / "tickers.txt"
        tickers_path.write_text("600519\n", encoding="utf-8")
        output_path = Path(tmpdir) / "l1_output.json"

        fake_all_data = {"600519": _make_ticker_data()}
        from unittest.mock import MagicMock
        with patch("screener.main.BatchFetcher") as MockBF, \
             patch("screener.main.date") as mock_d:
            MockBF.return_value.fetch_all.return_value = fake_all_data
            mock_d.today.return_value.isoformat.return_value = "2026-07-21"
            # 第一次运行
            r1 = runner.invoke(app, [
                "screen", "--tickers", str(tickers_path), "--output", str(output_path),
            ])
            assert r1.exit_code == 0, r1.stdout
            first_run_id = json.loads(output_path.read_text(encoding="utf-8"))["run_id"]

            # 第二次运行（同日同输入，run_id 不同——uuid4 每次唯一）
            r2 = runner.invoke(app, [
                "screen", "--tickers", str(tickers_path), "--output", str(output_path),
            ])
            assert r2.exit_code == 0, r2.stdout

        # 旧 run 文件 SHALL 仍存在（run-scoped 文件名分流，未被覆盖）
        first_data = json.loads(output_path.read_text(encoding="utf-8"))
        assert first_data["run_id"] == first_run_id, "旧 run 输出 SHALL 不被第二次运行覆盖"

        # 第二次 run SHALL 写到 run-scoped 文件名（{stem}.{run_id[:8]}.json）
        run_scoped = output_path.with_name(f"l1_output.{first_run_id[:8]}.json")
        # 第二次 run 的 run_id 与第一次不同；分流文件应存在且含第二次 run_id
        scoped_candidates = list(output_path.parent.glob("l1_output.*.json"))
        assert len(scoped_candidates) >= 1, "第二次运行 SHALL 产生 run-scoped 分流文件"
        second_data = json.loads(scoped_candidates[0].read_text(encoding="utf-8"))
        assert second_data["run_id"] != first_run_id, "两次运行 run_id SHALL 不同（uuid4）"


def test_cli_screen_output_preserves_legacy_no_run_id_file():
    """g1-canonical-run-identity-repair: --output 目标已有无 run_id 的旧文件（G1-3 前遗留）SHALL 不覆盖.

    对应 run-identity MODIFIED 运行隔离: #### Scenario: legacy CLI output 无 run_id 不覆盖。
    旧文件无 run_id（existing_rid=None）SHALL 同样分流，旧无 identity 文件保留可读。
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tickers_path = Path(tmpdir) / "tickers.txt"
        tickers_path.write_text("600519\n", encoding="utf-8")
        output_path = Path(tmpdir) / "l1_output.json"
        # 预放一个 G1-3 前的旧文件（无 run_id 字段）
        legacy_content = json.dumps({"candidates": [], "stats": {"total": 0}}, ensure_ascii=False)
        output_path.write_text(legacy_content, encoding="utf-8")

        fake_all_data = {"600519": _make_ticker_data()}
        from unittest.mock import MagicMock
        with patch("screener.main.BatchFetcher") as MockBF, \
             patch("screener.main.date") as mock_d:
            MockBF.return_value.fetch_all.return_value = fake_all_data
            mock_d.today.return_value.isoformat.return_value = "2026-07-21"
            result = runner.invoke(app, [
                "screen", "--tickers", str(tickers_path), "--output", str(output_path),
            ])
            assert result.exit_code == 0, result.stdout

        # 旧文件 SHALL 不被覆盖（内容不变）
        legacy_after = output_path.read_text(encoding="utf-8")
        assert legacy_after == legacy_content, "旧无 run_id 文件 SHALL 不被覆盖"

        # 新结果 SHALL 写入 run-scoped 分流文件
        scoped = list(output_path.parent.glob("l1_output.*.json"))
        assert len(scoped) >= 1, "SHALL 产生 run-scoped 分流文件"
        new_data = json.loads(scoped[0].read_text(encoding="utf-8"))
        assert new_data.get("run_id"), "分流文件 SHALL 含 run_id"


def test_run_scoped_output_path_legacy_corrupted():
    """目标路径是损坏的非 JSON 文件，SHALL 分流（不静默覆盖，保留排查证据）.

    对应 run-identity MODIFIED: legacy CLI output 无 run_id 不覆盖（损坏文件同分流）。
    """
    from cli import _run_scoped_output_path
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "l1.json"
        output_path.write_text("not json {{{", encoding="utf-8")  # 损坏文件
        result = _run_scoped_output_path(output_path, "rid12345678")
        assert result != output_path, "损坏文件 SHALL 分流（不静默覆盖）"
        assert "rid12345" in result.name, "分流文件名含 run_id 前 8 字符"
        # 损坏文件保留
        assert output_path.read_text(encoding="utf-8") == "not json {{{"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
