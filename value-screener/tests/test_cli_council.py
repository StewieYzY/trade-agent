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

    def test_bj_not_misjudged_as_sh(self):
        """g1-canonical-run-identity: 920xxx BJ 不误判为 SH（修 cli 旧 9→SH bug）.

        _normalize_ticker 改调 canonical_ticker（复用 market_router._a_share_suffix，
        BJ 前缀 43/83/87/88/92 优先判定）。
        """
        from cli import _normalize_ticker
        assert _normalize_ticker("920060") == "920060.BJ", \
            "920xxx BJ MUST NOT 误判为 SH（修 cli 旧逻辑首字符 9 → SH 的 bug）"

    def test_lowercase_suffix_uppercased(self):
        """g1-canonical-run-identity: 小写后缀统一大写."""
        from cli import _normalize_ticker
        assert _normalize_ticker("600519.sh") == "600519.SH"
        assert _normalize_ticker("920060.bj") == "920060.BJ"

    def test_invalid_length(self):
        """非法 ticker 报错（g1-canonical-run-identity: canonical SoT 语义）.

        旧 _normalize_ticker 对 5 位 60051 报错（非 6 位 A 股）；
        新 canonical_ticker 复用 market_router，5 位数字被识别为 HK（00700.HK 形式）。
        故改用真正非法的 case：7 位数字（非 6 位 A 股、非 3-5 位 HK）。
        """
        from cli import _normalize_ticker
        import typer
        with pytest.raises(typer.BadParameter):
            _normalize_ticker("1234567")  # 7 位，非 6 位 A 股也非 3-5 位 HK

    def test_invalid_chars(self):
        """非法 ticker 报错（g1-canonical-run-identity: 纯字母被识别为 US，中文才是真非法）.

        旧 _normalize_ticker 对 ABCDEF 报错（非数字）；
        新 canonical_ticker 复用 market_router，纯字母 1-6 位被识别为 US ticker（AAPL 形式）。
        故改用真正非法的 case：中文名（本层不解析名称→代码，需调用方先 resolve）。
        """
        from cli import _normalize_ticker
        import typer
        with pytest.raises(typer.BadParameter):
            _normalize_ticker("水晶光电")  # 中文名，canonical SoT 不解析

    def test_unknown_suffix(self):
        """未知后缀报错（g1-canonical-run-identity: canonical SoT 校验后缀合法性）.

        旧 test_unknown_prefix 测 123456 报错（非 0/3/6/9 开头）；
        新 canonical_ticker 把 123456 识别为 SZ（6 位数字默认深交所），不再报错。
        该测试的语义前提（严格前缀校验）被 canonical SoT 复用 market_router 决策推翻。
        改测真正非法的未知后缀 case。
        """
        from cli import _normalize_ticker
        import typer
        with pytest.raises(typer.BadParameter):
            _normalize_ticker("600519.XX")  # 未知后缀（.XX 非 .SH/.SZ/.BJ）


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
            round1=[AgentOutput(name="buffett", signal="bullish", conviction=80, core_thesis="好公司", what_would_change_my_mind="业绩下滑", out_of_circle=False)],
            final_verdict="bullish",
            key_variables=[]
        )

        result = runner.invoke(app, ["council", "--ticker", "600519"])
        assert result.exit_code == 0
        # g1-canonical-run-identity-repair D4: 路径提示用 canonical（带 .SH 后缀），
        # 与 _debate_path 实际写入路径一致，MUST NOT 显示纯数字旧路径。
        assert "debate/600519.SH/" in result.stdout, \
            "路径提示 SHALL 显示 canonical debate/600519.SH/，MUST NOT 显示纯数字 debate/600519/"
        assert "debate/600519/" not in result.stdout.replace("debate/600519.SH/", ""), \
            "MUST NOT 出现纯数字 debate/600519/ 路径提示"

    @patch("council.debate.run_debate", new_callable=AsyncMock)
    def test_council_force_flag(self, mock_run_debate, tmp_path, monkeypatch):
        """council --force 传递 force=True."""
        monkeypatch.chdir(tmp_path)
        from council.schema import CouncilResult
        mock_run_debate.return_value = CouncilResult(
            ticker="600519.SH",
            round1=[],
            final_verdict="bullish",
            key_variables=[]
        )

        result = runner.invoke(app, ["council", "--ticker", "600519", "--force"])
        assert result.exit_code == 0
        call_kwargs = mock_run_debate.call_args[1]
        assert call_kwargs["force"] is True
