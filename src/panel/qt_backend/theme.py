"""Qt 主题转换器 — 将 CanvasTheme tokens 转换为 QSS 样式表。"""

from __future__ import annotations

from src.panel.canvas.theme import CanvasTheme, current_theme
from src.panel.canvas.theme.style_mappings import derive_hover_bg as _derive_hover_bg
from src.panel.qt_backend.scale import qt_scale_manager


def theme_to_qss(t: CanvasTheme) -> str:
    """将 CanvasTheme 转换为全局 QSS 样式表。"""
    return f"""
    /* ── 全局 ── */
    QMainWindow, QWidget {{
        background-color: {t.page_bg};
        color: {t.text_primary};
        font-family: {t.font_family};
    }}

    /* ── 按钮 ── */
    QPushButton {{
        background-color: {t.btn_bg};
        color: {t.text_primary};
        border: 1px solid {t.btn_border};
        border-radius: 4px;
        padding: {t.pad_sm}px {t.pad_md}px;
        min-height: {t.button_height}px;
    }}
    QPushButton:hover {{
        background-color: {t.btn_bg_hover};
    }}
    QPushButton:pressed {{
        background-color: {t.accent_blue};
        color: {t.text_on_accent};
    }}
    QPushButton:disabled {{
        background-color: {t.btn_disabled_bg};
        color: {t.btn_disabled_fg};
    }}
    QPushButton[dnaBtnStyle="primary"] {{
        background-color: {t.accent_blue};
        color: {t.text_on_accent};
        border: 1px solid {t.accent_blue};
    }}
    QPushButton[dnaBtnStyle="primary"]:hover {{
        background-color: {_derive_hover_bg(t.accent_blue)};
    }}
    QPushButton[dnaBtnStyle="danger"] {{
        background-color: {t.danger_color};
        color: {t.text_on_accent};
        border: 1px solid {t.danger_color};
    }}
    QPushButton[dnaBtnStyle="danger"]:hover {{
        background-color: {_derive_hover_bg(t.danger_color)};
    }}
    QPushButton[dnaBtnStyle="ghost"] {{
        background-color: {t.page_bg};
        color: {t.text_primary};
        border: 1px solid transparent;
    }}
    QPushButton[dnaBtnStyle="ghost"]:hover {{
        background-color: {t.bg_surface_hover};
    }}
    /* 监控区紧凑按钮(action_chain）—— objectName 引用全局 QSS，随主题刷新 */
    QPushButton#dnaMonBtn {{
        background-color: {t.btn_bg};
        color: {t.text_primary};
        border: 1px solid {t.border_default};
        border-radius: 3px;
        padding: 2px {qt_scale_manager().s(6)}px;
        font-size: {qt_scale_manager().s(9)}px;
    }}
    QPushButton#dnaMonBtn:hover {{
        background-color: {t.btn_bg_hover};
        border-color: {t.accent_blue};
    }}
    /* 工具栏文字按钮（transparent 背景）—— objectName 引用全局 QSS，随主题刷新 */
    QPushButton#dnaToolBtn {{
        background: transparent;
        border: none;
        padding: 4px 8px;
        color: {t.text_primary};
    }}
    QPushButton#dnaToolBtn:hover {{
        background: {t.bg_surface_hover};
        border-radius: 3px;
    }}

    /* ── 标签 ── */
    QLabel {{
        background: transparent;
        color: {t.text_primary};
    }}
    /* 区域标题(themed_section_header)——用 dynamic property 引用全局 QSS，
       避免局部 stylesheet 隔离导致主题切换不跟随。 */
    QLabel#dnaSectionHeader {{
        background-color: {t.panel_header_bg};
        color: {t.text_primary};
        font-weight: bold;
        font-size: {qt_scale_manager().s(9)}px;
        border-bottom: 1px solid {t.border_default};
    }}
    QLabel#dnaTitle {{
        color: {t.text_primary};
        font-weight: bold;
        font-size: {qt_scale_manager().s(10)}px;
    }}
    /* 页面状态栏（base_page _build_qt_status_bar）—— objectName 全局 QSS，随主题刷新 */
    QWidget#dnaStatusBar {{
        background-color: {t.panel_bg};
        border-top: 1px solid {t.border_default};
    }}
    QLabel#dnaStatusLabel {{
        color: {t.text_muted};
        font-size: {qt_scale_manager().s(11)}px;
    }}

    /* ── 输入框 ── */
    QLineEdit {{
        background-color: {t.input_bg};
        color: {t.input_fg};
        border: 1px solid {t.border_default};
        border-radius: 4px;
        padding: {t.pad_xs}px {t.pad_sm}px;
        min-height: {t.button_height - 8}px;
        selection-background-color: {t.accent_blue};
        selection-color: {t.text_on_accent};
    }}
    QLineEdit:focus {{
        border-color: {t.accent_blue};
    }}
    QLineEdit:disabled {{
        background-color: {t.btn_disabled_bg};
        color: {t.btn_disabled_fg};
    }}

    /* ── 数值输入框 ── */
    QSpinBox {{
        background-color: {t.input_bg};
        color: {t.input_fg};
        border: 1px solid {t.border_default};
        border-radius: 4px;
        padding: {t.pad_xs}px {t.pad_sm}px;
        min-height: {t.button_height - 8}px;
    }}
    QSpinBox:focus {{
        border-color: {t.accent_blue};
    }}
    /* 浮点数值框(秒数/时长/速度) — 镜像 QSpinBox 保持视觉一致 */
    QDoubleSpinBox {{
        background-color: {t.input_bg};
        color: {t.input_fg};
        border: 1px solid {t.border_default};
        border-radius: 4px;
        padding: {t.pad_xs}px {t.pad_sm}px;
        min-height: {t.button_height - 8}px;
    }}
    QDoubleSpinBox:focus {{
        border-color: {t.accent_blue};
    }}

    /* ── 下拉框 ── */
    QComboBox {{
        background-color: {t.input_bg};
        color: {t.input_fg};
        border: 1px solid {t.border_default};
        border-radius: 4px;
        padding: {t.pad_xs}px {t.pad_sm}px;
        min-height: {t.button_height - 8}px;
        padding-right: {qt_scale_manager().s(24)}px;
    }}
    QComboBox:focus {{
        border-color: {t.accent_blue};
    }}
    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: center right;
        width: {qt_scale_manager().s(24)}px;
        border: none;
        border-left: 1px solid {t.border_default};
        background-color: {t.input_bg};
    }}
    QComboBox::drop-down:hover {{
        background-color: {t.bg_surface_hover};
    }}
    QComboBox::down-arrow {{
        width: 0;
        height: 0;
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-top: 6px solid {t.text_primary};
    }}
    QComboBox:disabled {{
        background-color: {t.btn_disabled_bg};
        color: {t.btn_disabled_fg};
    }}
    QComboBox:disabled::down-arrow {{
        border-top-color: {t.btn_disabled_fg};
    }}
    QComboBox QAbstractItemView {{
        background-color: {t.card_bg};
        color: {t.text_primary};
        selection-background-color: {t.accent_blue};
        selection-color: {t.text_on_accent};
        border: 1px solid {t.border_default};
        outline: none;
        padding: {t.pad_xs}px;
    }}
    QComboBox QAbstractItemView::item {{
        padding: {t.pad_xs}px {t.pad_sm}px;
        min-height: {t.button_height - 8}px;
    }}
    QComboBox QAbstractItemView::item:hover {{
        background-color: {t.bg_surface_hover};
    }}

    /* ── 复选框 ── */
    QCheckBox {{
        color: {t.text_primary};
        spacing: {t.pad_sm}px;
    }}
    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border: 2px solid {t.border_default};
        border-radius: 3px;
        background-color: {t.input_bg};
    }}
    QCheckBox::indicator:checked {{
        background-color: {t.accent_blue};
        border-color: {t.accent_blue};
    }}

    /* ── 单选按钮 ── */
    QRadioButton {{
        color: {t.text_primary};
        spacing: {t.pad_sm}px;
    }}
    QRadioButton::indicator {{
        width: 16px;
        height: 16px;
        border: 2px solid {t.border_default};
        border-radius: 8px;
        background-color: {t.input_bg};
    }}
    QRadioButton::indicator:checked {{
        background-color: {t.accent_blue};
        border-color: {t.accent_blue};
    }}

    /* ── 树形列表 ── */
    QTreeWidget {{
        background-color: {t.card_bg};
        color: {t.text_primary};
        border: 1px solid {t.border_default};
        border-radius: 4px;
        outline: none;
        alternate-background-color: {t.row_stripe_bg};
    }}
    QTreeWidget::item {{
        padding: {t.pad_xs}px;
        border-bottom: 1px solid transparent;
    }}
    QTreeWidget::item:hover {{
        background-color: {t.bg_surface_hover};
    }}
    QTreeWidget::item:selected {{
        background-color: {t.accent_blue_dim};
        color: {t.text_on_accent};
    }}
    QHeaderView::section {{
        background-color: {t.bg_surface};
        color: {t.text_primary};
        border: none;
        border-bottom: 1px solid {t.border_default};
        padding: {t.pad_sm}px;
        font-weight: bold;
    }}

    /* ── 分组框 ── */
    QGroupBox {{
        color: {t.text_primary};
        border: 1px solid {t.border_default};
        border-radius: 6px;
        margin-top: 12px;
        padding-top: 16px;
        font-weight: bold;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: {t.pad_md}px;
        padding: 0 {t.pad_xs}px;
    }}

    /* ── 样式化容器(_styled_panel 用 objectName 引用，避免局部 stylesheet 隔离）── */
    QFrame#dnaStyledPanel {{
        background-color: {t.panel_bg};
        border: 1px solid {t.border_default};
        border-radius: 4px;
    }}

    /* ── 分隔线 ── */
    QFrame[frameShape="4"] {{
        color: {t.separator_color};
        max-height: 1px;
    }}
    QFrame[frameShape="5"] {{
        color: {t.separator_color};
        max-width: 1px;
    }}

    /* ── 滚动区域 ── */
    QScrollArea {{
        background-color: transparent;
        border: none;
    }}

    /* ── 滚动条 ── */
    QScrollBar:vertical {{
        background-color: {t.bg_secondary};
        width: 10px;
        border: none;
    }}
    QScrollBar::handle:vertical {{
        background-color: {t.bg_surface};
        border-radius: 5px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background-color: {t.bg_surface_hover};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QScrollBar:horizontal {{
        background-color: {t.bg_secondary};
        height: 10px;
        border: none;
    }}
    QScrollBar::handle:horizontal {{
        background-color: {t.bg_surface};
        border-radius: 5px;
        min-width: 30px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background-color: {t.bg_surface_hover};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0;
    }}

    /* ── 选项卡 ── */
    QTabWidget::pane {{
        border: 1px solid {t.border_default};
        border-radius: 4px;
        background-color: {t.card_bg};
    }}
    QTabBar::tab {{
        background-color: {t.bg_surface};
        color: {t.text_secondary};
        padding: {t.pad_sm}px {t.pad_lg}px;
        border-top-left-radius: 4px;
        border-top-right-radius: 4px;
        margin-right: 2px;
    }}
    QTabBar::tab:selected {{
        background-color: {t.card_bg};
        color: {t.text_primary};
    }}
    QTabBar::tab:hover:!selected {{
        background-color: {t.bg_surface_hover};
    }}

    /* ── 分割器 ── */
    QSplitter::handle {{
        background-color: {t.border_default};
    }}
    QSplitter::handle:hover {{
        background-color: {t.accent_blue};
    }}

    /* ── 工具栏 ── */
    QToolBar {{
        background-color: {t.bg_surface};
        border: none;
        spacing: {t.pad_xs}px;
        padding: {t.pad_xs}px;
    }}
    QToolBar QToolButton {{
        background-color: transparent;
        color: {t.text_primary};
        border: 1px solid transparent;
        border-radius: 4px;
        padding: {t.pad_xs}px {t.pad_sm}px;
    }}
    QToolBar QToolButton:hover {{
        background-color: {t.bg_surface_hover};
        border-color: {t.border_default};
    }}
    QToolBar QToolButton:pressed {{
        background-color: {t.accent_blue};
        color: {t.text_on_accent};
    }}
    QToolBar QToolButton:checked {{
        background-color: {t.accent_blue_dim};
        color: {t.text_on_accent};
    }}
    QToolBar::separator {{
        width: 1px;
        height: 1px;
        background-color: {t.border_default};
        margin: {t.pad_xs}px {t.pad_sm}px;
    }}

    /* ── 状态栏 ── */
    QStatusBar {{
        background-color: {t.bg_surface};
        color: {t.text_muted};
        border-top: 1px solid {t.border_default};
        font-size: {t.font_small[1]}px;
    }}

    /* ── 工具提示 ── */
    QToolTip {{
        background-color: {t.card_bg};
        color: {t.text_primary};
        border: 1px solid {t.border_default};
        padding: {t.pad_xs}px {t.pad_sm}px;
    }}

    /* ── 菜单 ── */
    QMenu {{
        background-color: {t.card_bg};
        color: {t.text_primary};
        border: 1px solid {t.border_default};
        padding: {t.pad_xs}px;
    }}
    QMenu::item {{
        padding: {t.pad_xs}px {t.pad_lg}px;
    }}
    QMenu::item:selected {{
        background-color: {t.accent_blue_dim};
        color: {t.text_on_accent};
    }}
    QMenu::separator {{
        height: 1px;
        background-color: {t.border_default};
        margin: {t.pad_xs}px {t.pad_sm}px;
    }}

    /* ── 消息框 ── */
    QMessageBox {{
        background-color: {t.dialog_bg};
    }}
    QDialog {{
        background-color: {t.dialog_bg};
        color: {t.text_primary};
    }}

    /* ── 列表 ── */
    QListWidget {{
        background-color: {t.card_bg};
        color: {t.text_primary};
        border: 1px solid {t.border_default};
        border-radius: 4px;
        outline: none;
    }}
    QListWidget::item {{
        padding: {t.pad_xs}px {t.pad_sm}px;
    }}
    QListWidget::item:hover {{
        background-color: {t.bg_surface_hover};
    }}
    QListWidget::item:selected {{
        background-color: {t.accent_blue_dim};
        color: {t.text_on_accent};
    }}

    /* ── 进度条 ── */
    QProgressBar {{
        background-color: {t.bg_secondary};
        border: 1px solid {t.border_default};
        border-radius: 4px;
        text-align: center;
        color: {t.text_primary};
        min-height: 6px;
    }}
    QProgressBar::chunk {{
        background-color: {t.accent_blue};
        border-radius: 3px;
    }}

    /* ── 文本编辑区 ── */
    QPlainTextEdit, QTextEdit {{
        background-color: {t.card_bg};
        color: {t.text_primary};
        border: 1px solid {t.border_default};
        border-radius: 4px;
        font-family: {t.font_family};
        selection-background-color: {t.accent_blue_dim};
    }}

    /* ── 滑块 ── */
    QSlider::groove:horizontal {{
        background-color: {t.bg_secondary};
        height: 6px;
        border-radius: 3px;
    }}
    QSlider::handle:horizontal {{
        background-color: {t.accent_blue};
        width: 16px;
        height: 16px;
        margin: -5px 0;
        border-radius: 8px;
    }}
    QSlider::handle:horizontal:hover {{
        background-color: {t.accent_blue};
    }}
    """
