"""WorkflowPropertiesMixin — 右侧属性面板填充。"""

import tkinter as tk
from tkinter import ttk

from src.core.flow import FlowEdge, FlowNode, NodeType
from src.core.error.error_config import ErrorConfig, ErrorStrategy, RetryPolicy
from src.panel.canvas.theme import current_theme, node_fill_color
from src.panel.canvas.node_renderer import _type_label as node_type_label
from src.panel.canvas.scale import scale_manager
from src.panel.widgets import (
    themed_button,
    themed_checkbutton,
    themed_danger_link,
    themed_entry,
    themed_frame,
    themed_label,
    themed_labelframe,
    themed_separator,
    themed_spinbox,
)
from src.utils.i18n import t


class WorkflowPropertiesMixin:
    """属性面板相关方法，供 WorkflowPage 继承。

    依赖 self 属性:
        _model, _canvas, _controller, _selected_node_id, _prop_panel
    """

    def _cleanup_prop_vars(self) -> None:
        for var, trace_name in getattr(self, "_prop_traced_vars", []):
            try:
                var.trace_remove("write", trace_name)
            except Exception:
                pass
        self._prop_traced_vars = []

    @staticmethod
    def _build_accent_sidebar(content: tk.Frame, color: str) -> tk.Frame:
        """创建强调色左边框 + 内容区域，返回 inner frame。"""
        theme = current_theme()
        sm = scale_manager()
        px = theme.pad_xs
        bar = tk.Canvas(content, width=sm.s(3), highlightthickness=0, bg=theme.panel_bg)
        bar.pack(side=tk.LEFT, fill=tk.Y, padx=(0, px))
        bar.bind("<Configure>", lambda e: bar.create_rectangle(
            0, 0, sm.s(3), e.height, fill=color, outline="",
        ))
        inner = themed_frame(content)
        inner.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        return inner

    def _track_var(self, var: tk.Variable, *trace_args) -> tk.Variable:
        if not hasattr(self, "_prop_traced_vars"):
            self._prop_traced_vars = []
        trace_name = var.trace_add("write", *trace_args)
        self._prop_traced_vars.append((var, trace_name))
        return var

    def _show_node_properties(self, node_id: str):
        node = self._model.graph.get_node(node_id)
        if not node:
            return

        self._prop_panel.show_properties(
            lambda content: self._fill_node_properties(content, node_id, node),
        )

    def _fill_node_properties(self, content: tk.Frame, node_id: str, node: FlowNode):
        self._cleanup_prop_vars()
        theme = current_theme()
        sm = scale_manager()
        px = theme.pad_xs
        py = theme.pad_xs

        inner = self._build_accent_sidebar(content, node_fill_color(node.node_type))

        # ── 基本信息 ──
        identity_frame = themed_labelframe(inner, text=t("workflow.properties.identity"))
        identity_frame.pack(fill=tk.X, padx=px, pady=(py, px))

        pill_color = node_fill_color(node.node_type)
        tk.Label(
            identity_frame,
            text=f"  {node_type_label(node.node_type)}  ",
            bg=pill_color, fg=theme.text_on_accent_bright,
            font=(theme.font_family, sm.s(9), "bold"),
        ).pack(anchor=tk.W, padx=px, pady=(px, 2))

        desc = node.describe()
        themed_label(
            identity_frame, text=desc, style="small", wraplength=sm.s(220),
        ).pack(anchor=tk.W, padx=px, pady=(0, px))

        # ── 设置 ──
        settings_frame = themed_labelframe(inner, text=t("workflow.properties.settings"))
        settings_frame.pack(fill=tk.X, padx=px, pady=px)

        enable_var = tk.BooleanVar(value=node.enabled)
        self._track_var(
            enable_var,
            lambda *_: (
                self._controller.toggle_node_enabled(node_id),
                self._canvas.update_node_visual(node_id),
            ),
        )
        themed_checkbutton(
            settings_frame, text=t("common.enabled"),
            variable=enable_var,
        ).pack(anchor=tk.W, padx=px, pady=(px, 2))

        themed_label(
            settings_frame, text=f"{t('workflow.properties.comment')}:",
            style="small",
        ).pack(anchor=tk.W, padx=px, pady=(sm.s(4), 0))

        comment_var = tk.StringVar(value=node.comment)
        comment_entry = themed_entry(settings_frame, textvariable=comment_var)
        comment_entry.pack(fill=tk.X, padx=px, pady=2)
        self._track_var(
            comment_var,
            lambda *_: self._update_comment(node_id, comment_var.get()),
        )

        if node.node_type == NodeType.ACTION:
            themed_button(
                settings_frame, text=t("workflow.properties.edit_action"),
                command=lambda: self._edit_node_action(node_id),
            ).pack(fill=tk.X, padx=px, pady=(sm.s(4), px))
        elif node.node_type == NodeType.CONDITION:
            themed_button(
                settings_frame, text=t("workflow.properties.edit_condition"),
                command=lambda: self._edit_node_condition(node_id),
            ).pack(fill=tk.X, padx=px, pady=(sm.s(4), px))
        elif node.node_type == NodeType.LOOP:
            self._build_loop_count_editor(settings_frame, node_id, node, px, sm)

        # ── 连接 ──
        outgoing = self._model.graph.get_outgoing_edges(node_id)
        incoming = [e for e in self._model.graph.edges if e.to_node == node_id]
        conn_frame = themed_labelframe(inner, text=t("workflow.properties.connections"))
        conn_frame.pack(fill=tk.X, padx=px, pady=px)
        themed_label(
            conn_frame,
            text=f"{t('workflow.properties.edges_in')}: {len(incoming)}  "
                 f"{t('workflow.properties.edges_out')}: {len(outgoing)}",
            style="small",
        ).pack(anchor=tk.W, padx=px, pady=px)

        # ── 错误配置 ──
        if node.node_type in (NodeType.ACTION, NodeType.LOOP):
            self._build_error_config_section(inner, node_id, node)

        # ── 危险操作 ──
        themed_separator(inner).pack(fill=tk.X, padx=px, pady=sm.s(6))
        themed_danger_link(
            inner,
            text=f"✕ {t('workflow.properties.delete_node')}",
            on_click=lambda: self._delete_node(node_id),
        ).pack(anchor=tk.W, padx=px, pady=(sm.s(4), sm.s(2)))

    def _build_loop_count_editor(self, parent, node_id, node, px, sm):
        loop_frame = themed_frame(parent)
        loop_frame.pack(fill=tk.X, padx=px, pady=(sm.s(4), px))
        themed_label(
            loop_frame, text=t("common.loop_count_label"), style="body",
        ).pack(side=tk.LEFT)
        loop_count_var = tk.IntVar(value=node.loop_count)
        themed_spinbox(
            loop_frame, from_=0, to=9999, textvariable=loop_count_var, width=6,
        ).pack(side=tk.LEFT, padx=4)
        themed_label(
            loop_frame, text=t("common.loop_count_hint"), style="small",
        ).pack(side=tk.LEFT)

        def _on_loop_count_change(*_):
            node.loop_count = loop_count_var.get()
        self._track_var(loop_count_var, _on_loop_count_change)

    def _update_comment(self, node_id: str, comment: str):
        node = self._model.graph.get_node(node_id)
        if node:
            node.comment = comment

    def _build_error_config_section(self, content: tk.Frame, node_id: str, node: FlowNode):
        theme = current_theme()
        sm = scale_manager()
        px = theme.pad_xs

        ec_frame = themed_labelframe(content, text=t("error_config.title"))
        ec_frame.pack(fill=tk.X, padx=px, pady=px)

        ec = node.error_config
        current_strategy = ec.strategy if ec else None

        strategy_frame = themed_frame(ec_frame)
        strategy_frame.pack(fill=tk.X, padx=px, pady=(px, 2))
        themed_label(
            strategy_frame, text=t("error_config.strategy"), style="small",
        ).pack(side=tk.LEFT)

        strategy_options = [
            (t("error_config.inherit"), None),
            (t("error_config.strategy.ignore"), ErrorStrategy.IGNORE),
            (t("error_config.strategy.skip"), ErrorStrategy.SKIP),
            (t("error_config.strategy.retry"), ErrorStrategy.RETRY),
            (t("error_config.strategy.fallback"), ErrorStrategy.FALLBACK),
            (t("error_config.strategy.fail_fast"), ErrorStrategy.FAIL_FAST),
        ]
        strategy_labels = [s[0] for s in strategy_options]

        current_idx = 0
        if current_strategy is not None:
            for i, (_, v) in enumerate(strategy_options):
                if v == current_strategy:
                    current_idx = i
                    break

        strategy_var = tk.StringVar(value=strategy_labels[current_idx])
        ttk.Combobox(
            strategy_frame, textvariable=strategy_var,
            state="readonly", width=12, values=strategy_labels,
        ).pack(side=tk.LEFT, padx=4)

        detail_frame = themed_frame(ec_frame)
        detail_frame.pack(fill=tk.X, padx=px, pady=2)

        retry_retries_var = tk.IntVar(
            value=ec.retry_policy.max_retries if ec and ec.retry_policy else 3,
        )
        retry_base_var = tk.DoubleVar(
            value=ec.retry_policy.base_delay if ec and ec.retry_policy else 1.0,
        )
        retry_max_var = tk.DoubleVar(
            value=ec.retry_policy.max_delay if ec and ec.retry_policy else 30.0,
        )
        exhausted_var = tk.StringVar(value=t("error_config.strategy.skip"))
        fallback_var = tk.StringVar(
            value=ec.fallback_label if ec and ec.strategy == ErrorStrategy.FALLBACK else "fallback",
        )

        exhausted_options = [
            t("error_config.strategy.ignore"),
            t("error_config.strategy.skip"),
            t("error_config.strategy.fail_fast"),
        ]
        exhausted_values = [ErrorStrategy.IGNORE, ErrorStrategy.SKIP, ErrorStrategy.FAIL_FAST]

        if ec and ec.exhausted_strategy:
            for i, v in enumerate(exhausted_values):
                if v == ec.exhausted_strategy:
                    exhausted_var.set(exhausted_options[i])
                    break

        def _refresh_detail(*_):
            for w in detail_frame.winfo_children():
                w.destroy()
            selected_label = strategy_var.get()
            selected_strategy = None
            for lbl, val in strategy_options:
                if lbl == selected_label:
                    selected_strategy = val
                    break

            if selected_strategy == ErrorStrategy.RETRY:
                for label_text, var, w, lo, hi, inc in [
                    (t("error_config.max_retries"), retry_retries_var, 5, 1, 100, 1),
                    (t("error_config.base_delay"), retry_base_var, 6, 0.1, 60.0, 0.1),
                    (t("error_config.max_delay"), retry_max_var, 6, 1.0, 300.0, 1.0),
                ]:
                    rf = themed_frame(detail_frame)
                    rf.pack(fill=tk.X, pady=1)
                    themed_label(rf, text=label_text, style="small").pack(side=tk.LEFT)
                    themed_spinbox(
                        rf, from_=lo, to=hi, increment=inc,
                        textvariable=var, width=w,
                    ).pack(side=tk.LEFT, padx=4)

                rf4 = themed_frame(detail_frame)
                rf4.pack(fill=tk.X, pady=1)
                themed_label(
                    rf4, text=t("error_config.exhausted_strategy"), style="small",
                ).pack(side=tk.LEFT)
                ttk.Combobox(
                    rf4, textvariable=exhausted_var,
                    state="readonly", width=10, values=exhausted_options,
                ).pack(side=tk.LEFT, padx=4)

            elif selected_strategy == ErrorStrategy.FALLBACK:
                rf = themed_frame(detail_frame)
                rf.pack(fill=tk.X, pady=1)
                themed_label(
                    rf, text=t("error_config.fallback_label"), style="small",
                ).pack(side=tk.LEFT)
                themed_entry(
                    rf, textvariable=fallback_var, width=12,
                ).pack(side=tk.LEFT, padx=4)

        def _apply_error_config():
            selected_label = strategy_var.get()
            selected_strategy = None
            for lbl, val in strategy_options:
                if lbl == selected_label:
                    selected_strategy = val
                    break

            if selected_strategy is None:
                new_ec = None
            elif selected_strategy == ErrorStrategy.RETRY:
                ex_label = exhausted_var.get()
                ex_strategy = ErrorStrategy.SKIP
                for i, lbl in enumerate(exhausted_options):
                    if lbl == ex_label:
                        ex_strategy = exhausted_values[i]
                        break
                new_ec = ErrorConfig(
                    strategy=ErrorStrategy.RETRY,
                    retry_policy=RetryPolicy(
                        max_retries=retry_retries_var.get(),
                        base_delay=retry_base_var.get(),
                        max_delay=retry_max_var.get(),
                    ),
                    exhausted_strategy=ex_strategy,
                )
            elif selected_strategy == ErrorStrategy.FALLBACK:
                new_ec = ErrorConfig(
                    strategy=ErrorStrategy.FALLBACK,
                    fallback_label=fallback_var.get(),
                )
            else:
                new_ec = ErrorConfig(strategy=selected_strategy)

            self._controller.update_node_error_config(node_id, new_ec)
            self._append_log(
                t("error_config.custom") + f": {selected_label}"
                if selected_strategy
                else t("error_config.inherit"),
            )

        self._track_var(strategy_var, _refresh_detail)
        _refresh_detail()
        themed_button(
            ec_frame, text=t("common.ok"), command=_apply_error_config,
        ).pack(fill=tk.X, padx=px, pady=(sm.s(4), px))

    # ── 连线属性 ─────────────────────────────────────────────

    def _show_edge_properties(self, edge_id: str):
        edge = self._model.graph.get_edge(edge_id)
        if not edge:
            return
        self._prop_panel.show_properties(
            lambda content: self._fill_edge_properties(content, edge),
        )

    def _fill_edge_properties(self, content: tk.Frame, edge: FlowEdge):
        self._cleanup_prop_vars()
        theme = current_theme()
        sm = scale_manager()
        px = theme.pad_xs
        py = theme.pad_xs

        inner = self._build_accent_sidebar(content, theme.edge_default)

        # ── 基本信息 ──
        info_frame = themed_labelframe(inner, text=t("workflow.properties.edge_info"))
        info_frame.pack(fill=tk.X, padx=px, pady=(py, px))

        from_node = self._model.graph.get_node(edge.from_node)
        to_node = self._model.graph.get_node(edge.to_node)
        from_label = from_node.describe() if from_node else edge.from_node
        to_label = to_node.describe() if to_node else edge.to_node

        themed_label(
            info_frame,
            text=f"{t('workflow.properties.edge_from')}: {from_label}",
            style="small",
        ).pack(anchor=tk.W, padx=px, pady=(px, 2))

        themed_label(
            info_frame,
            text=f"{t('workflow.properties.edge_to')}: {to_label}",
            style="small",
        ).pack(anchor=tk.W, padx=px, pady=2)

        # ── 标签和优先级 ──
        settings_frame = themed_labelframe(inner, text=t("workflow.properties.settings"))
        settings_frame.pack(fill=tk.X, padx=px, pady=px)

        label_var = tk.StringVar(value=edge.label)
        themed_label(
            settings_frame, text=f"{t('workflow.properties.edge_label')}:",
            style="small",
        ).pack(anchor=tk.W, padx=px, pady=(px, 0))
        label_combo = ttk.Combobox(
            settings_frame, textvariable=label_var,
            state="readonly", width=14,
            values=["default", "true", "false", "timeout", "loop", "exit"],
        )
        label_combo.pack(fill=tk.X, padx=px, pady=2)

        priority_var = tk.IntVar(value=edge.priority)
        priority_frame = themed_frame(settings_frame)
        priority_frame.pack(fill=tk.X, padx=px, pady=2)
        themed_label(
            priority_frame,
            text=f"{t('workflow.properties.edge_priority')}:",
            style="small",
        ).pack(side=tk.LEFT)
        themed_spinbox(
            priority_frame, from_=0, to=99,
            textvariable=priority_var, width=5,
        ).pack(side=tk.LEFT, padx=4)

        def _on_label_change(*_):
            new_label = label_var.get()
            if new_label == edge.label:
                return
            old_label = edge.label
            self._controller.update_edge_property(
                edge.edge_id, "label", old_label, new_label,
            )
            self._canvas.refresh_edge_visual(edge.edge_id)

        def _on_priority_change(*_):
            try:
                new_pri = priority_var.get()
            except tk.TclError:
                return
            if new_pri == edge.priority:
                return
            old_pri = edge.priority
            self._controller.update_edge_property(
                edge.edge_id, "priority", old_pri, new_pri,
            )

        self._track_var(label_var, _on_label_change)
        self._track_var(priority_var, _on_priority_change)

        # ── 危险操作 ──
        themed_separator(inner).pack(fill=tk.X, padx=px, pady=sm.s(6))
        themed_danger_link(
            inner,
            text=f"✕ {t('workflow.properties.delete_edge')}",
            on_click=lambda: self._on_delete_edge(edge.edge_id),
        ).pack(anchor=tk.W, padx=px, pady=(sm.s(4), sm.s(2)))
