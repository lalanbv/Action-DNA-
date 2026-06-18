"""QtStepDialogBase — PySide6 步骤配置对话框抽象基类。

与 tkinter StepDialogBase (base_dialog.py) 对等。
子类实现 _build_content()、_get_result()，可选覆盖
_validate_inputs() 和 _populate_fields()。
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Callable

from PySide6.QtWidgets import (
    QAbstractSpinBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QLabel, QLayout, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)
from PySide6.QtCore import Qt

from src.core.step_types import BaseStep
from src.panel.canvas.theme import current_theme
from src.panel.canvas.theme.theme_manager import on_theme_change, remove_theme_change
from src.panel.qt_backend.scale import qt_scale_manager
from src.panel.qt_backend.widgets import (
    reapply_button_qss, themed_button, themed_checkbutton, themed_doublespinbox,
    themed_entry, themed_frame, themed_label, themed_spinbox,
)
from src.utils.float_utils import safe_float, safe_int
from src.utils.i18n import t


class QtStepDialogBase(QDialog):
    """步骤配置对话框抽象基类。

    子类实现 _build_content()、_get_result()，可选覆盖
    _validate_inputs() 和 _populate_fields()。

    注意：不继承 ABC 以避免与 Shiboken 元类冲突。
    抽象方法通过 __init_subclass__ 在开发时检查。
    """

    def __init__(
        self,
        parent: QWidget,
        title: str,
        action: BaseStep | None = None,
        callback: Callable[[BaseStep], None] | None = None,
        width: int = 520,
        height: int = 520,
    ) -> None:
        super().__init__(parent)
        th = current_theme()
        sm = qt_scale_manager()

        self.setWindowTitle(title)
        self._action = action
        self._callback = callback
        self._vars: dict[str, object] = {}
        self._result: BaseStep | None = None

        self.setMinimumSize(sm.s(400), sm.s(350))
        self.resize(sm.s(width), sm.s(height))
        self.setWindowFlags(self.windowFlags() | Qt.Dialog)
        self.setModal(True)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        self._content_frame = QWidget()
        self._form_layout = QFormLayout(self._content_frame)
        self._form_layout.setContentsMargins(
            sm.s(th.pad_md), sm.s(th.pad_md),
            sm.s(th.pad_md), sm.s(th.pad_md),
        )
        self._form_layout.setSpacing(sm.s(8))
        scroll.setWidget(self._content_frame)
        main_layout.addWidget(scroll, 1)

        self._build_content()

        btn_frame = themed_frame(self)
        btn_layout = QHBoxLayout(btn_frame)
        btn_layout.setContentsMargins(sm.s(th.pad_md), 0, sm.s(th.pad_md), sm.s(th.pad_sm))
        btn_layout.addStretch()
        cancel_btn = themed_button(
            btn_frame, text=t("common.cancel"),
            command=self.reject, style="secondary",
        )
        btn_layout.addWidget(cancel_btn)
        ok_btn = themed_button(
            btn_frame, text=t("common.ok"),
            command=self._on_confirm, style="primary",
        )
        btn_layout.addWidget(ok_btn)
        main_layout.addWidget(btn_frame)

        if action:
            self._populate_fields(action)

        self._center_on_parent(parent)

        # B4：注册主题回调 —— 打开期间切换深/浅色时重应用主题。
        self._theme_cb_id: int | None = on_theme_change(self.apply_theme)

    def apply_theme(self) -> None:
        """主题切换回调：按当前主题重设对话框样式 + 重建带 dnaBtnStyle 的按钮 QSS。

        entry/spinbox/checkbox 等无本地 stylesheet 的控件走主窗口全局 QSS；
        primary/danger 等按钮有本地 stylesheet（绑死创建时主题色），需逐个重建。
        """
        th = current_theme()
        # 对话框背景（遮蔽全局 QSS 的 dialog 背景，显式重设）
        self.setStyleSheet(f"QDialog {{ background-color: {th.dialog_bg}; }}")
        for btn in self.findChildren(QPushButton):
            reapply_button_qss(btn)

    def done(self, result: int) -> None:
        """关闭对话框时注销主题回调（B4：防泄漏 + 防销毁后回调报错）。"""
        if getattr(self, "_theme_cb_id", None) is not None:
            remove_theme_change(self._theme_cb_id)
            self._theme_cb_id = None
        super().done(result)

    @abstractmethod
    def _build_content(self) -> None:
        """构建对话框内容区域。"""

    @abstractmethod
    def _get_result(self) -> BaseStep:
        """从字段提取配置结果。"""

    def _validate_inputs(self) -> list[str]:
        """验证输入，返回错误列表。"""
        return []

    def _populate_fields(self, action: BaseStep) -> None:
        """用现有配置填充字段（编辑模式）。"""

    def _on_confirm(self) -> None:
        errors = self._validate_inputs()
        if errors:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, t("dialog.validation.title"),
                "\n".join(f"  - {e}" for e in errors),
            )
            return
        result = self._get_result()
        if self._callback:
            try:
                self._callback(result)
            except RuntimeError as exc:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.critical(
                    self, t("dialog.validation.title"), str(exc),
                )
                return
        self._result = result
        self.accept()

    def get_result(self) -> BaseStep | None:
        """返回对话框结果（仅在 accept 后有效）。"""
        return self._result

    def _center_on_parent(self, parent: QWidget) -> None:
        if parent is None:
            return
        geo = parent.geometry()
        self.move(
            geo.x() + (geo.width() - self.width()) // 2,
            geo.y() + (geo.height() - self.height()) // 2,
        )

    def _add_row(
        self, label: str, widget: QWidget, row: int | None = None,
    ) -> None:
        """添加带标签的表单行。"""
        lbl = themed_label(self._content_frame, text=label)
        if row is not None:
            self._form_layout.insertRow(row, lbl, widget)
        else:
            self._form_layout.addRow(lbl, widget)

    def _add_labeled_entry(
        self, label: str, default: str = "", row: int | None = None,
    ) -> QLineEdit:
        """添加带标签的输入框，返回 QLineEdit。"""
        entry = themed_entry(self._content_frame, text=default)
        self._add_row(label, entry, row)
        return entry

    def _add_labeled_spinbox(
        self,
        label: str,
        default: float = 0.0,
        min_val: float = 0.0,
        max_val: float = 9999.0,
        increment: float = 0.1,
        row: int | None = None,
    ) -> QAbstractSpinBox:
        """添加带标签的数值框。

        小数步进(increment < 1, 如秒数/时长/速度)→ QDoubleSpinBox, 使用真实
        min/max/value/increment(对齐 tkinter tk.Spinbox 浮点行为)。
        整数步进(increment >= 1)→ QSpinBox。
        两种控件均提供 .value()/.setValue(), _get_float/_get_int 无需区分。
        """
        if increment < 1:
            spin = themed_doublespinbox(
                self._content_frame,
                minimum=min_val, maximum=max_val,
                value=default, single_step=increment, decimals=2,
            )
        else:
            spin = themed_spinbox(
                self._content_frame,
                minimum=int(min_val), maximum=int(max_val),
                value=int(default), single_step=int(increment),
            )
        self._add_row(label, spin, row)
        return spin

    def _add_common_fields(self, step: BaseStep) -> None:
        """添加注释和启用步骤通用字段。"""
        comment_entry = themed_entry(
            self._content_frame, text=step.comment,
        )
        self._vars["comment_entry"] = comment_entry
        self._add_row(t("dialog.label.comment"), comment_entry)

        cb = themed_checkbutton(
            self._content_frame, text=t("dialog.label.enable_step"),
            checked=step.enabled,
        )
        self._vars["enabled_cb"] = cb
        self._form_layout.addRow(cb)

    def _apply_common(self, step: BaseStep) -> None:
        comment_entry = self._vars.get("comment_entry")
        if comment_entry is not None:
            step.comment = comment_entry.text()
        enabled_cb = self._vars.get("enabled_cb")
        if enabled_cb is not None:
            step.enabled = enabled_cb.isChecked()

    def _get_float(
        self,
        name: str,
        *,
        min_val: float | None = None,
        max_val: float | None = None,
        default: float = 0.0,
        decimal_places: int | None = None,
    ) -> float:
        """从 self._vars[name] 安全读取浮点值。"""
        spin = self._vars.get(name)
        if spin is None:
            return default
        return safe_float(
            spin.value(),
            min_val=min_val, max_val=max_val,
            default=default, decimal_places=decimal_places,
        )

    def _get_int(
        self,
        name: str,
        *,
        min_val: int | None = None,
        max_val: int | None = None,
        default: int = 0,
    ) -> int:
        """从 self._vars[name] 安全读取整数值。"""
        spin = self._vars.get(name)
        if spin is None:
            return default
        return safe_int(
            spin.value(),
            min_val=min_val, max_val=max_val, default=default,
        )
