"""动作类型定义 — 枚举类型。

ActionStep 和 ActionChain 已移除，统一使用 src.core.step_types 中的类型化 Step 类。
"""

from enum import Enum, auto


class ActionType(Enum):
    """动作类型"""
    CLICK_IMAGE = auto()
    WAIT = auto()
    WAIT_RANDOM = auto()
    PRESS_KEY = auto()
    CLICK_POS = auto()
    MOUSE_SCROLL = auto()
    HOLD_KEY = auto()
    MOUSE_MOVE = auto()
    MOUSE_DRAG = auto()
    KEY_COMBO = auto()
    MULTI_KEY_SEQUENCE = auto()
    IDLE_BEHAVIOR = auto()
    START_TIMER = auto()
    PIXEL_SEARCH = auto()
    OCR_CHECK = auto()
    SUB_GRAPH = auto()


class FoundAction(Enum):
    """图片检测到后执行的操作（始终先移动到图片中心，再执行操作）"""
    LEFT_CLICK = "left_click"
    RIGHT_CLICK = "right_click"
    LEFT_DOUBLE_CLICK = "left_double_click"
    RIGHT_DOUBLE_CLICK = "right_double_click"
    LONG_PRESS = "long_press"
    DRAG_TO = "drag_to"
    ONLY_MOVE = "only_move"
    OUTPUT_COORD = "output_coord"

    @classmethod
    def _missing_(cls, value: object) -> "FoundAction | None":
        _LEGACY: dict[str, str] = {
            "左键点击": "left_click", "右键点击": "right_click",
            "左键双击": "left_double_click", "右键双击": "right_double_click",
            "长按": "long_press", "拖拽到偏移位置": "drag_to",
            "仅移动（不点击）": "only_move", "输出中心点坐标": "output_coord",
        }
        if isinstance(value, str) and value in _LEGACY:
            return cls(_LEGACY[value])
        return None


class DetectMode(Enum):
    """图片检测模式"""
    WAIT_UNTIL_FOUND = "wait_until_found"
    SKIP_IF_NOT_FOUND = "skip_if_not_found"
    FAIL_IF_NOT_FOUND = "fail_if_not_found"

    @classmethod
    def _missing_(cls, value: object) -> "DetectMode | None":
        _LEGACY: dict[str, str] = {
            "一直等待直到检测到": "wait_until_found",
            "未找到则跳过": "skip_if_not_found",
            "未找到则停止": "fail_if_not_found",
        }
        if isinstance(value, str) and value in _LEGACY:
            return cls(_LEGACY[value])
        return None


