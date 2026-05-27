"""FlowGraph 序列化/反序列化 — 纯数据转换，无 UI 依赖。

供 importer.py 和 profile_manager.py 共用，避免 core → panel 的循环导入。
"""

import dataclasses
import os

from src.core.action import ActionType, DetectMode, FoundAction
from src.core.step_types import BaseStep, ClickImageStep, STEP_CLASSES
from src.utils.i18n import t
from src.core.condition import Condition, ConditionType
from src.core.engine.fsm_engine import GlobalTransition, Transition
from src.core.error.error_config import ErrorConfig
from src.core.flow import FlowEdge, FlowNode, NodeType
from src.core.monitor import MonitorConfig


# ── 旧 FoundAction 名称迁移 ──────────────────────────────────

_FOUND_ACTION_MIGRATION = {
    "CLICK": "LEFT_CLICK",
    "DOUBLE_CLICK": "LEFT_DOUBLE_CLICK",
    "MOVE_TO": "ONLY_MOVE",
    "CLICK_HOLD": "LONG_PRESS",
}


def resolve_found_action(value: str) -> FoundAction:
    """解析 FoundAction，兼容旧版枚举名"""
    try:
        return FoundAction[value]
    except KeyError:
        migrated = _FOUND_ACTION_MIGRATION.get(value)
        if migrated:
            return FoundAction[migrated]
        from src.core.logger import log
        log.warning(t("serialization.log.unknown_found_action", value=value))
        return FoundAction.LEFT_CLICK


# ── BaseStep ──────────────────────────────────────────────

def step_to_dict(step: BaseStep) -> dict:
    """BaseStep → JSON 可序列化字典（统一入口）。"""
    return typed_step_to_dict(step)


def dict_to_step(data: dict) -> BaseStep:
    """JSON 字典 → BaseStep 子类（统一入口）。"""
    return dict_to_typed_step(data)


# ── Typed Step (BaseStep) ───────────────────────────────────


def typed_step_to_dict(step: BaseStep) -> dict:
    """BaseStep 子类 → JSON 可序列化字典。

    自动处理 Enum 字段（DetectMode/FoundAction）→ name 字符串。
    ClassVar action_type 不在 dataclass.fields 中，手动写入。
    """
    d = dataclasses.asdict(step)
    d["action_type"] = step.action_type.name
    # 将 Enum 值转为 name 字符串
    for key, val in list(d.items()):
        if isinstance(val, (DetectMode, FoundAction)):
            d[key] = val.name
    return d


def dict_to_typed_step(data: dict) -> BaseStep:
    """JSON 字典 → BaseStep 子类，使用 STEP_CLASSES 注册表。

    自动忽略未知字段（向前/向后兼容）。
    """
    if "action_type" not in data:
        raise ValueError("缺少必需字段 'action_type'")
    atype = ActionType[data["action_type"]]
    cls = STEP_CLASSES.get(atype)
    if cls is None:
        raise ValueError(f"未注册的 ActionType: {atype.name}")
    d = dict(data)
    d.pop("action_type", None)
    # 枚举字段还原
    if "detect_mode" in d and isinstance(d["detect_mode"], str):
        d["detect_mode"] = DetectMode[d["detect_mode"]]
    if "found_action" in d:
        d["found_action"] = resolve_found_action(d["found_action"])
    # 旧版兼容：skip_if_not_found → detect_mode
    if "skip_if_not_found" in d and "detect_mode" not in d:
        d["detect_mode"] = (
            DetectMode.SKIP_IF_NOT_FOUND if d.pop("skip_if_not_found")
            else DetectMode.WAIT_UNTIL_FOUND
        )
    d.pop("skip_if_not_found", None)
    # 过滤掉不属于该类的字段
    valid_keys = {f.name for f in dataclasses.fields(cls)}
    d = {k: v for k, v in d.items() if k in valid_keys}
    return cls(**d)


# ── Condition ───────────────────────────────────────────────

def condition_to_dict(cond: Condition) -> dict:
    """Condition → JSON 可序列化字典"""
    d: dict = {
        "condition_type": cond.condition_type.name,
        "image_path": cond.image_path,
        "threshold": cond.threshold,
        "variable_name": cond.variable_name,
        "compare_op": cond.compare_op,
        "compare_value_x": cond.compare_value_x,
        "compare_value_y": cond.compare_value_y,
        "timeout_seconds": cond.timeout_seconds,
        "timer_name": cond.timer_name,
    }
    if cond.children:
        d["children"] = [condition_to_dict(c) for c in cond.children]
    return d


def dict_to_condition(data: dict) -> Condition:
    """JSON 字典 → Condition"""
    children: list[Condition] = []
    if "children" in data and data["children"]:
        children = [dict_to_condition(c) for c in data["children"]]
    return Condition(
        condition_type=ConditionType[data["condition_type"]],
        image_path=data.get("image_path", ""),
        threshold=data.get("threshold", 0.8),
        variable_name=data.get("variable_name", ""),
        compare_op=data.get("compare_op", ""),
        compare_value_x=data.get("compare_value_x", 0),
        compare_value_y=data.get("compare_value_y", 0),
        timeout_seconds=data.get("timeout_seconds", 0.0),
        timer_name=data.get("timer_name", ""),
        children=children,
    )


# ── FlowNode ────────────────────────────────────────────────

def flow_node_to_dict(node: FlowNode) -> dict:
    """FlowNode → JSON 可序列化字典（v3 含 error_config / breakpoint / fsm）"""
    d: dict = {
        "node_id": node.node_id,
        "node_type": node.node_type.name,
        "comment": node.comment,
        "enabled": node.enabled,
        "loop_count": node.loop_count,
        "pos_x": node.pos_x,
        "pos_y": node.pos_y,
    }
    if node.action is not None:
        d["action"] = step_to_dict(node.action)
    if node.condition is not None:
        d["condition"] = condition_to_dict(node.condition)
    if node.error_config is not None:
        d["error_config"] = node.error_config.to_dict()
    if node.breakpoint:
        d["breakpoint"] = True
    if node.fsm_transitions:
        d["fsm_transitions"] = [t.to_dict() for t in node.fsm_transitions]
    if node.fsm_global_transitions:
        d["fsm_global_transitions"] = [g.to_dict() for g in node.fsm_global_transitions]
    return d


def dict_to_flow_node(data: dict, profile_dir: str) -> FlowNode:
    """JSON 字典 → FlowNode"""
    node_type = NodeType[data["node_type"]]
    action: BaseStep | None = None
    condition: Condition | None = None

    if "action" in data and data["action"] is not None:
        action = dict_to_step(data["action"])
        if isinstance(action, ClickImageStep) and action.image_path:
            abs_path = os.path.normpath(os.path.join(profile_dir, action.image_path))
            action.image_path = abs_path

    if "condition" in data and data["condition"] is not None:
        condition = dict_to_condition(data["condition"])
        if condition.image_path:
            abs_path = os.path.normpath(os.path.join(profile_dir, condition.image_path))
            condition.image_path = abs_path

    error_config = None
    if data.get("error_config") is not None:
        error_config = ErrorConfig.from_dict(data["error_config"])
    breakpoint = data.get("breakpoint", False)
    fsm_transitions = [
        Transition.from_dict(t) for t in data.get("fsm_transitions", [])
    ]
    fsm_global_transitions = [
        GlobalTransition.from_dict(g) for g in data.get("fsm_global_transitions", [])
    ]

    return FlowNode(
        node_id=data["node_id"],
        node_type=node_type,
        action=action,
        condition=condition,
        comment=data.get("comment", ""),
        enabled=data.get("enabled", True),
        loop_count=data.get("loop_count", 0),
        pos_x=data.get("pos_x", 0),
        pos_y=data.get("pos_y", 0),
        error_config=error_config,
        breakpoint=breakpoint,
        fsm_transitions=fsm_transitions,
        fsm_global_transitions=fsm_global_transitions,
    )


# ── FlowEdge ────────────────────────────────────────────────

def flow_edge_to_dict(edge: FlowEdge) -> dict:
    """FlowEdge → JSON 可序列化字典"""
    return {
        "edge_id": edge.edge_id,
        "from_node": edge.from_node,
        "to_node": edge.to_node,
        "label": edge.label,
        "priority": edge.priority,
    }


def dict_to_flow_edge(data: dict) -> FlowEdge:
    """JSON 字典 → FlowEdge"""
    return FlowEdge(
        edge_id=data["edge_id"],
        from_node=data["from_node"],
        to_node=data["to_node"],
        label=data.get("label", "default"),
        priority=data.get("priority", 0),
    )


# ── MonitorConfig ───────────────────────────────────────────

def monitor_to_dict(mon: MonitorConfig) -> dict:
    """MonitorConfig → JSON 可序列化字典"""
    return {
        "name": mon.name,
        "enabled": mon.enabled,
        "image_path": mon.image_path,
        "threshold": mon.threshold,
        "check_interval": mon.check_interval,
        "handler_action": mon.handler_action.name,
        "handler_image_path": mon.handler_image_path,
        "priority": mon.priority,
        "max_consecutive": mon.max_consecutive,
        "cooldown": mon.cooldown,
    }


def dict_to_monitor(data: dict, profile_dir: str) -> MonitorConfig:
    """JSON 字典 → MonitorConfig"""
    handler_action = FoundAction.LEFT_CLICK
    if "handler_action" in data:
        handler_action = resolve_found_action(data["handler_action"])

    image_path = data.get("image_path", "")
    if image_path:
        image_path = os.path.normpath(os.path.join(profile_dir, image_path))
    handler_image_path = data.get("handler_image_path", "")
    if handler_image_path:
        handler_image_path = os.path.normpath(
            os.path.join(profile_dir, handler_image_path)
        )

    return MonitorConfig(
        name=data.get("name", ""),
        enabled=data.get("enabled", True),
        image_path=image_path,
        threshold=data.get("threshold", 0.8),
        check_interval=data.get("check_interval", 1.0),
        handler_action=handler_action,
        handler_image_path=handler_image_path,
        priority=data.get("priority", 0),
        max_consecutive=data.get("max_consecutive", 3),
        cooldown=data.get("cooldown", 2.0),
    )
