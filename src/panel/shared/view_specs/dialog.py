"""步骤对话框契约（Phase 2，规格 §5.1）。

两后端步骤对话框基类对齐：均接受 ``action``（编辑目标，None 表新建）+
``callback``（完成回调），并具备主题回调能力（apply_theme / ThemeCallbackMixin）。

- tk：``src.panel.dialogs.base_dialog.StepDialogBase``（``tk.Toplevel`` +
  ``ThemeCallbackMixin``，``apply_to_toplevel`` 配色）。
- Qt：``src.panel.qt_backend.dialogs.base_dialog.QtStepDialogBase``（``QDialog`` +
  ``apply_theme`` 重设 QSS）。

校验：``tests/unit/panel/test_view_specs.py`` 断言两后端基类 ``__init__`` 接受
``action`` / ``callback`` 关键字参数。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DialogSpec:
    """步骤对话框契约 —— 两后端基类 __init__ 必须支持。"""

    title: str = ""
    #: 编辑目标；None 表示新建。
    action: object | None = None
    #: 完成（OK）回调，接收编辑后的 BaseStep。
    callback: object | None = None


#: 两后端 StepDialogBase / QtStepDialogBase ``__init__`` 必须接受的关键字参数。
DIALOG_PROPS: tuple[str, ...] = ("action", "callback")
