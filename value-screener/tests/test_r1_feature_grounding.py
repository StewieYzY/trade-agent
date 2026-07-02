"""Tests for R1 feature grounding 校验（f1-deviation-fix §6, G4）.

spec debate-quality-gate: R1 输出引用真实特征校验（反向校验）。
- 反向校验：提取 key_metrics 里的数字，检查是否在 features 任一字段值中出现；
  含凭空数字（features 对应字段为 None 或值不匹配）则标记幻觉。
- 环形引用检测：R1（other_opinions=None）的 core_thesis 出现其他 agent_id 名字
  （munger/duan/feng_liu/buffett 互引）时标记幻觉引用。
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from council.schema import AgentOutput
from council.verify_quality_gate import (
    verify_r1_feature_grounding,
    detect_circular_reference,
)


def _make_agent(name="buffett", key_metrics=None, core_thesis="基本面良好"):
    return AgentOutput.from_dict(name, {
        "signal": "bullish",
        "conviction": 75,
        "core_thesis": core_thesis,
        "key_metrics": key_metrics or [],
        "risks": [],
        "what_would_change_my_mind": "业绩下滑",
        "out_of_circle": False,
        "historical_parallel": None,
    })


# ── 反向特征校验 ──────────────────────────────────────────────


def test_key_metrics_number_found_in_features_passes():
    """key_metrics 含 "PE_TTM 26.42"，features.pe_ttm == 26.42 → 通过."""
    agent = _make_agent(key_metrics=["PE_TTM 26.42", "ROE 趋势上升"])
    features = {"pe_ttm": 26.42, "roe_3y": [25.0, 26.0, 27.0], "net_margin": 30.0}
    ok, issues = verify_r1_feature_grounding(agent, features)
    assert ok is True
    assert issues == []


def test_key_metrics_fabricated_number_detected():
    """key_metrics 含 "ROE 32%"，features 无 32 → 标记幻觉（核心场景：600900 水电股输出茅台特征）."""
    agent = _make_agent(key_metrics=["ROE 32%", "毛利率 90%+"])
    # features roe_3y 各值都不是 32，net_margin 也不是 90
    features = {"pe_ttm": 18.2, "roe_3y": [15.0, 16.0, 17.0], "net_margin": 40.0}
    ok, issues = verify_r1_feature_grounding(agent, features)
    assert ok is False
    # 至少识别出凭空数字
    assert any("32" in i or "90" in i for i in issues)


def test_key_metrics_number_not_in_features_when_field_none():
    """features 对应字段为 None + key_metrics 含数字 → 幻觉."""
    agent = _make_agent(key_metrics=["PE 100"])
    features = {"pe_ttm": None, "roe_3y": None, "net_margin": None}
    ok, issues = verify_r1_feature_grounding(agent, features)
    assert ok is False
    assert any("100" in i for i in issues)


def test_key_metrics_no_numbers_passes():
    """key_metrics 不含数字（纯文字）→ 不触发反向校验，通过（避免误伤）."""
    agent = _make_agent(key_metrics=["ROE 趋势上升", "毛利率稳定"])
    features = {"pe_ttm": 26.42, "roe_3y": [25.0, 26.0, 27.0], "net_margin": 30.0}
    ok, issues = verify_r1_feature_grounding(agent, features)
    assert ok is True


def test_key_metrics_number_matches_different_field():
    """key_metrics 数字在 features 任一字段值中出现即算有来源（spec Scenario 1）."""
    # "ROE 27" → features.roe_3y 含 27.0（最后一年）
    agent = _make_agent(key_metrics=["ROE 27"])
    features = {"pe_ttm": 26.42, "roe_3y": [25.0, 26.0, 27.0], "net_margin": 30.0}
    ok, issues = verify_r1_feature_grounding(agent, features)
    assert ok is True


# ── 环形引用检测 ──────────────────────────────────────────────


def test_circular_reference_buffett_cites_munger_detected():
    """R1（buffett）core_thesis 含 "munger 看好" → 环形引用（spec 600519 铁证）."""
    agent = _make_agent(name="buffett", core_thesis="munger 看好长期价值")
    ok, issues = detect_circular_reference(agent)
    assert ok is False
    assert any("munger" in i.lower() for i in issues)


def test_circular_reference_no_other_agent_passes():
    """R1 core_thesis 不引其他 agent → 通过."""
    agent = _make_agent(name="buffett", core_thesis="贵州茅台拥有强大的品牌护城河")
    ok, issues = detect_circular_reference(agent)
    assert ok is True
    assert issues == []


def test_circular_reference_all_agent_pairs():
    """四 agent 互引都识别（buffett/munger/duan/feng_liu）."""
    pairs = [
        ("buffett", "munger 看好"),
        ("munger", "duan 提到"),
        ("duan", "feng_liu 认为"),
        ("feng_liu", "buffett 同意"),
    ]
    for agent_id, thesis in pairs:
        agent = _make_agent(name=agent_id, core_thesis=thesis)
        ok, issues = detect_circular_reference(agent)
        assert ok is False, f"{agent_id} 引用应被识别：{thesis}"


def test_circular_reference_self_name_not_flagged():
    """agent 引用自己的名字不算环形引用（如 buffett 说"我巴菲特认为"）.

    注：buffett 的 display name 含"巴菲特"，但 agent_id 是 buffett。
    自引不构成 R1 信息隔离破坏。
    """
    agent = _make_agent(name="buffett", core_thesis="作为 buffett 我坚持判断")
    ok, issues = detect_circular_reference(agent)
    # 引用自己（agent_id 相同）不应标记
    assert ok is True


def test_circular_reference_dynamic_agent_ids_supports_zhangkun():
    """P3 修复：agent_ids 动态注入，张坤（未注册）加入后能被检测.

    模拟张坤注册后，buffett 引用 zhangkun 应被识别（原硬编码会漏检）。
    """
    agent = _make_agent(name="buffett", core_thesis="zhangkun 看好消费板块")
    # 注入含张坤的 agent_ids（模拟张坤注册）
    ok, issues = detect_circular_reference(agent, agent_ids=("buffett", "munger", "duan", "feng_liu", "zhangkun"))
    assert ok is False
    assert any("zhangkun" in i.lower() for i in issues)


def test_circular_reference_default_reads_agent_registry():
    """P3 修复：agent_ids=None 时动态从 AGENT_REGISTRY 读取（当前 4 agent）."""
    from council.agents import AGENT_REGISTRY
    # buffett 引用 feng_liu（在 AGENT_REGISTRY 中）→ 应被检测
    agent = _make_agent(name="buffett", core_thesis="feng_liu 的逆向思路有启发")
    ok, issues = detect_circular_reference(agent)  # 不传 agent_ids，走动态读取
    assert ok is False
    assert any("feng_liu" in i.lower() for i in issues)
    # 验证动态读取的是 AGENT_REGISTRY 的 keys
    assert "buffett" in AGENT_REGISTRY
