"""palette_data — 共享的节点调色板注册表。

ActionType / NodeType → i18n key 的映射，
供 WorkflowPage 和 NodeCreationPopup 共同使用。
"""

from src.core.action import ActionType
from src.core.flow import NodeType

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
