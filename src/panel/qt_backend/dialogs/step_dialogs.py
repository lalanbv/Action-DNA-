"""QtStepDialogs — 对话框注册表 + re-export 垫片。

对话框实现已拆分到独立文件（与 tkinter dialogs/ 结构对齐）。
本文件保留 _QT_DIALOG_MAP 注册表和 get_qt_dialog_class() API，
确保 dialog_registry.py 的导入路径不变。
"""

from __future__ import annotations

from src.core.action import ActionType

from src.panel.qt_backend.dialogs.base_dialog import QtStepDialogBase
from src.panel.qt_backend.dialogs.wait_dialog import QtWaitDialog
from src.panel.qt_backend.dialogs.wait_random_dialog import QtWaitRandomDialog
from src.panel.qt_backend.dialogs.press_key_dialog import QtPressKeyDialog
from src.panel.qt_backend.dialogs.hold_key_dialog import QtHoldKeyDialog
from src.panel.qt_backend.dialogs.click_pos_dialog import QtClickPosDialog
from src.panel.qt_backend.dialogs.click_image_dialog import QtClickImageDialog
from src.panel.qt_backend.dialogs.scroll_dialog import QtScrollDialog
from src.panel.qt_backend.dialogs.key_combo_dialog import QtKeyComboDialog
from src.panel.qt_backend.dialogs.multi_key_sequence_dialog import QtMultiKeySequenceDialog
from src.panel.qt_backend.dialogs.mouse_drag_dialog import QtMouseDragDialog
from src.panel.qt_backend.dialogs.mouse_move_dialog import QtMouseMoveDialog
from src.panel.qt_backend.dialogs.idle_behavior_dialog import QtIdleBehaviorDialog
from src.panel.qt_backend.dialogs.start_timer_dialog import QtStartTimerDialog
from src.utils.i18n import t

# ── Qt 对话框注册表 ──

_QT_DIALOG_MAP: dict[ActionType, type[QtStepDialogBase]] = {
    ActionType.WAIT: QtWaitDialog,
    ActionType.WAIT_RANDOM: QtWaitRandomDialog,
    ActionType.PRESS_KEY: QtPressKeyDialog,
    ActionType.HOLD_KEY: QtHoldKeyDialog,
    ActionType.CLICK_POS: QtClickPosDialog,
    ActionType.CLICK_IMAGE: QtClickImageDialog,
    ActionType.MOUSE_SCROLL: QtScrollDialog,
    ActionType.KEY_COMBO: QtKeyComboDialog,
    ActionType.MULTI_KEY_SEQUENCE: QtMultiKeySequenceDialog,
    ActionType.MOUSE_DRAG: QtMouseDragDialog,
    ActionType.MOUSE_MOVE: QtMouseMoveDialog,
    ActionType.IDLE_BEHAVIOR: QtIdleBehaviorDialog,
    ActionType.START_TIMER: QtStartTimerDialog,
}


def get_qt_dialog_class(action_type: ActionType) -> type[QtStepDialogBase] | None:
    """获取 Qt 后端对话框类。"""
    return _QT_DIALOG_MAP.get(action_type)


def open_step_dialog(parent, step, title: str, on_done) -> None:
    """根据 step.action_type 打开对应的 Qt 对话框。"""
    dlg_cls = _QT_DIALOG_MAP.get(step.action_type)
    if dlg_cls is None:
        raise ValueError(t("panel.exc.unregistered_action_type", action_type=step.action_type))
    dlg = dlg_cls(parent, title=title, action=step, callback=on_done)
    dlg.open()
