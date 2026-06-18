"""关键参数集中配置：ActionType → [(字段名, i18n_key)]。Qt/tk 共用。

字段选择规则：用户最常调整的——坐标 / 阈值 / 时间 / 按键 / 检测模式 / 重试 / 方向。
详情面板「关键参数」区按此渲染；未列出的 ActionType 降级为只显示「全部字段」表。
字段名必须与 ``step_types.py`` 中 dataclass 字段一致，否则取值降级为 ``--``。
"""

from __future__ import annotations

from src.core.action import ActionType

KEY_FIELDS: dict[ActionType, list[tuple[str, str]]] = {
    ActionType.CLICK_IMAGE: [
        ("image_path", "chain.kf.image_path"),
        ("threshold", "chain.kf.threshold"),
        ("detect_mode", "chain.kf.detect_mode"),
        ("found_action", "chain.kf.found_action"),
        ("retry_count", "chain.kf.retry_count"),
    ],
    ActionType.CLICK_POS: [
        ("pos_x", "chain.kf.pos_x"),
        ("pos_y", "chain.kf.pos_y"),
        ("clicks", "chain.kf.clicks"),
        ("button", "chain.kf.button"),
        ("hold_duration", "chain.kf.hold_duration"),
    ],
    ActionType.PRESS_KEY: [
        ("key", "chain.kf.key"),
        ("text", "chain.kf.text"),
    ],
    ActionType.HOLD_KEY: [
        ("keys_hold", "chain.kf.keys_hold"),
        ("hold_duration", "chain.kf.hold_duration"),
    ],
    ActionType.MOUSE_SCROLL: [
        ("scroll_clicks", "chain.kf.scroll_clicks"),
        ("scroll_delta_x", "chain.kf.scroll_delta_x"),
        ("pos_x", "chain.kf.pos_x"),
        ("pos_y", "chain.kf.pos_y"),
    ],
    ActionType.MOUSE_MOVE: [
        ("offset_x", "chain.kf.offset_x"),
        ("offset_y", "chain.kf.offset_y"),
        ("move_speed", "chain.kf.move_speed"),
        ("button", "chain.kf.button"),
    ],
    ActionType.WAIT: [
        ("wait_seconds", "chain.kf.wait_seconds"),
    ],
    ActionType.WAIT_RANDOM: [
        ("wait_min", "chain.kf.wait_min"),
        ("wait_max", "chain.kf.wait_max"),
    ],
    ActionType.KEY_COMBO: [
        ("combo_keys", "chain.kf.combo_keys"),
        ("combo_mode", "chain.kf.combo_mode"),
        ("hold_duration", "chain.kf.hold_duration"),
    ],
    ActionType.MULTI_KEY_SEQUENCE: [
        ("key_sequence", "chain.kf.key_sequence"),
        ("key_interval_min", "chain.kf.key_interval_min"),
        ("key_interval_max", "chain.kf.key_interval_max"),
    ],
    ActionType.IDLE_BEHAVIOR: [
        ("idle_duration", "chain.kf.idle_duration"),
        ("jitter_intensity", "chain.kf.jitter_intensity"),
        ("idle_actions", "chain.kf.idle_actions"),
    ],
    ActionType.START_TIMER: [
        ("timer_name", "chain.kf.timer_name"),
        ("timer_timeout", "chain.kf.timer_timeout"),
    ],
    ActionType.PIXEL_SEARCH: [
        ("target_color", "chain.kf.target_color"),
        ("color_tolerance", "chain.kf.color_tolerance"),
        ("color_mode", "chain.kf.color_mode"),
        ("color_preset", "chain.kf.color_preset"),
    ],
    ActionType.OCR_CHECK: [
        ("target_text", "chain.kf.target_text"),
        ("ocr_fuzzy", "chain.kf.ocr_fuzzy"),
    ],
    ActionType.MOUSE_DRAG: [
        ("start_x", "chain.kf.start_x"),
        ("start_y", "chain.kf.start_y"),
        ("end_x", "chain.kf.end_x"),
        ("end_y", "chain.kf.end_y"),
        ("button", "chain.kf.button"),
        ("duration", "chain.kf.duration"),
    ],
    ActionType.SUB_GRAPH: [
        ("graph_ref", "chain.kf.graph_ref"),
    ],
}


def key_fields_for(step) -> list[tuple[str, str]]:
    """返回该步骤的关键字段配置 [(字段名, i18n_key)]；无配置返回 []。"""
    return KEY_FIELDS.get(getattr(step, "action_type", None), [])
