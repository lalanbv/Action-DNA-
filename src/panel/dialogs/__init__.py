"""步骤对话框 — 各类型步骤的编辑/添加对话框。

导入此包会触发各子模块的 DialogRegistry.register() 自动注册。
"""

from src.panel.dialogs.base_dialog import StepDialogBase
from src.panel.dialogs.dialog_registry import DialogRegistry
from src.panel.dialogs.key_picker import SyncedVar, make_key_picker

# 各类型对话框（导入即注册）
from src.panel.dialogs.click_image_dialog import ClickImageDialog  # noqa: F401
from src.panel.dialogs.click_pos_dialog import ClickPosDialog  # noqa: F401
from src.panel.dialogs.hold_key_dialog import HoldKeyDialog  # noqa: F401
from src.panel.dialogs.idle_behavior_dialog import IdleBehaviorDialog  # noqa: F401
from src.panel.dialogs.key_combo_dialog import KeyComboDialog  # noqa: F401
from src.panel.dialogs.mouse_drag_dialog import MouseDragDialog  # noqa: F401
from src.panel.dialogs.mouse_move_dialog import MouseMoveDialog  # noqa: F401
from src.panel.dialogs.multi_key_sequence_dialog import MultiKeySequenceDialog  # noqa: F401
from src.panel.dialogs.press_key_dialog import PressKeyDialog  # noqa: F401
from src.panel.dialogs.scroll_dialog import ScrollDialog  # noqa: F401
from src.panel.dialogs.start_timer_dialog import StartTimerDialog  # noqa: F401
from src.panel.dialogs.wait_dialog import WaitDialog  # noqa: F401
from src.panel.dialogs.wait_random_dialog import WaitRandomDialog  # noqa: F401

__all__ = [
    "StepDialogBase",
    "DialogRegistry",
    "SyncedVar",
    "make_key_picker",
    "ClickImageDialog",
    "ClickPosDialog",
    "HoldKeyDialog",
    "IdleBehaviorDialog",
    "KeyComboDialog",
    "MouseDragDialog",
    "MouseMoveDialog",
    "MultiKeySequenceDialog",
    "PressKeyDialog",
    "ScrollDialog",
    "StartTimerDialog",
    "WaitDialog",
    "WaitRandomDialog",
]


def open_step_dialog(
    parent, step, title: str, on_done,
) -> None:
    """工厂方法：根据 step.action_type 打开对应对话框。"""
    dlg_cls = DialogRegistry.get(step.action_type)
    if dlg_cls is None:
        raise ValueError(f"未注册的 ActionType: {step.action_type}")
    dlg_cls(parent, title=title, action=step, callback=on_done)
