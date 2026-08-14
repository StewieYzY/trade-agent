"""scripts/run_full_market_evidence.py 参数透传测试.

G1 6.1/6.2 的受控全市场 run 必须 force L2（绕过 L2 cache 复用，真实 LLM 调用），
与 8-12 run 的实际口径一致；脚本必须显式暴露 --force-l2 而不是硬编码 False。
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "_rfme_script_under_test", ROOT / "scripts" / "run_full_market_evidence.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_universe(tmp_path) -> Path:
    path = tmp_path / "universe.json"
    path.write_text(json.dumps({
        "source": "test-frozen-universe",
        "generated_at": "2026-08-13T00:00:00",
        "tickers": ["600001.SH", "600002.SH"],
    }, ensure_ascii=False), encoding="utf-8")
    return path


def _run_script(monkeypatch, tmp_path, extra_args: list[str]) -> dict:
    module = _load_script()
    captured: dict = {}

    async def fake_run(tickers, **kwargs):
        captured["tickers"] = tickers
        captured.update(kwargs)
        # run_failed=True 让 main() 走最短输出路径（不构造完整 bundle 字段）
        return {"run_failed": True, "failure": {"error": "test-stub"}, "gate_passed": False}

    saved: dict = {}

    def fake_save(bundle, output_dir=None):
        saved["bundle"] = bundle
        return tmp_path / "bundle.json"

    monkeypatch.setattr(sys, "argv", [
        "run_full_market_evidence.py",
        "--tickers-file", str(_write_universe(tmp_path)),
        "--coverage", "full_market",
        *extra_args,
    ])
    with patch("performance.run_evidence.run_full_market_evidence", new=fake_run), \
         patch("performance.run_evidence.save_evidence_bundle", new=fake_save):
        asyncio.run(module.main())
    assert saved, "evidence bundle 未落盘（save_evidence_bundle 未被调用）"
    return captured


def test_force_l2_flag_passes_through(monkeypatch, tmp_path):
    captured = _run_script(monkeypatch, tmp_path, ["--force-l2"])
    assert captured["force_l2"] is True
    assert captured["tickers"] == ["600001.SH", "600002.SH"]
    assert captured["coverage"] == "full_market"


def test_force_l2_defaults_false(monkeypatch, tmp_path):
    captured = _run_script(monkeypatch, tmp_path, [])
    assert captured["force_l2"] is False
