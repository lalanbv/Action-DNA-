"""QtScrollableFrame — PySide6 可滚动容器。

替代 tkinter ScrollableFrame，直接使用 QScrollArea。
Qt 内置滚动条和视口管理，无需手动实现。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

from src.panel.canvas.theme import CanvasTheme, current_theme


class QtScrollableFrame(QScrollArea):
    """可滚动容器，内部 content_widget 为实际内容容器。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self._content = QWidget()
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self.setWidget(self._content)

    @property
    def content_widget(self) -> QWidget:
        """返回内部内容容器，用于添加子控件。"""
        return self._content

    @property
    def content_layout(self) -> QVBoxLayout:
        """返回内部布局，用于添加子控件。"""
        return self._layout

    def apply_theme(self, theme: CanvasTheme | None = None) -> None:
        if theme is None:
            theme = current_theme()
        self.setStyleSheet(f"""
            QScrollArea {{
                background-color: transparent;
                border: none;
            }}
        """)
