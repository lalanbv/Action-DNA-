"""多模板字段序列化往返 + 枚举转换 + rel/abs 路径转换测试。"""

import json
import os

from src.core.action import MatchStrategy, ThresholdMode
from src.core.serialization import dict_to_flow_node, dict_to_step, step_to_dict
from src.core.step_types import ClickImageStep


def test_step_to_dict_includes_multi_fields():
    """step_to_dict 含多模板字段,且枚举转为 name 字符串。"""
    step = ClickImageStep(
        image_path="a.png",
        alt_image_paths=["b.png", "c.png"],
        alt_thresholds=[0.7, None],
        match_strategy=MatchStrategy.BEST_CONFIDENCE,
        threshold_mode=ThresholdMode.PER_TEMPLATE,
    )
    d = step_to_dict(step)
    assert d["alt_image_paths"] == ["b.png", "c.png"]
    assert d["alt_thresholds"] == [0.7, None]
    # 枚举必须转为字符串(JSON 可序列化)
    assert d["match_strategy"] == "BEST_CONFIDENCE"
    assert d["threshold_mode"] == "PER_TEMPLATE"


def test_step_to_dict_is_json_serializable():
    """关键:含枚举字段的 step 经 step_to_dict 后可 json.dumps。"""
    step = ClickImageStep(image_path="a.png", alt_image_paths=["b.png"])
    d = step_to_dict(step)
    s = json.dumps(d)  # 不抛 TypeError 即通过
    assert "match_strategy" in s


def test_dict_to_step_loads_multi_fields():
    """dict_to_step 从 name 字符串还原枚举。"""
    data = {
        "action_type": "CLICK_IMAGE",
        "image_path": "a.png",
        "threshold": 0.8,
        "alt_image_paths": ["b.png"],
        "alt_thresholds": [0.7],
        "match_strategy": "BEST_CONFIDENCE",
        "threshold_mode": "PER_TEMPLATE",
    }
    step = dict_to_step(data)
    assert isinstance(step, ClickImageStep)
    assert step.alt_image_paths == ["b.png"]
    assert step.alt_thresholds == [0.7]
    assert step.match_strategy == MatchStrategy.BEST_CONFIDENCE
    assert step.threshold_mode == ThresholdMode.PER_TEMPLATE


def test_dict_to_step_backward_compat_old_profile():
    """旧 profile 无新字段 → 默认值,行为等价单模板。"""
    data = {"action_type": "CLICK_IMAGE", "image_path": "a.png", "threshold": 0.8}
    step = dict_to_step(data)
    assert step.alt_image_paths == []
    assert step.alt_thresholds == []
    assert step.match_strategy == MatchStrategy.ADAPTIVE
    assert step.threshold_mode == ThresholdMode.GLOBAL


def test_roundtrip_step_to_dict_and_back():
    """step_to_dict → dict_to_step 往返一致。"""
    original = ClickImageStep(
        image_path="a.png",
        alt_image_paths=["b.png", "c.png"],
        alt_thresholds=[0.7, None],
        match_strategy=MatchStrategy.FIRST_MATCH,
        threshold_mode=ThresholdMode.AUTO,
    )
    restored = dict_to_step(step_to_dict(original))
    assert restored.alt_image_paths == ["b.png", "c.png"]
    assert restored.alt_thresholds == [0.7, None]
    assert restored.match_strategy == MatchStrategy.FIRST_MATCH
    assert restored.threshold_mode == ThresholdMode.AUTO


def test_dict_to_flow_node_converts_alt_rel_to_abs(tmp_path):
    """dict_to_flow_node 加载时 alt 相对路径 → 绝对(与主图一致)。"""
    profile_dir = str(tmp_path)
    (tmp_path / "b.png").write_bytes(b"x")
    node_data = {
        "node_type": "ACTION",
        "node_id": "n1",
        "action": {
            "action_type": "CLICK_IMAGE",
            "image_path": "a.png",
            "threshold": 0.8,
            "alt_image_paths": ["b.png"],
            "alt_thresholds": [None],
        },
    }
    node = dict_to_flow_node(node_data, profile_dir)
    assert isinstance(node.action, ClickImageStep)
    assert os.path.isabs(node.action.image_path)
    assert node.action.image_path.endswith("a.png")
    # alt 路径也应转为绝对
    assert len(node.action.alt_image_paths) == 1
    assert os.path.isabs(node.action.alt_image_paths[0])
    assert node.action.alt_image_paths[0].endswith("b.png")
