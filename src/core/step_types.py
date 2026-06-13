"""类型化动作步骤 — 每种 ActionType 对应一个独立的 dataclass。

替代已移除的 ActionStep 单一 dataclass（42 个字段），
每个类型化 Step 仅包含该 ActionType 相关的字段（2-13 个）。

序列化兼容：
- 类型化 Step 与旧 ActionStep 字段名完全一致
- 序列化输出与旧格式完全相同（profile.json 格式不变）
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar, Union

from src.core.action import ActionType, DetectMode, FoundAction, MatchStrategy, ThresholdMode
from src.utils.i18n import t


@dataclass
class BaseStep(ABC):
    """所有步骤类型的抽象基类。"""

    enabled: bool = True
    comment: str = ""
    recorded_duration: float = 0.0

    @property
    @abstractmethod
    def action_type(self) -> ActionType:
        ...

    @abstractmethod
    def describe(self) -> str:
        ...


# ── CLICK_IMAGE ────────────────────────────────────────────


@dataclass
class ClickImageStep(BaseStep):
    action_type: ClassVar[ActionType] = ActionType.CLICK_IMAGE

    image_path: str = ""
    threshold: float = 0.8
    detect_mode: DetectMode = DetectMode.SKIP_IF_NOT_FOUND
    retry_count: int = 0
    found_action: FoundAction = FoundAction.LEFT_CLICK
    save_coord_name: str = ""
    retry_wait_min: float = 0.5
    retry_wait_max: float = 1.5
    offset_x: int = 0
    offset_y: int = 0
    drag_offset_x: int = 0
    drag_offset_y: int = 0
    hold_duration: float = 0.5
    # ── 多模板字段(增量式,旧 profile 零修改兼容)──
    # 备用模板路径(状态变体);主图 image_path 永远第一个,顺序 = 命中优先级
    alt_image_paths: list[str] = field(default_factory=list)
    # 与 alt_image_paths 平行;None = 继承全局/自动;具体浮点 = 独立覆盖
    alt_thresholds: list[float | None] = field(default_factory=list)
    # 匹配编排策略
    match_strategy: MatchStrategy = MatchStrategy.ADAPTIVE
    # 阈值模式(数据模型默认 GLOBAL,保旧 profile 零漂移;对话框新建默认 AUTO)
    threshold_mode: ThresholdMode = ThresholdMode.GLOBAL

    def describe(self) -> str:

        name = os.path.basename(self.image_path) if self.image_path else t("common.not_set")
        fa_keys = {
            "LEFT_CLICK": "dialog.found_action.left_click",
            "RIGHT_CLICK": "dialog.found_action.right_click",
            "LEFT_DOUBLE_CLICK": "dialog.found_action.left_double_click",
            "RIGHT_DOUBLE_CLICK": "dialog.found_action.right_double_click",
            "LONG_PRESS": "dialog.found_action.long_press",
            "DRAG_TO": "dialog.found_action.drag_to",
            "ONLY_MOVE": "dialog.found_action.only_move",
            "OUTPUT_COORD": "dialog.found_action.output_coord",
        }
        action_label = t(fa_keys.get(self.found_action.name, ""))
        return t("action.describe.click_image", name=name, action=action_label)


# ── CLICK_POS ──────────────────────────────────────────────


@dataclass
class ClickPosStep(BaseStep):
    action_type: ClassVar[ActionType] = ActionType.CLICK_POS

    pos_x: int = 0
    pos_y: int = 0
    use_coord_var: bool = False
    coord_var_name: str = ""
    clicks: int = 1
    button: str = "left"
    hold_duration: float = 0.0
    path_points: list[tuple[int, int, float]] = field(default_factory=list)
    move_speed: float = 0.5

    def describe(self) -> str:

        if self.use_coord_var and self.coord_var_name:
            return t("action.describe.click_var", name=self.coord_var_name)
        click_labels = {
            1: t("action.describe.single_click"),
            2: t("action.describe.double_click"),
            3: t("action.describe.triple_click"),
        }
        click_label = click_labels.get(
            self.clicks,
            t("action.describe.multi_click", count=self.clicks),
        )
        button_prefix = ""
        if self.button == "right":
            button_prefix = t("action.describe.right_prefix")
        elif self.button == "middle":
            button_prefix = t("action.describe.middle_prefix")
        desc = f"{button_prefix}{click_label} ({self.pos_x}, {self.pos_y})"
        if self.hold_duration > 0.3:
            desc += f" ({t('action.describe.hold_label', duration=self.hold_duration)})"
        return desc


# ── PRESS_KEY ──────────────────────────────────────────────


@dataclass
class PressKeyStep(BaseStep):
    action_type: ClassVar[ActionType] = ActionType.PRESS_KEY

    key: str = ""
    text: str = ""

    def describe(self) -> str:

        if self.text:
            return t("action.describe.type_text", text=self.text[:30])
        key_display = (
            t("action.key.mouse_left") if self.key == "mouse_left" else
            t("action.key.mouse_middle") if self.key == "mouse_middle" else
            t("action.key.mouse_right") if self.key == "mouse_right" else
            self.key
        )
        return t("action.describe.press_key", key_name=key_display)


# ── HOLD_KEY ───────────────────────────────────────────────


@dataclass
class HoldKeyStep(BaseStep):
    action_type: ClassVar[ActionType] = ActionType.HOLD_KEY

    keys_hold: str = ""
    key: str = ""
    hold_duration: float = 0.0

    def describe(self) -> str:

        keys = self.keys_hold or self.key

        def _key_name(k: str) -> str:
            k = k.strip()
            return (
                t("action.key.mouse_left") if k == "mouse_left" else
                t("action.key.mouse_middle") if k == "mouse_middle" else
                t("action.key.mouse_right") if k == "mouse_right" else k
            )

        names = [_key_name(k) for k in keys.split(",")]
        return t("action.describe.hold_key", keys="+".join(names), duration=self.hold_duration)


# ── MOUSE_SCROLL ───────────────────────────────────────────


@dataclass
class MouseScrollStep(BaseStep):
    action_type: ClassVar[ActionType] = ActionType.MOUSE_SCROLL

    scroll_clicks: int = 3
    scroll_delta_x: int = 0
    pos_x: int = 0
    pos_y: int = 0

    def describe(self) -> str:

        parts = []
        if self.scroll_clicks != 0:
            d = t("action.describe.scroll_up") if self.scroll_clicks > 0 else t("action.describe.scroll_down")
            parts.append(t("action.describe.scroll", direction=d, amount=abs(self.scroll_clicks)))
        if self.scroll_delta_x != 0:
            d = t("action.describe.scroll_left") if self.scroll_delta_x < 0 else t("action.describe.scroll_right")
            parts.append(t("action.describe.scroll", direction=d, amount=abs(self.scroll_delta_x)))
        return " ".join(parts) if parts else t("action.describe.scroll", direction="", amount=0)


# ── MOUSE_MOVE ─────────────────────────────────────────────


@dataclass
class MouseMoveStep(BaseStep):
    """鼠标移动 — 支持无按键移动和按住按键拖拽。"""

    action_type: ClassVar[ActionType] = ActionType.MOUSE_MOVE

    offset_x: int = 0
    offset_y: int = 0
    move_speed: float = 0.5
    curve_amount: float = 0.0
    path_points: list[tuple[int, int, float]] = field(default_factory=list)
    button: str = ""

    def describe(self) -> str:

        parts = []
        btn_label = ""
        if self.button == "right":
            btn_label = t("action.describe.right_prefix")
        elif self.button == "middle":
            btn_label = t("action.describe.middle_prefix")
        if self.offset_x != 0:
            parts.append(t("action.describe.horizontal", value=self.offset_x))
        if self.offset_y != 0:
            parts.append(t("action.describe.vertical", value=self.offset_y))
        desc = " ".join(parts) if parts else t("action.describe.no_offset")
        duration_str = f"{self.recorded_duration:.1f}s" if self.recorded_duration > 0 else ""
        if self.button:
            return t("action.describe.mouse_drag_move", button=btn_label, desc=desc, duration=duration_str)
        return t("action.describe.mouse_move", desc=desc, duration=duration_str)


# ── WAIT ───────────────────────────────────────────────────


@dataclass
class WaitStep(BaseStep):
    action_type: ClassVar[ActionType] = ActionType.WAIT

    wait_seconds: float = 1.0

    def describe(self) -> str:

        return t("action.describe.wait", seconds=self.wait_seconds)


# ── WAIT_RANDOM ────────────────────────────────────────────


@dataclass
class WaitRandomStep(BaseStep):
    action_type: ClassVar[ActionType] = ActionType.WAIT_RANDOM

    wait_min: float = 0.5
    wait_max: float = 2.0

    def describe(self) -> str:

        return t("action.describe.wait_random", min=self.wait_min, max=self.wait_max)


# ── KEY_COMBO ──────────────────────────────────────────────


@dataclass
class KeyComboStep(BaseStep):
    action_type: ClassVar[ActionType] = ActionType.KEY_COMBO

    combo_keys: str = ""
    combo_mode: str = "hold_tap"
    hold_duration: float = 0.0

    def describe(self) -> str:

        mode_map = {
            "hold_tap": "common.mode.hold_tap",
            "sequence": "common.mode.sequence",
            "all_hold": "common.mode.all_hold",
        }
        mode_name = t(mode_map.get(self.combo_mode, ""))
        return t("action.describe.key_combo", keys=self.combo_keys, mode=mode_name)


# ── MULTI_KEY_SEQUENCE ─────────────────────────────────────


@dataclass
class MultiKeySequenceStep(BaseStep):
    action_type: ClassVar[ActionType] = ActionType.MULTI_KEY_SEQUENCE

    key_sequence: str = ""
    key_interval_min: float = 0.1
    key_interval_max: float = 0.3

    def describe(self) -> str:

        return t(
            "action.describe.multi_key_sequence",
            keys=self.key_sequence,
            min=self.key_interval_min,
            max=self.key_interval_max,
        )


# ── IDLE_BEHAVIOR ──────────────────────────────────────────


@dataclass
class IdleBehaviorStep(BaseStep):
    action_type: ClassVar[ActionType] = ActionType.IDLE_BEHAVIOR

    idle_duration: float = 3.0
    jitter_intensity: int = 3
    idle_actions: str = ""
    idle_action_chance: float = 0.2

    def describe(self) -> str:

        return t(
            "action.describe.idle",
            duration=self.idle_duration,
            jitter=self.jitter_intensity,
        )


# ── START_TIMER ────────────────────────────────────────────


@dataclass
class StartTimerStep(BaseStep):
    action_type: ClassVar[ActionType] = ActionType.START_TIMER

    timer_name: str = ""
    timer_timeout: float = 0.0

    def describe(self) -> str:

        if self.timer_timeout > 0:
            return t(
                "action.describe.start_timer_timeout",
                name=self.timer_name,
                seconds=self.timer_timeout,
            )
        return t("action.describe.start_timer", name=self.timer_name)


# ── PIXEL_SEARCH ───────────────────────────────────────────


@dataclass
class PixelSearchStep(BaseStep):
    action_type: ClassVar[ActionType] = ActionType.PIXEL_SEARCH

    target_color: tuple[int, int, int] | None = None
    color_tolerance: int = 10
    search_region: tuple[int, int, int, int] | None = None
    color_mode: str = "hsv"
    color_preset: str = ""

    def describe(self) -> str:

        color = self.color_preset or str(self.target_color)
        return t("action.describe.pixel_search", color=color, tolerance=self.color_tolerance)


# ── OCR_CHECK ──────────────────────────────────────────────


@dataclass
class OcrCheckStep(BaseStep):
    action_type: ClassVar[ActionType] = ActionType.OCR_CHECK

    target_text: str = ""
    ocr_region: tuple[int, int, int, int] | None = None
    ocr_fuzzy: bool = True

    def describe(self) -> str:

        return t("action.describe.ocr_check", text=self.target_text)


# ── MOUSE_DRAG ─────────────────────────────────────────────


@dataclass
class MouseDragStep(BaseStep):
    """鼠标拖拽 — 从起点按住拖拽到终点。"""

    action_type: ClassVar[ActionType] = ActionType.MOUSE_DRAG

    start_x: int = 0
    start_y: int = 0
    end_x: int = 0
    end_y: int = 0
    button: str = "left"
    duration: float = 0.5

    def describe(self) -> str:

        btn_label = ""
        if self.button == "right":
            btn_label = t("action.describe.right_prefix")
        elif self.button == "middle":
            btn_label = t("action.describe.middle_prefix")
        return t(
            "action.describe.mouse_drag",
            button=btn_label,
            start_x=self.start_x,
            start_y=self.start_y,
            end_x=self.end_x,
            end_y=self.end_y,
        )


@dataclass
class SubGraphStep(BaseStep):
    """子图嵌套 — 引用并执行另一个 FlowGraph 配置。"""

    action_type: ClassVar[ActionType] = ActionType.SUB_GRAPH

    graph_ref: str = ""

    def describe(self) -> str:
        return t("action.describe.sub_graph", ref=self.graph_ref or "?")


# ── 注册表 ─────────────────────────────────────────────────

STEP_CLASSES: dict[ActionType, type[BaseStep]] = {
    ActionType.CLICK_IMAGE: ClickImageStep,
    ActionType.CLICK_POS: ClickPosStep,
    ActionType.PRESS_KEY: PressKeyStep,
    ActionType.HOLD_KEY: HoldKeyStep,
    ActionType.MOUSE_SCROLL: MouseScrollStep,
    ActionType.MOUSE_MOVE: MouseMoveStep,
    ActionType.MOUSE_DRAG: MouseDragStep,
    ActionType.WAIT: WaitStep,
    ActionType.WAIT_RANDOM: WaitRandomStep,
    ActionType.KEY_COMBO: KeyComboStep,
    ActionType.MULTI_KEY_SEQUENCE: MultiKeySequenceStep,
    ActionType.IDLE_BEHAVIOR: IdleBehaviorStep,
    ActionType.START_TIMER: StartTimerStep,
    ActionType.PIXEL_SEARCH: PixelSearchStep,
    ActionType.OCR_CHECK: OcrCheckStep,
    ActionType.SUB_GRAPH: SubGraphStep,
}

Step = Union[
    ClickImageStep,
    ClickPosStep,
    PressKeyStep,
    HoldKeyStep,
    MouseScrollStep,
    MouseMoveStep,
    MouseDragStep,
    WaitStep,
    WaitRandomStep,
    KeyComboStep,
    MultiKeySequenceStep,
    IdleBehaviorStep,
    StartTimerStep,
    PixelSearchStep,
    OcrCheckStep,
    SubGraphStep,
]
