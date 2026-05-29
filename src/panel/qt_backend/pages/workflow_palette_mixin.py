"""QtWorkflowPaletteMixin — PySide6 node palette panel.

替代 tkinter WorkflowPaletteMixin (~500 行)，使用 QTabWidget + QTreeWidget。
搜索过滤、折叠分组、帮助标签页。
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QTabWidget, QTreeWidget, QVBoxLayout, QWidget,
)

from src.core.flow import NodeType
from src.panel.canvas.theme import current_theme, node_fill_color
from src.panel.components.palette_data import (
    ACTION_PALETTE, FLOW_PALETTE, HELP_ACTION_ITEMS, HELP_FLOW_ITEMS,
    action_accent, flow_accent,
)
from src.panel.qt_backend.scale import qt_scale_manager
from src.panel.qt_backend.widgets import themed_palette_button, themed_section_header
from src.utils.i18n import t

class QtWorkflowPaletteMixin:
    """Node palette panel: tabs for nodes, monitors, help.

    Required self attributes:
        _palette_widget, _palette_mode, _palette_btn_widgets
    """

    def _build_node_palette(self):
        th = current_theme()
        sm = qt_scale_manager()

        self._palette_btn_widgets: list[QPushButton] = []
        self._palette_buttons: list[QWidget] = []

        self._palette_widget = QWidget()
        self._palette_widget.setMinimumWidth(sm.s(100))
        palette_layout = QVBoxLayout(self._palette_widget)
        palette_layout.setContentsMargins(0, 0, 0, 0)
        palette_layout.setSpacing(0)

        notebook = QTabWidget()
        palette_layout.addWidget(notebook)

        self._build_nodes_tab(notebook)
        self._build_monitor_tab(notebook)
        self._build_help_tab(notebook)

        self._palette_widget.setStyleSheet(f"""
            QWidget {{ background-color: {th.panel_bg}; }}
            QTabWidget::pane {{ border: 1px solid {th.border_default}; }}
            QTabBar::tab {{
                background-color: {th.bg_surface};
                color: {th.text_primary};
                padding: {sm.s(3)}px {sm.s(6)}px;
                border: 1px solid {th.border_default};
                font-size: {sm.s(10)}px;
                min-width: {sm.s(40)}px;
            }}
            QTabBar::tab:selected {{
                background-color: {th.panel_bg};
                border-bottom: 2px solid {th.accent_blue};
            }}
        """)

    # ── Nodes tab ──────────────────────────────────────────

    def _build_nodes_tab(self, notebook: QTabWidget):
        th = current_theme()

        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        search = QLineEdit()
        search.setPlaceholderText(t("workflow.palette.search_placeholder"))
        search.textChanged.connect(self._on_palette_search)
        layout.addWidget(search)
        self._palette_search = search

        # 按钮容器
        scroll_content = QWidget()
        self._palette_inner_layout = QVBoxLayout(scroll_content)
        self._palette_inner_layout.setContentsMargins(0, 0, 0, 0)
        self._palette_inner_layout.setSpacing(2)
        self._palette_inner_layout.addStretch()

        # 用 QScrollArea 包裹，使内容可滚动
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet(f"QScrollArea {{ background-color: {th.panel_bg}; }}")
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        self._build_action_section()
        self._build_flow_section()

        notebook.addTab(tab, t("workflow.tab.nodes"))

    def _build_action_section(self):
        th = current_theme()
        self._palette_inner_layout.insertWidget(
            self._palette_inner_layout.count() - 1,
            self._make_section_header(t("workflow.palette.section_action")),
        )
        for action_type, i18n_key in ACTION_PALETTE:
            accent_token = action_accent(action_type)
            color = getattr(th, accent_token, th.accent_blue)
            btn = self._create_palette_button(
                f"+ {t(i18n_key)}", color,
                lambda at=action_type: self._on_add_action_node(at),
            )
            self._palette_inner_layout.insertWidget(self._palette_inner_layout.count() - 1, btn)
            btn._palette_text = t(i18n_key)

    def _build_flow_section(self):
        th = current_theme()
        self._palette_inner_layout.insertWidget(
            self._palette_inner_layout.count() - 1,
            self._make_section_header(t("workflow.palette.section_flow")),
        )
        for node_type, i18n_key in FLOW_PALETTE:
            accent_token = flow_accent(node_type)
            color = getattr(th, accent_token, th.accent_blue)
            btn = self._create_palette_button(
                t(i18n_key), color,
                lambda nt=node_type: self._on_add_node(nt),
            )
            self._palette_inner_layout.insertWidget(self._palette_inner_layout.count() - 1, btn)
            btn._palette_text = t(i18n_key)

    # ── Monitor tab ──────────────────────────────────────────

    def _build_monitor_tab(self, notebook: QTabWidget):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 4, 4, 4)

        monitor_color = node_fill_color(NodeType.CONDITION)
        add_btn = self._create_palette_button(
            t("workflow.palette.add_monitor"), monitor_color,
            self._on_add_monitor,
        )
        layout.addWidget(add_btn)

        self._monitor_tree = QTreeWidget()
        self._monitor_tree.setHeaderLabels([
            "✓", t("common.name"), t("chain.mon.col.action"), t("chain.mon.col.interval"),
        ])
        self._monitor_tree.setColumnCount(4)
        self._monitor_tree.header().resizeSection(0, 25)
        self._monitor_tree.itemDoubleClicked.connect(lambda: self._on_edit_monitor())
        layout.addWidget(self._monitor_tree)

        btn_row = QHBoxLayout()
        for icon, handler in [
            ("✎", self._on_edit_monitor),
            ("✓", self._on_toggle_monitor),
            ("✕", self._on_delete_monitor),
        ]:
            b = QPushButton(icon)
            b.setFixedWidth(28)
            b.clicked.connect(handler)
            btn_row.addWidget(b)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        notebook.addTab(tab, t("workflow.tab.monitor"))

    # ── Help tab ──────────────────────────────────────────

    def _build_help_tab(self, notebook: QTabWidget):
        th = current_theme()
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(4, 4, 4, 4)
        tab_layout.setSpacing(0)

        scroll_content = QWidget()
        content_layout = QVBoxLayout(scroll_content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(4)

        self._build_help_card(content_layout, th,
                              title_key="workflow.help.action.title",
                              title_color=th.accent_blue,
                              items=HELP_ACTION_ITEMS)
        self._build_help_card(content_layout, th,
                              title_key="workflow.help.flow.title",
                              title_color=th.accent_orange,
                              items=HELP_FLOW_ITEMS)

        hint = QLabel(t("workflow.help.hint"))
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {th.text_muted};")
        content_layout.addWidget(hint)
        content_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet(f"QScrollArea {{ background-color: {th.panel_bg}; }}")
        scroll.setWidget(scroll_content)
        tab_layout.addWidget(scroll)

        notebook.addTab(tab, t("workflow.tab.help"))

    def _build_help_card(self, layout: QVBoxLayout, th, *,
                         title_key: str, title_color: str,
                         items: list[tuple[str, str]]) -> None:
        card = QWidget()
        card.setStyleSheet(
            f"QWidget {{ background-color: {th.card_bg}; "
            f"border: 1px solid {th.border_default}; border-radius: 4px; }}"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(6, 4, 6, 4)
        card_layout.setSpacing(1)

        title = QLabel(f"<b>{t(title_key)}</b>")
        title.setStyleSheet(f"color: {title_color}; border: none;")
        card_layout.addWidget(title)

        for name_key, desc_key in items:
            row = QLabel(f"<b>{t(name_key)}</b>: {t(desc_key)}")
            row.setWordWrap(True)
            row.setStyleSheet(f"color: {th.text_secondary}; border: none;")
            card_layout.addWidget(row)

        layout.addWidget(card)

    # ── Helpers ──────────────────────────────────────────

    def _make_section_header(self, title: str) -> QLabel:
        return themed_section_header(None, title)

    def _create_palette_button(self, text: str, color: str, command) -> QPushButton:
        """Create a themed palette button and register it for state/search."""
        btn = themed_palette_button(None, text, color, command)
        self._palette_btn_widgets.append(btn)
        self._palette_buttons.append(btn)
        return btn

    # ── Search ──────────────────────────────────────────

    def _on_palette_search(self, text: str):
        query = text.lower().strip()
        for btn in self._palette_buttons:
            if not hasattr(btn, "_palette_text"):
                continue
            visible = not query or query in btn._palette_text.lower()
            btn.setVisible(visible)
