"""QtWorkflowPropertiesMixin — PySide6 right-side properties panel.

替代 tkinter WorkflowPropertiesMixin，填充节点属性表单。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QDoubleSpinBox, QFrame, QHBoxLayout, QLabel,
    QPushButton, QVBoxLayout, QWidget,
)

from src.core.flow import FlowEdge, FlowNode, NodeType
from src.core.error.error_config import ErrorConfig, ErrorStrategy, RetryPolicy
from src.panel.canvas.theme import current_theme, node_fill_color
from src.panel.canvas.node_renderer import _type_label as node_type_label
from src.panel.models.enums import EdgeLabel
from src.panel.qt_backend.scale import qt_scale_manager
from src.panel.qt_backend.widgets import (
    themed_button, themed_checkbutton, themed_dropdown, themed_entry,
    themed_spinbox,
)
from src.utils.i18n import t

if TYPE_CHECKING:
    pass


class QtWorkflowPropertiesMixin:
    """Properties panel filling for selected nodes.

    Required self attributes:
        _model, _canvas, _controller, _selected_node_id,
        _props_inner, _props_inner_layout
    """

    @staticmethod
    def _clear_layout(layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if sub := item.layout():
                QtWorkflowPropertiesMixin._clear_layout(sub)
            elif w := item.widget():
                w.deleteLater()

    def _clear_props(self) -> None:
        if not hasattr(self, "_props_inner_layout"):
            return
        self._clear_layout(self._props_inner_layout)
        self._props_inner_layout.addStretch()

    def _show_node_properties(self, node_id: str):
        node = self._model.graph.get_node(node_id)
        if not node:
            return
        self._clear_props()
        layout = self._props_inner_layout
        stretch_item = layout.takeAt(layout.count() - 1)

        self._fill_node_properties(layout, node_id, node)

        layout.addItem(stretch_item)

    def _fill_node_properties(self, layout: QVBoxLayout, node_id: str, node: FlowNode):
        th = current_theme()
        sm = qt_scale_manager()
        accent_color = node_fill_color(node.node_type)

        # Identity section
        identity_frame = QFrame()
        identity_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {th.panel_bg};
                border: 1px solid {th.border_default};
                border-radius: 4px;
                border-left: 3px solid {accent_color};
            }}
        """)
        id_layout = QVBoxLayout(identity_frame)
        id_layout.setContentsMargins(sm.s(8), sm.s(4), sm.s(4), sm.s(4))

        pill = QLabel(f"  {node_type_label(node.node_type)}  ")
        pill.setStyleSheet(f"""
            background-color: {accent_color};
            color: {th.text_on_accent_bright};
            font-weight: bold;
            font-size: {sm.s(9)}px;
            border-radius: 3px;
            padding: 2px 6px;
        """)
        id_layout.addWidget(pill)

        desc = QLabel(node.describe())
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {th.text_muted}; font-size: {sm.s(9)}px;")
        id_layout.addWidget(desc)

        layout.addWidget(identity_frame)

        # Settings section
        settings_frame = QFrame()
        settings_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {th.panel_bg};
                border: 1px solid {th.border_default};
                border-radius: 4px;
            }}
        """)
        s_layout = QVBoxLayout(settings_frame)
        s_layout.setContentsMargins(sm.s(8), sm.s(4), sm.s(4), sm.s(4))

        s_title = QLabel(t("workflow.properties.settings"))
        s_title.setStyleSheet(f"color: {th.text_primary}; font-weight: bold; font-size: {sm.s(10)}px;")
        s_layout.addWidget(s_title)

        enable_cb = themed_checkbutton(None, t("common.enabled"), checked=node.enabled)
        enable_cb.stateChanged.connect(lambda: self._controller.toggle_node_enabled(node_id))
        enable_cb.stateChanged.connect(lambda: self._canvas.update_node_position(node_id))
        s_layout.addWidget(enable_cb)

        comment_label = QLabel(f"{t('workflow.properties.comment')}:")
        comment_label.setStyleSheet(f"color: {th.text_muted}; font-size: {sm.s(9)}px;")
        s_layout.addWidget(comment_label)

        comment_edit = themed_entry(None, text=node.comment or "")
        comment_edit.textChanged.connect(lambda text: self._update_comment(node_id, text))
        s_layout.addWidget(comment_edit)

        if node.node_type == NodeType.ACTION:
            edit_btn = themed_button(None, t("workflow.properties.edit_action"), style="primary")
            edit_btn.clicked.connect(lambda: self._edit_node_action(node_id))
            s_layout.addWidget(edit_btn)
        elif node.node_type == NodeType.CONDITION:
            edit_btn = themed_button(None, t("workflow.properties.edit_condition"), style="primary")
            edit_btn.clicked.connect(lambda: self._edit_node_condition(node_id))
            s_layout.addWidget(edit_btn)
        elif node.node_type == NodeType.LOOP:
            loop_row = QHBoxLayout()
            loop_label = QLabel(t("common.loop_count_label"))
            loop_label.setStyleSheet(f"color: {th.text_primary}; font-size: {sm.s(10)}px;")
            loop_row.addWidget(loop_label)
            loop_spin = themed_spinbox(None, minimum=0, maximum=9999, value=node.loop_count)
            loop_spin.valueChanged.connect(lambda v: setattr(node, "loop_count", v))
            loop_row.addWidget(loop_spin)
            hint = QLabel(t("common.loop_count_hint"))
            hint.setStyleSheet(f"color: {th.text_muted}; font-size: {sm.s(8)}px;")
            loop_row.addWidget(hint)
            loop_row.addStretch()
            s_layout.addLayout(loop_row)

        layout.addWidget(settings_frame)

        # Connections section
        outgoing = self._model.graph.get_outgoing_edges(node_id)
        incoming = [e for e in self._model.graph.edges if e.to_node == node_id]
        conn_frame = QFrame()
        conn_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {th.panel_bg};
                border: 1px solid {th.border_default};
                border-radius: 4px;
            }}
        """)
        c_layout = QVBoxLayout(conn_frame)
        c_layout.setContentsMargins(sm.s(8), sm.s(4), sm.s(4), sm.s(4))
        c_title = QLabel(t("workflow.properties.connections"))
        c_title.setStyleSheet(f"color: {th.text_primary}; font-weight: bold; font-size: {sm.s(10)}px;")
        c_layout.addWidget(c_title)
        c_info = QLabel(
            f"{t('workflow.properties.edges_in')}: {len(incoming)}  "
            f"{t('workflow.properties.edges_out')}: {len(outgoing)}",
        )
        c_info.setStyleSheet(f"color: {th.text_muted}; font-size: {sm.s(9)}px;")
        c_layout.addWidget(c_info)
        layout.addWidget(conn_frame)

        # Error config section
        if node.node_type in (NodeType.ACTION, NodeType.LOOP):
            self._build_error_config_section(layout, node_id, node)

        delete_btn = self._make_danger_button(
            f"✕ {t('workflow.properties.delete_node')}",
            lambda: self._delete_node(node_id),
        )
        layout.addWidget(delete_btn)

    def _update_comment(self, node_id: str, comment: str):
        node = self._model.graph.get_node(node_id)
        if node:
            node.comment = comment

    @staticmethod
    def _make_danger_button(text: str, command) -> QPushButton:
        th = current_theme()
        sm = qt_scale_manager()
        btn = QPushButton(text)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {th.accent_red};
                border: 1px solid {th.accent_red};
                border-radius: 3px;
                padding: {sm.s(4)}px;
                font-size: {sm.s(9)}px;
            }}
            QPushButton:hover {{
                background-color: {th.accent_red};
                color: white;
            }}
        """)
        btn.clicked.connect(command)
        return btn

    _STRATEGY_OPTIONS = [
        ("inherit", None),
        ("strategy.ignore", ErrorStrategy.IGNORE),
        ("strategy.skip", ErrorStrategy.SKIP),
        ("strategy.retry", ErrorStrategy.RETRY),
        ("strategy.fallback", ErrorStrategy.FALLBACK),
        ("strategy.fail_fast", ErrorStrategy.FAIL_FAST),
    ]
    _EXHAUSTED_OPTIONS = [
        ("strategy.ignore", ErrorStrategy.IGNORE),
        ("strategy.skip", ErrorStrategy.SKIP),
        ("strategy.fail_fast", ErrorStrategy.FAIL_FAST),
    ]

    def _build_error_config_section(self, layout: QVBoxLayout, node_id: str, node: FlowNode):
        th = current_theme()
        sm = qt_scale_manager()
        ec = node.error_config

        ec_frame = QFrame()
        ec_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {th.panel_bg};
                border: 1px solid {th.border_default};
                border-radius: 4px;
            }}
        """)
        ec_layout = QVBoxLayout(ec_frame)
        ec_layout.setContentsMargins(sm.s(8), sm.s(4), sm.s(4), sm.s(4))

        ec_title = QLabel(t("error_config.title"))
        ec_title.setStyleSheet(f"color: {th.text_primary}; font-weight: bold; font-size: {sm.s(10)}px;")
        ec_layout.addWidget(ec_title)

        strategy_options = [(v, f"error_config.{k}") for k, v in self._STRATEGY_OPTIONS]
        current_idx = self._find_strategy_index(ec.strategy if ec else None)
        strategy_combo = themed_dropdown(None, options=strategy_options)
        strategy_combo.setCurrentIndex(current_idx)
        ec_layout.addWidget(strategy_combo)

        retry_retries_spin = themed_spinbox(None, minimum=1, maximum=100,
                                            value=ec.retry_policy.max_retries if ec and ec.retry_policy else 3)

        retry_base_spin = QDoubleSpinBox()
        retry_base_spin.setRange(0.1, 60.0)
        retry_base_spin.setSingleStep(0.1)
        retry_base_spin.setDecimals(1)
        retry_base_spin.setValue(ec.retry_policy.base_delay if ec and ec.retry_policy else 1.0)

        retry_max_spin = QDoubleSpinBox()
        retry_max_spin.setRange(1.0, 300.0)
        retry_max_spin.setSingleStep(1.0)
        retry_max_spin.setDecimals(1)
        retry_max_spin.setValue(ec.retry_policy.max_delay if ec and ec.retry_policy else 30.0)

        exhausted_options = [(v, f"error_config.{k}") for k, v in self._EXHAUSTED_OPTIONS]
        exhausted_combo = themed_dropdown(None, options=exhausted_options)
        if ec and ec.exhausted_strategy:
            idx = exhausted_combo.findData(ec.exhausted_strategy)
            if idx >= 0:
                exhausted_combo.setCurrentIndex(idx)

        fallback_edit = themed_entry(
            None,
            text=ec.fallback_label if ec and ec.strategy == ErrorStrategy.FALLBACK else "fallback",
        )

        detail_widget = QWidget()
        detail_layout = QVBoxLayout(detail_widget)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        ec_layout.addWidget(detail_widget)

        def _make_row(label_text: str, widget: QWidget) -> QHBoxLayout:
            row = QHBoxLayout()
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"color: {th.text_muted}; font-size: {sm.s(9)}px;")
            row.addWidget(lbl)
            row.addWidget(widget)
            row.addStretch()
            return row

        def _refresh_detail(*_):
            self._clear_layout(detail_layout)
            selected_strategy = strategy_combo.currentData()

            if selected_strategy == ErrorStrategy.RETRY:
                retry_retries_spin.setParent(detail_widget)
                detail_layout.addLayout(_make_row(t("error_config.max_retries"), retry_retries_spin))
                retry_base_spin.setParent(detail_widget)
                detail_layout.addLayout(_make_row(t("error_config.base_delay"), retry_base_spin))
                retry_max_spin.setParent(detail_widget)
                detail_layout.addLayout(_make_row(t("error_config.max_delay"), retry_max_spin))
                exhausted_combo.setParent(detail_widget)
                detail_layout.addLayout(_make_row(t("error_config.exhausted_strategy"), exhausted_combo))
            elif selected_strategy == ErrorStrategy.FALLBACK:
                fallback_edit.setParent(detail_widget)
                detail_layout.addLayout(_make_row(t("error_config.fallback_label"), fallback_edit))

        strategy_combo.currentIndexChanged.connect(_refresh_detail)
        _refresh_detail()

        apply_btn = themed_button(None, t("common.ok"), style="primary")
        apply_btn.clicked.connect(lambda: self._apply_error_config(
            node_id, strategy_combo, retry_retries_spin, retry_base_spin,
            retry_max_spin, exhausted_combo, fallback_edit,
        ))
        ec_layout.addWidget(apply_btn)
        layout.addWidget(ec_frame)

    def _find_strategy_index(self, strategy: ErrorStrategy | None) -> int:
        if strategy is None:
            return 0
        for i, (_, v) in enumerate(self._STRATEGY_OPTIONS):
            if v == strategy:
                return i
        return 0

    def _apply_error_config(
        self, node_id, combo, retry_retries_spin, retry_base_spin,
        retry_max_spin, exhausted_combo, fallback_edit,
    ):
        selected_strategy = combo.currentData()

        if selected_strategy is None:
            new_ec = None
        elif selected_strategy == ErrorStrategy.RETRY:
            ex_strategy = exhausted_combo.currentData()
            new_ec = ErrorConfig(
                strategy=ErrorStrategy.RETRY,
                retry_policy=RetryPolicy(
                    max_retries=retry_retries_spin.value(),
                    base_delay=retry_base_spin.value(),
                    max_delay=retry_max_spin.value(),
                ),
                exhausted_strategy=ex_strategy,
            )
        elif selected_strategy == ErrorStrategy.FALLBACK:
            new_ec = ErrorConfig(
                strategy=ErrorStrategy.FALLBACK,
                fallback_label=fallback_edit.text(),
            )
        else:
            new_ec = ErrorConfig(strategy=selected_strategy)

        self._controller.update_node_error_config(node_id, new_ec)
        self._append_log(
            t("error_config.custom") if selected_strategy else t("error_config.inherit"),
        )

    # ── 连线属性 ─────────────────────────────────────────────

    def _show_edge_properties(self, edge_id: str):
        edge = self._model.graph.get_edge(edge_id)
        if not edge:
            return
        self._clear_props()
        layout = self._props_inner_layout
        stretch_item = layout.takeAt(layout.count() - 1)
        self._fill_edge_properties(layout, edge)
        layout.addItem(stretch_item)

    def _fill_edge_properties(self, layout: QVBoxLayout, edge: FlowEdge):
        th = current_theme()
        sm = qt_scale_manager()

        # Info section
        info_frame = QFrame()
        info_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {th.panel_bg};
                border: 1px solid {th.border_default};
                border-radius: 4px;
                border-left: 3px solid {th.edge_default};
            }}
        """)
        info_layout = QVBoxLayout(info_frame)
        info_layout.setContentsMargins(sm.s(8), sm.s(4), sm.s(4), sm.s(4))

        title = QLabel(t("workflow.properties.edge_info"))
        title.setStyleSheet(f"color: {th.text_primary}; font-weight: bold; font-size: {sm.s(10)}px;")
        info_layout.addWidget(title)

        from_node = self._model.graph.get_node(edge.from_node)
        to_node = self._model.graph.get_node(edge.to_node)
        from_label = from_node.describe() if from_node else edge.from_node
        to_label = to_node.describe() if to_node else edge.to_node

        from_lbl = QLabel(f"{t('workflow.properties.edge_from')}: {from_label}")
        from_lbl.setWordWrap(True)
        from_lbl.setStyleSheet(f"color: {th.text_muted}; font-size: {sm.s(9)}px;")
        info_layout.addWidget(from_lbl)

        to_lbl = QLabel(f"{t('workflow.properties.edge_to')}: {to_label}")
        to_lbl.setWordWrap(True)
        to_lbl.setStyleSheet(f"color: {th.text_muted}; font-size: {sm.s(9)}px;")
        info_layout.addWidget(to_lbl)

        layout.addWidget(info_frame)

        # Settings section
        settings_frame = QFrame()
        settings_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {th.panel_bg};
                border: 1px solid {th.border_default};
                border-radius: 4px;
            }}
        """)
        s_layout = QVBoxLayout(settings_frame)
        s_layout.setContentsMargins(sm.s(8), sm.s(4), sm.s(4), sm.s(4))

        s_title = QLabel(t("workflow.properties.settings"))
        s_title.setStyleSheet(f"color: {th.text_primary}; font-weight: bold; font-size: {sm.s(10)}px;")
        s_layout.addWidget(s_title)

        label_label = QLabel(f"{t('workflow.properties.edge_label')}:")
        label_label.setStyleSheet(f"color: {th.text_muted}; font-size: {sm.s(9)}px;")
        s_layout.addWidget(label_label)

        label_combo = themed_dropdown(None, options=[
            (EdgeLabel.DEFAULT, EdgeLabel.DEFAULT),
            (EdgeLabel.TRUE, EdgeLabel.TRUE),
            (EdgeLabel.FALSE, EdgeLabel.FALSE),
            (EdgeLabel.TIMEOUT, EdgeLabel.TIMEOUT),
            (EdgeLabel.LOOP, EdgeLabel.LOOP),
            (EdgeLabel.EXIT, EdgeLabel.EXIT),
        ])
        label_combo.setCurrentText(edge.label)
        s_layout.addWidget(label_combo)

        pri_row = QHBoxLayout()
        pri_label = QLabel(f"{t('workflow.properties.edge_priority')}:")
        pri_label.setStyleSheet(f"color: {th.text_muted}; font-size: {sm.s(9)}px;")
        pri_row.addWidget(pri_label)
        pri_spin = themed_spinbox(None, minimum=0, maximum=99, value=edge.priority)
        pri_row.addWidget(pri_spin)
        pri_row.addStretch()
        s_layout.addLayout(pri_row)

        layout.addWidget(settings_frame)

        def _on_label_change(new_text: str):
            if new_text == edge.label:
                return
            old_label = edge.label
            self._controller.update_edge_property(
                edge.edge_id, "label", old_label, new_text,
            )
            self._canvas.render_graph(self._model.graph)

        def _on_priority_change(new_val: int):
            if new_val == edge.priority:
                return
            old_pri = edge.priority
            self._controller.update_edge_property(
                edge.edge_id, "priority", old_pri, new_val,
            )

        label_combo.currentTextChanged.connect(_on_label_change)
        pri_spin.valueChanged.connect(_on_priority_change)

        delete_btn = self._make_danger_button(
            f"✕ {t('workflow.properties.delete_edge')}",
            lambda: self._on_delete_edge(edge.edge_id),
        )
        layout.addWidget(delete_btn)
