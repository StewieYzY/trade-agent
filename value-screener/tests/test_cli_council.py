"""L3 council CLI 子命令测试.

覆盖 cli.py 的 council 子命令和 _normalize_ticker 逻辑。
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from cli import app

runner = CliRunner()


class TestNormalizeTicker:
    """_normalize_ticker 4 条分支."""

    def test_6_digit_sh(self):
        """6 开头 → .SH."""
        from cli import _normalize_ticker
        assert _normalize_ticker("600519") == "600519.SH"

    def test_9_digit_sh(self):
        """9 开头 → .SH."""
        from cli import _normalize_ticker
        assert _normalize_ticker("900519") == "900519.SH"

    def test_0_digit_sz(self):
        """0 开头 → .SZ."""
        from cli import _normalize_ticker
        assert _normalize_ticker("000519") == "000519.SZ"

    def test_3_digit_sz(self):
        """3 开头 → .SZ."""
        from cli import _normalize_ticker
        assert _normalize_ticker("300519") == "300519.SZ"

    def test_already_has_suffix(self):
        """已有后缀保持不变."""
        from cli import _normalize_ticker
        assert _normalize_ticker("600519.SH") == "600519.SH"
        assert _normalize_ticker("000519.SZ") == "000519.SZ"

    def test_invalid_length(self):
        """非 6 位数字报错."""
        from cli import _normalize_ticker
        import typer
        with pytest.raises(typer.BadParameter):
            _normalize_ticker("60051")

    def test_invalid_chars(self):
        """非数字报错."""
        from cli import _normalize_ticker
        import typer
        with pytest.raises(typer.BadParameter):
            _normalize_ticker("ABCDEF")

    def test_unknown_prefix(self):
        """非 0/3/6/9 开头报错."""
        from cli import _normalize_ticker
        import typer
        with pytest.raises(typer.BadParameter):
            _normalize_ticker("123456")


class TestCouncilCommand:
    """council 子命令."""

    def test_council_requires_ticker_or_calibrate(self):
        """无 --ticker 且无 --calibrate 报错."""
        result = runner.invoke(app, ["council"])
        # typer BadParameter → exit code 2
        assert result.exit_code != 0

    @patch("council.debate.run_debate", new_callable=AsyncMock)
    def test_council_with_ticker(self, mock_run_debate, tmp_path, monkeypatch):
        """council --ticker 正常调用."""
        monkeypatch.chdir(tmp_path)
        from council.schema import CouncilResult, AgentOutput
        mock_run_debate.return_value = CouncilResult(
            ticker="600519.SH",
            rounds=[[AgentOutput(name="buffett", signal="bullish", conviction=80, core_thesis="好公司", what_would_change_my_mind="业绩下滑", out_of_circle=False)]],
            final_verdict="bullish",
            key_variables=[]
        )

        result = runner.invoke(app, ["council", "--ticker", "600519"])
        assert result.exit_code == 0

    @patch("council.debate.run_debate", new_callable=AsyncMock)
    def test_council_force_flag(self, mock_run_debate, tmp_path, monkeypatch):
        """council --force 传递 force=True."""
        monkeypatch.chdir(tmp_path)
        from council.schema import CouncilResult
        mock_run_debate.return_value = CouncilResult(
            ticker="600519.SH",
            rounds=[],
            final_verdict="bullish",
            key_variables=[]
        )

        result = runner.invoke(app, ["council", "--ticker", "600519", "--force"])
        assert result.exit_code == 0
        call_kwargs = mock_run_debate.call_args[1]
        assert call_kwargs["force"] is True
