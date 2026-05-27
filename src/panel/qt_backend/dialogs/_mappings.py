"""共享 I18N 映射表 — FoundAction / DetectMode 的翻译 key。"""

from src.core.action import DetectMode, FoundAction

_FOUND_ACTION_I18N = {
    FoundAction.LEFT_CLICK: "dialog.found_action.left_click",
    FoundAction.RIGHT_CLICK: "dialog.found_action.right_click",
    FoundAction.LEFT_DOUBLE_CLICK: "dialog.found_action.left_double_click",
    FoundAction.RIGHT_DOUBLE_CLICK: "dialog.found_action.right_double_click",
    FoundAction.LONG_PRESS: "dialog.found_action.long_press",
    FoundAction.DRAG_TO: "dialog.found_action.drag_to",
    FoundAction.ONLY_MOVE: "dialog.found_action.only_move",
    FoundAction.OUTPUT_COORD: "dialog.found_action.output_coord",
}

_DETECT_MODE_I18N = {
    DetectMode.WAIT_UNTIL_FOUND: "dialog.detect_mode.wait_until_found",
    DetectMode.SKIP_IF_NOT_FOUND: "dialog.detect_mode.skip_if_not_found",
    DetectMode.FAIL_IF_NOT_FOUND: "dialog.detect_mode.fail_if_not_found",
}
