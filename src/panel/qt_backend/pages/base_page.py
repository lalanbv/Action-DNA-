"""QtBasePage — PySide6 页面基类。

与 tkinter BasePage (base_page.py) 对等。
所有 Qt 功能页面的抽象父类，提供定时器、事件订阅、主题切换。
"""

from __future__ import annotations

from enum import StrEnum
from typing import Callable

from PySide6.QtWidgets import QHBoxLayout, QInputDialog, QLabel, QMessageBox, QVBoxLayout, QWidget

from src.core.debug.ring_buffer_log import LogEventType
from src.panel.canvas.theme import ThemeCallbackMixin, current_theme, on_theme_change, remove_theme_change
from src.panel.pages.page_registry import PAGE_HOME
from src.panel.qt_backend.components.base import QtDNAWidget
from src.panel.qt_backend.scale import qt_scale_manager
from src.panel.qt_backend.timer import QtTimerScheduler
from src.panel.qt_backend.widgets import themed_button, themed_label
from src.utils.i18n import t


class SaveDiscardCancel(StrEnum):
    SAVE = "save"
    DISCARD = "discard"
    CANCEL = "cancel"


class QtBasePage(ThemeCallbackMixin, QWidget):
    """Qt 页面基类，子类需实现 build() 和 title()。"""

    def __init__(self, parent: QWidget, app, **kwargs) -> None:
        super().__init__(parent)
        th = current_theme()

        self.app = app
        self._init_kwargs = kwargs
        self._timer = QtTimerScheduler()
        self._timer_ids: list[str] = []
        self._subscriptions: list[tuple[str, Callable]] = []
        self._init_theme_guard(self.apply_theme, RuntimeError)

        self.setStyleSheet(f"background-color: {th.page_bg};")

    def build(self) -> None:
        raise NotImplementedError

    def title(self) -> str:
        return "Action<DNA>"

    def on_enter(self, **kwargs) -> None:
        """页面进入前台时调用。"""

    def on_leave(self) -> None:
        """页面离开前台时调用。"""

    def update_monitors(self, states: list) -> None:
        """推送监控状态更新。默认委托给 _monitor_widget（如果存在）。"""
        widget = getattr(self, "_monitor_widget", None)
        if widget is not None:
            widget.update_monitors(states)

    def _append_log(self, msg: str) -> None:
        ring = getattr(self, "_ring_log", None)
        if ring is not None:
            ring.append(message=msg, event_type=LogEventType.CUSTOM)
        if hasattr(self, "_log_text") and self._log_text:
            self._log_text.appendPlainText(msg)

    def _build_qt_status_bar(self, *, center_label: bool = False) -> QWidget:
        th = current_theme()
        sm = qt_scale_manager()

        bar = QWidget()
        bar.setFixedHeight(sm.s(24))
        bar.setStyleSheet(
            f"background-color: {th.panel_bg}; "
            f"border-top: 1px solid {th.border_default};"
        )

        h = QHBoxLayout(bar)
        h.setContentsMargins(sm.s(8), 0, sm.s(8), 0)

        status_style = f"color: {th.text_muted}; font-size: {sm.s(11)}px;"
        self._status_left = QLabel("")
        self._status_left.setStyleSheet(status_style)
        self._status_right = QLabel("")
        self._status_right.setStyleSheet(status_style)
        h.addWidget(self._status_left)

        if center_label:
            h.addStretch()
            self._status_center = QLabel("")
            self._status_center.setStyleSheet(status_style)
            h.addWidget(self._status_center)

        h.addStretch()
        h.addWidget(self._status_right)

        self._status_bar = bar
        return bar

    def _resolve_import_conflict(
        self,
        *,
        has_content: bool,
        is_dirty: bool,
        save_callback: Callable[[], None],
    ) -> bool:
        if not has_content:
            return True

        if is_dirty:
            result = self._ask_save_discard_cancel(
                t("record.export.unsaved_title"),
                t("record.export.unsaved_message"),
            )
            if result == SaveDiscardCancel.CANCEL:
                return False
            if result == SaveDiscardCancel.SAVE:
                save_callback()
        else:
            if not self._ask_yes_no(t("record.export.new_title"), t("record.export.new_message")):
                return False

        return True

    def _show_running_warning(self, message: str) -> None:
        self._append_log(message)
        self._show_info(t("common.info"), message)

    def _go_home(self) -> None:
        """返回首页；若执行器正在运行则提示。"""
        if self.app.executor and self.app.executor.is_running:
            self._show_running_warning(t("workflow.msg.running_in_background"))
        self.app.navigate_to(PAGE_HOME)

    def apply_theme(self) -> None:
        th = current_theme()
        self.setStyleSheet(f"background-color: {th.page_bg};")
        # Force Qt to re-evaluate global QSS for all children
        self.style().unpolish(self)
        self.style().polish(self)
        # Re-apply inline styles for specialized widgets (palette buttons, section headers)
        for child in self.findChildren(QWidget):
            prop = child.property("dnaBtnStyle")
            if prop and isinstance(prop, str) and prop:
                from src.panel.qt_backend.widgets import _build_button_qss
                from src.panel.canvas.theme.style_mappings import _BUTTON_STYLES
                cfg = _BUTTON_STYLES.get(prop)
                if cfg:
                    bg = getattr(th, cfg["bg_prop"])
                    fg = getattr(th, cfg["fg_prop"])
                    child.setStyleSheet(_build_button_qss(bg, fg))
            # Update section headers
            if getattr(child, "_dna_section_header", False):
                from src.utils.i18n import t
                sm = qt_scale_manager()
                text = child.text().strip()
                child.setStyleSheet(f"""
                    background-color: {th.panel_header_bg};
                    color: {th.text_primary};
                    font-weight: bold;
                    font-size: {sm.s(9)}px;
                    border-bottom: 1px solid {th.border_default};
                """)

    # ── 对话框工具 ──────────────────────────────────────────

    def _ask_string(self, title: str, prompt: str) -> tuple[str, bool]:
        return QInputDialog.getText(self, title, prompt)

    def _show_info(self, title: str, message: str) -> None:
        QMessageBox.information(self, title, message)

    def _show_error(self, title: str, message: str) -> None:
        QMessageBox.critical(self, title, message)

    def _show_warning(self, title: str, message: str) -> None:
        QMessageBox.warning(self, title, message)

    def _ask_yes_no(self, title: str, message: str) -> bool:
        return QMessageBox.question(self, title, message) == QMessageBox.StandardButton.Yes

    def _ask_int(self, title: str, label: str, *, value: int = 0, min_val: int = 0, max_val: int = 2147483647) -> tuple[int, bool]:
        return QInputDialog.getInt(self, title, label, value, min_val, max_val)

    def _ask_save_discard_cancel(self, title: str, message: str) -> SaveDiscardCancel:
        answer = QMessageBox.question(
            self, title, message,
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Save:
            return SaveDiscardCancel.SAVE
        if answer == QMessageBox.StandardButton.Discard:
            return SaveDiscardCancel.DISCARD
        return SaveDiscardCancel.CANCEL

    def destroy_page(self) -> None:
        """销毁页面，取消所有定时器和事件订阅。"""
        self._unregister_theme_callback()
        for child in self.findChildren(QtDNAWidget):
            child._unregister_theme_callback()
        for tid in self._timer_ids:
            self._timer.cancel(tid)
        for event, callback in self._subscriptions:
            bus = getattr(self.app, "event_bus", None)
            if bus is not None:
                bus.off(event, callback)

    def schedule(self, ms: int, callback) -> str:
        tid = self._timer.schedule(ms, callback)
        self._timer_ids.append(tid)
        return tid

    def subscribe(self, event: str, callback: Callable) -> None:
        """订阅事件，页面销毁时自动取消。"""
        def _safe_callback(**kwargs):
            if self._timer.is_alive():
                self._timer.schedule_idle(
                    lambda: callback(**kwargs) if self._timer.is_alive() else None,
                )

        self.app.event_bus.on(event, _safe_callback)
        self._subscriptions.append((event, _safe_callback))

    def _build_toolbar_base(
        self,
        layout: QVBoxLayout,
        title_key: str,
        *,
        show_back: bool = True,
    ) -> QHBoxLayout:
        """构建标准工具栏（返回按钮 + 标题 + stretch），返回 QHBoxLayout 供子类追加按钮。"""
        toolbar = QHBoxLayout()
        if show_back:
            back_btn = themed_button(
                self, text=t("common.back"), style="secondary",
                command=lambda: self.app.navigate_to(PAGE_HOME),
            )
            toolbar.addWidget(back_btn)
        title_lbl = themed_label(self, text=t(title_key), style="section")
        toolbar.addWidget(title_lbl)
        toolbar.addStretch()
        layout.addLayout(toolbar)
        return toolbar
