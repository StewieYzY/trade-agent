"""Tests for scout/parse.py (tasks 6.5, 6.6)."""
import sys
from pathlib import Path
import json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scout.parse import parse_scout_output, apply_buffer_zone


def test_parse_scout_output_valid():
    """验证 parse_scout_output 解析合法 JSON."""
    raw = json.dumps({
        "verdict": "deep_dive",
        "confidence": 85,
        "one_liner": "优质白酒企业，估值合理",
        "red_flags": [],
        "green_flags": ["ROE 连续 3 年 > 25%"],
        "anti_trap_flags": [],
    })

    result = parse_scout_output(raw)

    assert result["verdict"] == "deep_dive"
    assert result["confidence"] == 85
    assert result["one_liner"] == "优质白酒企业，估值合理"
    assert result["red_flags"] == []
    assert result["green_flags"] == ["ROE 连续 3 年 > 25%"]
    assert result["anti_trap_flags"] == []


def test_parse_scout_output_malformed_json():
    """验证 parse_scout_output 处理格式错误 JSON."""
    raw = '{"verdict": "deep_dive", "confidence": 85'  # 缺少闭合

    result = parse_scout_output(raw)

    assert result["verdict"] == "watch"
    assert result["confidence"] == 0
    assert result.get("parse_error") is True


def test_parse_scout_output_invalid_verdict():
    """验证 parse_scout_output 处理非法 verdict."""
    raw = json.dumps({
        "verdict": "invalid_verdict",
        "confidence": 85,
        "one_liner": "test",
    })

    result = parse_scout_output(raw)

    assert result["verdict"] == "watch"  # 非法 verdict 回退为 watch
    assert result["confidence"] == 85


def test_parse_scout_output_invalid_confidence():
    """验证 parse_scout_output 处理非法 confidence."""
    raw = json.dumps({
        "verdict": "deep_dive",
        "confidence": 150,  # 超出范围
        "one_liner": "test",
    })

    result = parse_scout_output(raw)

    assert result["confidence"] == 0  # 非法 confidence 回退为 0


def test_parse_scout_output_flags_not_list():
    """验证 parse_scout_output 处理非 list 类型的 flags."""
    raw = json.dumps({
        "verdict": "deep_dive",
        "confidence": 85,
        "one_liner": "test",
        "red_flags": "not a list",  # 应为 list
    })

    result = parse_scout_output(raw)

    assert result["red_flags"] == []  # 非 list 回退为空列表


def test_parse_scout_output_one_liner_truncate():
    """验证 parse_scout_output 截断超长 one_liner."""
    raw = json.dumps({
        "verdict": "deep_dive",
        "confidence": 85,
        "one_liner": "x" * 100,  # 超过 50 字
    })

    result = parse_scout_output(raw)

    assert len(result["one_liner"]) == 50


def test_apply_buffer_zone_high_confidence():
    """验证 apply_buffer_zone: confidence >= 60 信任 verdict."""
    verdict, is_anomaly = apply_buffer_zone("deep_dive", 75)
    assert verdict == "deep_dive"
    assert is_anomaly is False

    verdict, is_anomaly = apply_buffer_zone("skip", 60)
    assert verdict == "skip"
    assert is_anomaly is False


def test_apply_buffer_zone_buffer_zone():
    """验证 apply_buffer_zone: 40 <= confidence < 60 强制 watch."""
    verdict, is_anomaly = apply_buffer_zone("deep_dive", 55)
    assert verdict == "watch"
    assert is_anomaly is False

    verdict, is_anomaly = apply_buffer_zone("skip", 40)
    assert verdict == "watch"
    assert is_anomaly is False


def test_apply_buffer_zone_low_confidence():
    """验证 apply_buffer_zone: confidence < 40 强制 watch + 标记异常."""
    verdict, is_anomaly = apply_buffer_zone("deep_dive", 30)
    assert verdict == "watch"
    assert is_anomaly is True

    verdict, is_anomaly = apply_buffer_zone("skip", 0)
    assert verdict == "watch"
    assert is_anomaly is True


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
