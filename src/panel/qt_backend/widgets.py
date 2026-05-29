"""QtThemedWidgets — PySide6 主题控件工厂。

与 tkinter ThemedWidgets (widgets.py) 对等。
所有页面和对话框通过此模块创建控件，确保视觉一致性和主题切换支持。
Qt 后端利用 QSS 全局样式传播，无需手动递归应用主题。
"""

from __future__ import annotations

from typing import Any, Callable, Literal

from PySide6.QtGui import QFont

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QRadioButton, QSpinBox, QVBoxLayout, QWidget,
)
from PySide6.QtCore import Qt, QSize

from src.panel.canvas.theme import CanvasTheme, current_theme
from src.panel.canvas.theme.style_mappings import (
    ButtonStyle, LabelStyle, _STYLE_FONTS, _BUTTON_STYLES,
    resolve_font as _resolve_font, derive_hover_bg as _derive_hover_bg,
)
from src.panel.qt_backend.scale import qt_scale_manager

_font_cache: dict[tuple, QFont] = {}


# ── 工厂函数 ──


def themed_frame(parent: QWidget, **kw: Any) -> QWidget:
    frame = QWidget(parent)
    obj_name = kw.pop("objectName", "")
    if obj_name:
        frame.setObjectName(obj_name)
    return frame


def themed_label(
    parent: QWidget, text: str = "", style: LabelStyle = "body", **kw: Any
) -> QLabel:
    th = current_theme()
    font = _resolve_font(th, style)
    label = QLabel(text, parent)
    label.setFont(_qt_font(font))
    obj_name = kw.pop("objectName", "")
    if obj_name:
        label.setObjectName(obj_name)
    return label


def themed_button(
    parent: QWidget,
    text: str = "",
    command: Callable[[], None] | None = None,
    style: ButtonStyle = "secondary",
    **kw: Any,
) -> QPushButton:
    th = current_theme()
    btn = QPushButton(text, parent)
    btn.setFont(_qt_font(th.font_body))

    if style != "secondary":
        btn.setProperty("dnaBtnStyle", style)
        btn_cfg = _BUTTON_STYLES[style]
        bg = getattr(th, btn_cfg["bg_prop"])
        fg = getattr(th, btn_cfg["fg_prop"])
        btn.setStyleSheet(_build_button_qss(bg, fg))

    if command:
        btn.clicked.connect(lambda _checked: command())

    obj_name = kw.pop("objectName", "")
    if obj_name:
        btn.setObjectName(obj_name)
    return btn


def themed_entry(parent: QWidget, **kw: Any) -> QLineEdit:
    th = current_theme()
    entry = QLineEdit(parent)
    entry.setFont(_qt_font(th.font_body))
    if "placeholder" in kw:
        entry.setPlaceholderText(kw.pop("placeholder"))
    if "text" in kw:
        entry.setText(kw.pop("text"))
    if "max_length" in kw:
        entry.setMaxLength(kw.pop("max_length"))
    obj_name = kw.pop("objectName", "")
    if obj_name:
        entry.setObjectName(obj_name)
    return entry


def themed_spinbox(parent: QWidget, **kw: Any) -> QSpinBox:
    th = current_theme()
    spin = QSpinBox(parent)
    spin.setFont(_qt_font(th.font_body))
    if "minimum" in kw:
        spin.setMinimum(kw.pop("minimum"))
    if "maximum" in kw:
        spin.setMaximum(kw.pop("maximum"))
    if "value" in kw:
        spin.setValue(kw.pop("value"))
    if "prefix" in kw:
        spin.setPrefix(kw.pop("prefix"))
    if "suffix" in kw:
        spin.setSuffix(kw.pop("suffix"))
    if "single_step" in kw:
        spin.setSingleStep(kw.pop("single_step"))
    obj_name = kw.pop("objectName", "")
    if obj_name:
        spin.setObjectName(obj_name)
    return spin


def themed_checkbutton(
    parent: QWidget, text: str = "", **kw: Any
) -> QCheckBox:
    cb = QCheckBox(text, parent)
    th = current_theme()
    cb.setFont(_qt_font(th.font_body))
    if "checked" in kw:
        cb.setChecked(kw.pop("checked"))
    if "command" in kw:
        cmd = kw.pop("command")
        cb.stateChanged.connect(lambda: cmd())
    obj_name = kw.pop("objectName", "")
    if obj_name:
        cb.setObjectName(obj_name)
    return cb


def themed_radiobutton(
    parent: QWidget, text: str = "", **kw: Any
) -> QRadioButton:
    rb = QRadioButton(text, parent)
    th = current_theme()
    rb.setFont(_qt_font(th.font_body))
    if "checked" in kw:
        rb.setChecked(kw.pop("checked"))
    obj_name = kw.pop("objectName", "")
    if obj_name:
        rb.setObjectName(obj_name)
    return rb


def themed_combobox(parent: QWidget, **kw: Any) -> QComboBox:
    th = current_theme()
    combo = QComboBox(parent)
    combo.setFont(_qt_font(th.font_body))
    if "items" in kw:
        combo.addItems(kw.pop("items"))
    if "editable" in kw:
        combo.setEditable(kw.pop("editable"))
    obj_name = kw.pop("objectName", "")
    if obj_name:
        combo.setObjectName(obj_name)
    return combo


def themed_labelframe(
    parent: QWidget, text: str = "", **kw: Any
) -> QGroupBox:
    gb = QGroupBox(text, parent)
    th = current_theme()
    gb.setFont(_qt_font(th.font_section_title))
    obj_name = kw.pop("objectName", "")
    if obj_name:
        gb.setObjectName(obj_name)
    return gb


def themed_separator(
    parent: QWidget, orient: Literal["horizontal", "vertical"] = "horizontal", **kw: Any
) -> QFrame:
    line = QFrame(parent)
    if orient == "vertical":
        line.setFrameShape(QFrame.VLine)
    else:
        line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    return line


def themed_treeview(parent: QWidget, **kw: Any) -> Any:
    from PySide6.QtWidgets import QTreeWidget
    th = current_theme()
    tree = QTreeWidget(parent)
    tree.setFont(_qt_font(th.font_body))
    tree.setAlternatingRowColors(True)
    if "columns" in kw:
        headers = kw.pop("columns")
        tree.setHeaderLabels(headers)
    if "column_widths" in kw:
        widths = kw.pop("column_widths")
        for i, w in enumerate(widths):
            tree.setColumnWidth(i, w)
    obj_name = kw.pop("objectName", "")
    if obj_name:
        tree.setObjectName(obj_name)
    return tree


# ── 辅助函数 ──


def _qt_font(font_tuple: tuple) -> QFont:
    if isinstance(font_tuple, QFont):
        return font_tuple
    if not isinstance(font_tuple, (tuple, list)) or len(font_tuple) < 2:
        return QFont("sans-serif", 10)
    key = tuple(font_tuple)
    cached = _font_cache.get(key)
    if cached is not None:
        return cached
    family, size = font_tuple[0], font_tuple[1]
    weight = QFont.Normal
    if len(font_tuple) > 2 and font_tuple[2] == "bold":
        weight = QFont.Bold
    qf = QFont(family, int(size), weight)
    if len(font_tuple) > 2 and font_tuple[2] == "italic":
        qf.setItalic(True)
    _font_cache[key] = qf
    return qf


def _build_button_qss(bg: str, fg: str) -> str:
    """Build QPushButton QSS for the given bg/fg colors."""
    th = current_theme()
    sm = qt_scale_manager()
    return f"""
        QPushButton {{
            background-color: {bg};
            color: {fg};
            border: 1px solid {th.btn_border};
            border-radius: 4px;
            padding: {sm.s(th.pad_xs)}px {sm.s(th.pad_md)}px;
            min-height: {th.button_height - sm.s(th.pad_xs) * 2}px;
        }}
        QPushButton:hover {{
            background-color: {_derive_hover_bg(bg)};
        }}
        QPushButton:pressed {{
            background-color: {th.accent_blue};
            color: {th.text_on_accent};
        }}
        QPushButton:disabled {{
            background-color: {th.btn_disabled_bg};
            color: {th.btn_disabled_fg};
        }}
    """


def themed_section_header(parent: QWidget, text: str) -> QLabel:
    """创建调色板区域标题（带背景色 + 粗体 + 下边框）。"""
    th = current_theme()
    sm = qt_scale_manager()
    label = QLabel(f"  {text}", parent)
    label.setFixedHeight(sm.s(22))
    label.setProperty("_dna_section_header", True)
    label.setStyleSheet(f"""
        background-color: {th.panel_header_bg};
        color: {th.text_primary};
        font-weight: bold;
        font-size: {sm.s(9)}px;
        border-bottom: 1px solid {th.border_default};
    """)
    return label


def themed_palette_button(
    parent: QWidget, text: str, accent_color: str, command: Callable[[], None],
) -> QPushButton:
    """创建调色板步骤按钮（左侧带颜色竖条）。"""
    th = current_theme()
    sm = qt_scale_manager()
    btn = QPushButton(text, parent)
    btn.setFixedHeight(sm.s(24))
    btn.setStyleSheet(f"""
        QPushButton {{
            background-color: {th.btn_bg};
            color: {th.text_primary};
            border: 1px solid {th.border_default};
            border-left: 3px solid {accent_color};
            border-radius: 2px;
            padding: 2px {sm.s(6)}px;
            text-align: left;
            font-size: {sm.s(10)}px;
        }}
        QPushButton:hover {{
            background-color: {th.btn_bg_hover};
            border-color: {th.accent_blue};
        }}
    """)
    btn.clicked.connect(lambda _checked: command())
    return btn


def style_button(btn: QPushButton, style: ButtonStyle = "secondary") -> None:
    """按预定义样式名更新按钮样式。"""
    th = current_theme()
    if style != "secondary":
        btn.setProperty("dnaBtnStyle", style)
        btn_cfg = _BUTTON_STYLES[style]
        bg = getattr(th, btn_cfg["bg_prop"])
        fg = getattr(th, btn_cfg["fg_prop"])
        btn.setStyleSheet(_build_button_qss(bg, fg))
    else:
        btn.setProperty("dnaBtnStyle", "")
        btn.setStyleSheet("")
