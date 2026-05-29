"""node_shared — tkinter / Qt 共享的节点尺寸、图标、标签等常量和纯函数。

两个后端（tkinter node_renderer.py, Qt node_item.py）共享同一份
节点规格、图标、标签和端口位置计算，避免数据漂移。
"""

import os

from src.core.action import ActionType
from src.core.condition import ConditionType
from src.core.flow import FlowNode, NodeType
from src.core.step_types import (
    ClickPosStep,
    HoldKeyStep,
    KeyComboStep,
    MultiKeySequenceStep,
    OcrCheckStep,
    PixelSearchStep,
    StartTimerStep,
)
from src.panel.models.enums import EdgeLabel
from src.utils.i18n import t
from src.utils.text import truncate

# ── 分段高度 (px, 世界坐标) ─────────────────────────────

HEADER_H = 24
BODY_H = 36
PORT_STRIP_H = 12

# ── 按类型分组: (width, height, header_h, body_h, port_strip_h) ──

# ── 自动布局常量 ─────────────────────────────────────────

LAYOUT_START_X = 300
LAYOUT_START_Y = 40
LAYOUT_SPACING_Y = 100

NODE_SPECS: dict[NodeType, tuple[float, float, float, float, float]] = {
    NodeType.START: (140, 56, HEADER_H, 20, PORT_STRIP_H),
    NodeType.END: (140, 56, HEADER_H, 20, PORT_STRIP_H),
    NodeType.ACTION: (210, 80, HEADER_H, 44, PORT_STRIP_H),
    NodeType.CONDITION: (220, 80, HEADER_H, 44, PORT_STRIP_H),
    NodeType.MERGE: (180, 60, HEADER_H, 24, PORT_STRIP_H),
    NodeType.LOOP: (220, 80, HEADER_H, 44, PORT_STRIP_H),
}

# ── 端口 / 视觉常量 ─────────────────────────────────────

PORT_RADIUS = 10          # 命中检测半径
PORT_VISUAL_RADIUS = 7    # 实际可见半径（菱形半轴/圆形半径）
PORT_DOT_SCALE = 0.5      # (legacy, Qt minimal LOD 使用)
PORT_LABEL_OFFSET = 0.7
PORT_LABEL_WIDTH = 60
PORT_LABEL_HEIGHT = 12
PORT_HIT_RADIUS = 20
PORT_OUT_PREFIX = "out_"
PORT_IN = "in"
PORT_OUT_DEFAULT = "out_default"
PORT_OUT_TRUE = "out_true"
PORT_OUT_FALSE = "out_false"
PORT_OUT_LOOP = "out_loop"
PORT_OUT_EXIT = "out_exit"
CORNER_RADIUS = 8
LOD_FULL = "full"
LOD_SIMPLIFIED = "simplified"
LOD_MINIMAL = "minimal"

# ── Canvas tag 常量（tkinter hit-test / 样式选择）─────────
TAG_SELECTABLE = "selectable"
TAG_SELECTION_RING = "selection_ring"
TAG_SELECTION_HIGHLIGHT = "selection_highlight"
TAG_SELECT_RECT = "select_rect"
TAG_PORT = "port"
TAG_PORT_IN = "port_in"
TAG_PORT_OUT = "port_out"
TAG_PORT_IN_ARROW = "port_in_arrow"
TAG_PORT_OUT_ARROW = "port_out_arrow"

# ── Font weight ──────────────────────────────────────────
FONT_BOLD = "bold"
FONT_NORMAL = "normal"

# ── 类型 → Unicode 图标 ─────────────────────────────────

NODE_ICONS: dict[NodeType, str] = {
    NodeType.START: "▶",
    NodeType.END: "■",
    NodeType.ACTION: "⚡",
    NodeType.CONDITION: "◇",
    NodeType.MERGE: "⊞",
    NodeType.LOOP: "↺",
}

# ── 类型 → 标签（延迟构建，避免 import 时 i18n 未就绪）──

_TYPE_LABEL_KEYS: dict[NodeType, str] = {
    NodeType.START: "workflow.node.start",
    NodeType.END: "workflow.node.end",
    NodeType.ACTION: "workflow.node.action",
    NodeType.CONDITION: "workflow.node.condition",
    NodeType.MERGE: "workflow.node.merge",
    NodeType.LOOP: "workflow.node.loop",
}

# ── 端口短名（延迟构建）────────────────────────────────

_PORT_SHORT_NAME_KEYS: dict[str, str] = {
    f"out_{EdgeLabel.TRUE}": "workflow.edge.true",
    f"out_{EdgeLabel.FALSE}": "workflow.edge.false",
    f"out_{EdgeLabel.LOOP}": "workflow.edge.loop",
    f"out_{EdgeLabel.EXIT}": "workflow.edge.exit",
}

# ActionType → i18n key (Body 第一行: 具体动作类型标签)
_ACTION_TYPE_LABEL_KEYS: dict[ActionType, str] = {
    ActionType.CLICK_IMAGE: "action_type.click_image",
    ActionType.CLICK_POS: "action_type.click_pos",
    ActionType.PRESS_KEY: "action_type.press_key",
    ActionType.HOLD_KEY: "action_type.hold_key",
    ActionType.MOUSE_SCROLL: "action_type.mouse_scroll",
    ActionType.MOUSE_MOVE: "action_type.mouse_move",
    ActionType.MOUSE_DRAG: "action_type.mouse_drag",
    ActionType.WAIT: "action_type.wait",
    ActionType.WAIT_RANDOM: "action_type.wait_random",
    ActionType.KEY_COMBO: "action_type.key_combo",
    ActionType.MULTI_KEY_SEQUENCE: "action_type.multi_key",
    ActionType.IDLE_BEHAVIOR: "action_type.idle",
    ActionType.START_TIMER: "action_type.start_timer",
    ActionType.PIXEL_SEARCH: "action_type.pixel_search",
    ActionType.OCR_CHECK: "action_type.ocr_check",
}


# ── 纯函数 ────────────────────────────────────────────────

def node_spec(node: FlowNode) -> tuple[float, float, float, float, float]:
    """返回 (width, height, header_h, body_h, port_strip_h)。"""
    return NODE_SPECS.get(node.node_type, NODE_SPECS[NodeType.ACTION])


def node_size(node: FlowNode) -> tuple[float, float]:
    w, h, *_ = node_spec(node)
    return w, h


def node_intersects_rect(
    node: FlowNode, wx1: float, wy1: float, wx2: float, wy2: float,
) -> bool:
    nw, nh = node_size(node)
    return node.pos_x + nw >= wx1 and node.pos_x <= wx2 \
        and node.pos_y + nh >= wy1 and node.pos_y <= wy2


def port_positions(node: FlowNode) -> dict[str, tuple[float, float]]:
    """计算节点的所有端口世界坐标。"""
    w, h, *_ = node_spec(node)
    cx = node.pos_x + w / 2
    positions: dict[str, tuple[float, float]] = {}

    match node.node_type:
        case NodeType.START:
            positions[PORT_IN] = (cx, node.pos_y)
            positions[PORT_OUT_DEFAULT] = (cx, node.pos_y + h)
        case NodeType.END:
            positions[PORT_IN] = (cx, node.pos_y)
            positions[PORT_OUT_LOOP] = (node.pos_x + w * 0.3, node.pos_y + h)
        case NodeType.CONDITION:
            positions[PORT_IN] = (cx, node.pos_y)
            positions[PORT_OUT_TRUE] = (node.pos_x + w * 0.3, node.pos_y + h)
            positions[PORT_OUT_FALSE] = (node.pos_x + w * 0.7, node.pos_y + h)
        case NodeType.LOOP:
            positions[PORT_IN] = (cx, node.pos_y)
            positions[PORT_OUT_LOOP] = (node.pos_x + w * 0.3, node.pos_y + h)
            positions[PORT_OUT_EXIT] = (node.pos_x + w * 0.7, node.pos_y + h)
        case NodeType.ACTION | NodeType.MERGE:
            positions[PORT_IN] = (cx, node.pos_y)
            positions[PORT_OUT_DEFAULT] = (cx, node.pos_y + h)

    return positions


def type_label(node_type: NodeType) -> str:
    key = _TYPE_LABEL_KEYS.get(node_type)
    return t(key) if key else ""


def port_label(node_type: NodeType, port_name: str) -> str:
    """获取端口标签文本，END 节点的 out_loop 使用「循环起点」。"""
    if node_type == NodeType.END and port_name == PORT_OUT_LOOP:
        return t("workflow.edge.loop_start")
    key = _PORT_SHORT_NAME_KEYS.get(port_name)
    return t(key) if key else ""


def lod_level(zoom: float) -> str:
    """返回 LOD 级别: 'full' | 'simplified' | 'minimal'。"""
    if zoom >= 0.8:
        return LOD_FULL
    elif zoom >= 0.4:
        return LOD_SIMPLIFIED
    else:
        return LOD_MINIMAL


def action_type_label(action_type: ActionType) -> str:
    """将 ActionType 枚举转为短标签 (如 CLICK_IMAGE → '模板匹配')。"""
    key = _ACTION_TYPE_LABEL_KEYS.get(action_type)
    return t(key) if key else action_type.name




def body_text_lines(node: FlowNode) -> tuple[str, str]:
    """返回节点 Body 的两行文本: (line1, line2)。

    line1: 具体 ActionType 标签或通用类型标签。
    line2: 配置摘要，无摘要时为空字符串。
    """
    if node.node_type == NodeType.ACTION and node.action:
        line1 = action_type_label(node.action.action_type)
    else:
        line1 = type_label(node.node_type)
    line2 = action_summary(node)
    return line1, line2


def action_summary(node: FlowNode) -> str:
    """提取节点关键配置参数作为 Body 第二行摘要。"""
    if node.node_type == NodeType.ACTION and node.action:
        action = node.action
        match action.action_type:
            case ActionType.CLICK_IMAGE:
                return truncate(os.path.basename(action.image_path), 22) if action.image_path else ""
            case ActionType.CLICK_POS:
                if isinstance(action, ClickPosStep) and action.use_coord_var and action.coord_var_name:
                    return f"${action.coord_var_name}"
                return f"({action.pos_x}, {action.pos_y})"
            case ActionType.PRESS_KEY:
                return truncate(action.key or action.text or "", 18)
            case ActionType.HOLD_KEY:
                keys = action.keys_hold if isinstance(action, HoldKeyStep) else (action.key or "")
                return truncate(keys, 18)
            case ActionType.WAIT:
                return f"{action.wait_seconds}s"
            case ActionType.WAIT_RANDOM:
                return f"{action.wait_min}~{action.wait_max}s"
            case ActionType.KEY_COMBO:
                return truncate(action.combo_keys if isinstance(action, KeyComboStep) else "", 18)
            case ActionType.MULTI_KEY_SEQUENCE:
                return truncate(action.key_sequence if isinstance(action, MultiKeySequenceStep) else "", 18)
            case ActionType.MOUSE_SCROLL:
                return f"±{abs(action.scroll_clicks)}"
            case ActionType.MOUSE_MOVE | ActionType.MOUSE_DRAG:
                return ""
            case ActionType.IDLE_BEHAVIOR:
                return f"{action.idle_duration}s"
            case ActionType.START_TIMER:
                return truncate(action.timer_name if isinstance(action, StartTimerStep) else "", 16)
            case ActionType.PIXEL_SEARCH:
                color = (action.color_preset or action.target_color) if isinstance(action, PixelSearchStep) else ""
                return truncate(str(color), 16)
            case ActionType.OCR_CHECK:
                return truncate(action.target_text if isinstance(action, OcrCheckStep) else "", 20)
            case _:
                return ""
    elif node.node_type == NodeType.CONDITION and node.condition:
        cond = node.condition
        match cond.condition_type:
            case ConditionType.IMAGE_FOUND | ConditionType.IMAGE_NOT_FOUND:
                return truncate(os.path.basename(cond.image_path), 22) if cond.image_path else ""
            case ConditionType.ELAPSED_TIME:
                return f"{cond.timeout_seconds}s"
            case ConditionType.VARIABLE_EXISTS | ConditionType.VARIABLE_COMPARE:
                return truncate(cond.variable_name or "", 18)
            case _:
                return ""
    elif node.node_type == NodeType.LOOP:
        return t("flow.node.infinite") if node.loop_count == 0 else f"×{node.loop_count}"
    return ""


def execution_state_theme_key(state: str) -> str | None:
    """将 NodeExecutionState 映射为 theme 属性名，无匹配返回 None。"""
    _STATE_THEME_KEYS: dict[str, str] = {
        "running": "status_running",
        "success": "status_success",
        "error": "status_error",
        "paused": "status_paused",
        "disabled": "accent_mauve",
    }
    return _STATE_THEME_KEYS.get(state)
