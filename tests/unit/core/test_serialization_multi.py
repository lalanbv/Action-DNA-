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


# ── Condition 多模板序列化 ──────────────────────────────────

def test_condition_to_dict_includes_multi_fields():
    from src.core.condition import Condition, ConditionType
    from src.core.serialization import condition_to_dict
    cond = Condition(
        condition_type=ConditionType.IMAGE_FOUND, image_path="a.png", threshold=0.8,
        alt_image_paths=["b.png", "c.png"], alt_thresholds=[0.7, None],
        match_strategy=MatchStrategy.BEST_CONFIDENCE, threshold_mode=ThresholdMode.PER_TEMPLATE,
    )
    d = condition_to_dict(cond)
    assert d["alt_image_paths"] == ["b.png", "c.png"]
    assert d["alt_thresholds"] == [0.7, None]
    # 枚举转为 name 字符串(JSON 可序列化,与 ClickImageStep 一致)
    assert d["match_strategy"] == "BEST_CONFIDENCE"
    assert d["threshold_mode"] == "PER_TEMPLATE"


def test_condition_from_dict_loads_multi_fields():
    from src.core.serialization import dict_to_condition
    data = {
        "condition_type": "IMAGE_FOUND", "image_path": "a.png", "threshold": 0.8,
        "alt_image_paths": ["b.png"], "alt_thresholds": [0.7],
        "match_strategy": "ADAPTIVE", "threshold_mode": "GLOBAL",
    }
    cond = dict_to_condition(data)
    assert cond.alt_image_paths == ["b.png"]
    assert cond.alt_thresholds == [0.7]
    assert cond.match_strategy == MatchStrategy.ADAPTIVE


def test_condition_from_dict_backward_compat():
    """旧 profile 无新字段 → 默认值。"""
    from src.core.serialization import dict_to_condition
    cond = dict_to_condition({"condition_type": "IMAGE_FOUND", "image_path": "a.png", "threshold": 0.8})
    assert cond.alt_image_paths == []
    assert cond.alt_thresholds == []
    assert cond.threshold_mode == ThresholdMode.GLOBAL


def test_flow_node_load_converts_condition_alt_rel_to_abs(tmp_path):
    """加载节点时 Condition alt 相对→绝对。"""
    from src.core.serialization import dict_to_flow_node
    profile_dir = str(tmp_path)
    (tmp_path / "b.png").write_bytes(b"x")
    data = {
        "node_id": "n1", "node_type": "ACTION", "action": None,
        "condition": {
            "condition_type": "IMAGE_FOUND", "image_path": "a.png", "threshold": 0.8,
            "alt_image_paths": ["b.png"], "alt_thresholds": [None],
            "match_strategy": "ADAPTIVE", "threshold_mode": "GLOBAL",
        },
    }
    node = dict_to_flow_node(data, profile_dir)
    assert node.condition is not None
    assert os.path.isabs(node.condition.alt_image_paths[0])
    assert node.condition.alt_image_paths[0].endswith("b.png")


# ── Monitor 多模板序列化 ────────────────────────────────────

def test_monitor_to_dict_includes_multi_fields():
    from src.core.monitor import MonitorConfig
    from src.core.serialization import monitor_to_dict
    mon = MonitorConfig(
        name="m", image_path="t.png", handler_image_path="h.png",
        alt_image_paths=["t2.png"], alt_thresholds=[0.7],
        alt_handler_image_paths=["h2.png"], alt_handler_thresholds=[None],
        match_strategy=MatchStrategy.BEST_CONFIDENCE, threshold_mode=ThresholdMode.PER_TEMPLATE,
    )
    d = monitor_to_dict(mon)
    assert d["alt_image_paths"] == ["t2.png"]
    assert d["alt_thresholds"] == [0.7]
    assert d["alt_handler_image_paths"] == ["h2.png"]
    assert d["match_strategy"] == "BEST_CONFIDENCE"
    assert d["threshold_mode"] == "PER_TEMPLATE"


def test_dict_to_monitor_loads_multi_and_converts_rel_to_abs(tmp_path):
    from src.core.serialization import dict_to_monitor
    (tmp_path / "t2.png").write_bytes(b"x")
    (tmp_path / "h2.png").write_bytes(b"x")
    data = {
        "name": "m", "enabled": True, "image_path": "t.png", "threshold": 0.8,
        "check_interval": 1.0, "handler_action": "LEFT_CLICK", "handler_image_path": "h.png",
        "priority": 0, "max_consecutive": 3, "cooldown": 2.0,
        "alt_image_paths": ["t2.png"], "alt_thresholds": [0.7],
        "alt_handler_image_paths": ["h2.png"], "alt_handler_thresholds": [None],
        "match_strategy": "ADAPTIVE", "threshold_mode": "GLOBAL",
    }
    mon = dict_to_monitor(data, profile_dir=str(tmp_path))
    assert os.path.isabs(mon.alt_image_paths[0]) and mon.alt_image_paths[0].endswith("t2.png")
    assert os.path.isabs(mon.alt_handler_image_paths[0]) and mon.alt_handler_image_paths[0].endswith("h2.png")
    assert mon.alt_thresholds == [0.7]
    assert mon.match_strategy == MatchStrategy.ADAPTIVE


def test_dict_to_monitor_backward_compat():
    from src.core.serialization import dict_to_monitor
    mon = dict_to_monitor({"name": "m", "image_path": "t.png", "threshold": 0.8}, profile_dir="/tmp")
    assert mon.alt_image_paths == []
    assert mon.alt_handler_image_paths == []
    assert mon.threshold_mode == ThresholdMode.GLOBAL
