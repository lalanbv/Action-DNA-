"""QtWorkflowPaletteMixin — PySide6 node palette panel.

替代 tkinter WorkflowPaletteMixin (~500 行)，使用 QTabWidget + QTreeWidget。
搜索过滤、折叠分组、帮助标签页。
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTabWidget, QTreeWidget, QVBoxLayout, QWidget,
)

from src.core.flow import NodeType
from src.panel.canvas.theme import current_theme, node_fill_color
from src.panel.components.palette_data import ACTION_PALETTE, FLOW_PALETTE
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
        self._palette_widget.setFixedWidth(sm.s(th.panel_width_left))
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
                padding: {sm.s(4)}px {sm.s(8)}px;
                border: 1px solid {th.border_default};
            }}
            QTabBar::tab:selected {{
                background-color: {th.panel_bg};
                border-bottom: 2px solid {th.accent_blue};
            }}
        """)

    # ── Nodes tab ──────────────────────────────────────────

    def _build_nodes_tab(self, notebook: QTabWidget):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 4, 4, 4)

        search = QLineEdit()
        search.setPlaceholderText(t("workflow.palette.search_placeholder"))
        search.textChanged.connect(self._on_palette_search)
        layout.addWidget(search)
        self._palette_search = search

        scroll_area = QWidget()
        self._palette_inner_layout = QVBoxLayout(scroll_area)
        self._palette_inner_layout.setContentsMargins(0, 0, 0, 0)
        self._palette_inner_layout.setSpacing(2)
        self._palette_inner_layout.addStretch()

        layout.addWidget(scroll_area)

        self._build_action_section()
        self._build_flow_section()

        notebook.addTab(tab, t("workflow.tab.nodes"))

    def _build_action_section(self):
        self._palette_inner_layout.insertWidget(
            self._palette_inner_layout.count() - 1,
            self._make_section_header(t("workflow.palette.section_action")),
        )
        for action_type, i18n_key in ACTION_PALETTE:
            color = node_fill_color("ACTION")
            btn = self._create_palette_button(
                f"+ {t(i18n_key)}", color,
                lambda at=action_type: self._on_add_action_node(at),
            )
            self._palette_inner_layout.insertWidget(self._palette_inner_layout.count() - 1, btn)
            btn._palette_text = t(i18n_key)

    def _build_flow_section(self):
        self._palette_inner_layout.insertWidget(
            self._palette_inner_layout.count() - 1,
            self._make_section_header(t("workflow.palette.section_flow")),
        )
        for node_type, i18n_key in FLOW_PALETTE:
            color = node_fill_color(node_type)
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
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 4, 4, 4)

        help_action_items = [
            ("action_type.click_image", "workflow.help.click_image"),
            ("action_type.wait", "workflow.help.wait"),
            ("action_type.wait_random", "workflow.help.wait_random"),
            ("action_type.press_key", "workflow.help.press_key"),
            ("action_type.click_pos", "workflow.help.click_pos"),
            ("action_type.scroll", "workflow.help.mouse_scroll"),
            ("action_type.hold_key", "workflow.help.hold_key"),
            ("action_type.mouse_move", "workflow.help.mouse_move"),
            ("action_type.mouse_drag", "workflow.help.mouse_drag"),
            ("action_type.key_combo", "workflow.help.key_combo"),
            ("action_type.multi_key", "workflow.help.multi_key_sequence"),
            ("action_type.idle", "workflow.help.idle_behavior"),
            ("action_type.start_timer", "workflow.help.start_timer"),
        ]
        layout.addWidget(QLabel(f"<b>{t('workflow.help.action.title')}</b>"))
        for name_key, desc_key in help_action_items:
            row = QLabel(f"<b>{t(name_key)}</b>: {t(desc_key)}")
            row.setWordWrap(True)
            layout.addWidget(row)

        layout.addSpacing(8)

        help_flow_items = [
            ("workflow.node.start", "workflow.help.start"),
            ("workflow.node.end", "workflow.help.end"),
            ("workflow.node.condition", "workflow.help.condition"),
            ("workflow.node.merge", "workflow.help.merge"),
            ("workflow.node.loop", "workflow.help.loop"),
        ]
        layout.addWidget(QLabel(f"<b>{t('workflow.help.flow.title')}</b>"))
        for name_key, desc_key in help_flow_items:
            row = QLabel(f"<b>{t(name_key)}</b>: {t(desc_key)}")
            row.setWordWrap(True)
            layout.addWidget(row)

        layout.addSpacing(8)
        hint = QLabel(t("workflow.help.hint"))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch()

        notebook.addTab(tab, t("workflow.tab.help"))

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
