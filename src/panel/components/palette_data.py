"""palette_data — 共享的节点调色板注册表。

ActionType / NodeType → i18n key + accent color 的映射，
供 WorkflowPage、ActionChainPage、StepPalette 共同使用。
"""

from src.core.action import ActionType
from src.core.flow import NodeType

# ── 动作类型 accent 颜色（theme token 名称）────────────────────

_ACTION_ACCENT: dict[ActionType, str] = {
    ActionType.CLICK_IMAGE: "accent_blue",
    ActionType.WAIT: "accent_green",
    ActionType.WAIT_RANDOM: "accent_green",
    ActionType.PRESS_KEY: "accent_orange",
    ActionType.CLICK_POS: "accent_red",
    ActionType.MOUSE_SCROLL: "accent_orange",
    ActionType.HOLD_KEY: "accent_mauve",
    ActionType.MOUSE_MOVE: "accent_teal",
    ActionType.MOUSE_DRAG: "accent_orange",
    ActionType.KEY_COMBO: "accent_mauve",
    ActionType.MULTI_KEY_SEQUENCE: "accent_teal",
    ActionType.IDLE_BEHAVIOR: "accent_gray",
    ActionType.START_TIMER: "accent_teal",
}

_ACTION_DEFAULT_ACCENT = "accent_blue"

# ── 流程节点 accent 颜色 ──────────────────────────────────────

_FLOW_ACCENT: dict[NodeType, str] = {
    NodeType.START: "accent_green",
    NodeType.END: "accent_red",
    NodeType.CONDITION: "accent_orange",
    NodeType.MERGE: "accent_gray",
    NodeType.LOOP: "accent_mauve",
}

_FLOW_DEFAULT_ACCENT = "accent_blue"

# ── 调色板数据 ────────────────────────────────────────────────

ACTION_PALETTE: list[tuple[ActionType, str]] = [
    (ActionType.CLICK_IMAGE, "action_type.click_image"),
    (ActionType.WAIT, "action_type.wait"),
    (ActionType.WAIT_RANDOM, "action_type.wait_random"),
    (ActionType.PRESS_KEY, "action_type.press_key"),
    (ActionType.CLICK_POS, "action_type.click_pos"),
    (ActionType.MOUSE_SCROLL, "action_type.scroll"),
    (ActionType.HOLD_KEY, "action_type.hold_key"),
    (ActionType.MOUSE_MOVE, "action_type.mouse_move"),
    (ActionType.MOUSE_DRAG, "action_type.mouse_drag"),
    (ActionType.KEY_COMBO, "action_type.key_combo"),
    (ActionType.MULTI_KEY_SEQUENCE, "action_type.multi_key"),
    (ActionType.IDLE_BEHAVIOR, "action_type.idle"),
    (ActionType.START_TIMER, "action_type.start_timer"),
]

FLOW_PALETTE: list[tuple[NodeType, str]] = [
    (NodeType.START, "workflow.palette.start"),
    (NodeType.END, "workflow.palette.end"),
    (NodeType.CONDITION, "workflow.palette.condition"),
    (NodeType.MERGE, "workflow.palette.merge"),
    (NodeType.LOOP, "workflow.palette.loop"),
]

# ── 颜色查询 ─────────────────────────────────────────────────


def action_accent(action_type: ActionType) -> str:
    """返回动作类型对应的主题 accent token 名称。"""
    return _ACTION_ACCENT.get(action_type, _ACTION_DEFAULT_ACCENT)


def flow_accent(node_type: NodeType) -> str:
    """返回流程节点类型对应的主题 accent token 名称。"""
    return _FLOW_ACCENT.get(node_type, _FLOW_DEFAULT_ACCENT)


# ── 帮助标签页数据 ─────────────────────────────────────────────

HELP_ACTION_ITEMS: list[tuple[str, str]] = [
    # (name_i18n_key, desc_i18n_key)
    ("action_type.click_image", "workflow.help.click_image"),
    ("action_type.wait", "workflow.help.wait"),
    ("action_type.wait_random", "workflow.help.wait_random"),
    ("action_type.press_key", "workflow.help.press_key"),
    ("action_type.click_pos", "workflow.help.click_pos"),
    ("action_type.scroll", "workflow.help.mouse_scroll"),
    ("action_type.hold_key", "workflow.help.hold_key"),
    ("action_type.mouse_move", "workflow.help.mouse_move"),
    ("action_type.mouse_drag", "workflow.help.mouse_drag"),
    ("action_type.key_combo", "workflow.help.key_combo"),
    ("action_type.multi_key", "workflow.help.multi_key_sequence"),
    ("action_type.idle", "workflow.help.idle_behavior"),
    ("action_type.start_timer", "workflow.help.start_timer"),
]

HELP_FLOW_ITEMS: list[tuple[str, str]] = [
    ("workflow.node.start", "workflow.help.start"),
    ("workflow.node.end", "workflow.help.end"),
    ("workflow.node.condition", "workflow.help.condition"),
    ("workflow.node.merge", "workflow.help.merge"),
    ("workflow.node.loop", "workflow.help.loop"),
]
