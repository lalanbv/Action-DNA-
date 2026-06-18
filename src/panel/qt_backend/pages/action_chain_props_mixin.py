"""Qt 动作链页面的属性面板渲染。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSpinBox, QToolButton,
)

from src.panel.canvas.theme import current_theme, node_fill_color
from src.panel.components.step_key_fields import key_fields_for
from src.panel.components.step_param_view import format_field_value, iter_all_fields
from src.panel.qt_backend.scale import qt_scale_manager
from src.utils.i18n import t


class QtActionChainPropsMixin:
    """属性面板渲染 Mixin。

    要求宿主类提供:
      - self._props_layout: QVBoxLayout
      - self._selected_step_idx: int | None
      - self._controller
      - self._on_step_enabled_change()
      - self._on_move_up()
      - self._on_move_down()
      - self._on_move_to_index(target: int)
      - self._on_duplicate()
      - self._on_edit_step()
      - self._on_delete_step()
    """

    # ── 属性面板 ──────────────────────────────────────────

    def _clear_props(self):
        layout = self._props_layout
        while layout.count() > 0:
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _show_empty_props(self):
        self._clear_props()
        th = current_theme()
        sm = qt_scale_manager()
        hint = QLabel(t("chain.msg.select_step"))
        hint.setStyleSheet(f"color: {th.text_muted}; font-size: {sm.s(10)}px;")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._props_layout.addWidget(hint)
        self._props_layout.addStretch()

    def _show_step_props(self, step, index: int, total: int):
        """渲染步骤详情：类型/序号 + 摘要 + 移动到序号 + 关键参数 + 全部字段 + 启用/备注 + 操作按钮。"""
        self._clear_props()
        th = current_theme()
        sm = qt_scale_manager()

        # 1. 类型胶囊 + 序号
        type_name = step.action_type.value if hasattr(step.action_type, "value") else str(step.action_type)
        pill = QLabel(f"  {type_name}  ")
        pill.setStyleSheet(f"""
            background-color: {node_fill_color("ACTION")};
            color: {th.text_on_accent_bright};
            font-weight: bold; font-size: {sm.s(9)}px;
            border-radius: 3px; padding: 2px 6px;
        """)
        self._props_layout.addWidget(pill)

        desc = QLabel(f"#{index + 1} / {total}")
        desc.setStyleSheet(f"color: {th.text_muted}; font-size: {sm.s(9)}px;")
        self._props_layout.addWidget(desc)

        # 2. describe 摘要（修历史漏渲染 bug —— Qt 端此前缺失此行）
        summary = step.describe() if hasattr(step, "describe") else ""
        if summary:
            sum_label = QLabel(summary)
            sum_label.setWordWrap(True)
            sum_label.setStyleSheet(f"color: {th.text_primary}; font-size: {sm.s(10)}px;")
            self._props_layout.addWidget(sum_label)

        # 3. 移动到指定序号（多于 1 步时才显示）
        if total > 1:
            self._props_layout.addLayout(self._build_move_to_row(index, total, th, sm))

        # 4. 关键参数表（默认展开）
        kf = key_fields_for(step)
        if kf:
            self._add_section_title(t("chain.detail.key_fields"))
            rows = [(t(i18n_key), format_field_value(step, fname)) for fname, i18n_key in kf]
            self._props_layout.addWidget(self._build_param_grid(rows, th, sm, sm.s(9)))

        # 5. 全部字段（默认折叠）
        all_pairs = list(iter_all_fields(step))
        if all_pairs:
            self._add_collapsible_fields(all_pairs, th, sm)

        # 6. 启用
        enable_cb = QCheckBox(t("common.enabled"))
        enable_cb.setChecked(step.enabled)
        enable_cb.setStyleSheet(f"color: {th.text_primary};")
        enable_cb.stateChanged.connect(
            lambda state, s=step: (setattr(s, "enabled", bool(state)), self._on_step_enabled_change()),
        )
        self._props_layout.addWidget(enable_cb)

        # 7. 备注
        comment_label = QLabel(f"{t('chain.col.comment')}:")
        comment_label.setStyleSheet(f"color: {th.text_muted}; font-size: {sm.s(9)}px;")
        self._props_layout.addWidget(comment_label)
        comment_edit = QLineEdit(step.comment or "")
        comment_edit.setStyleSheet(self._input_style(th, sm))
        comment_edit.textChanged.connect(lambda text: setattr(step, "comment", text))
        self._props_layout.addWidget(comment_edit)

        # 8. 按钮：↑ ↓ 复制 编辑 删除
        btn_row = QHBoxLayout()
        btn_style = self._btn_style(th, sm)
        for text, handler in [
            ("↑", self._on_move_up),
            ("↓", self._on_move_down),
            (t("common.duplicate"), self._on_duplicate),
            (t("common.edit"), self._on_edit_step),
        ]:
            b = QPushButton(text)
            b.setStyleSheet(btn_style)
            b.clicked.connect(handler)
            btn_row.addWidget(b)

        del_btn = QPushButton(t("common.delete"))
        del_btn.setStyleSheet(self._delete_btn_style(th, sm))
        del_btn.clicked.connect(self._on_delete_step)
        btn_row.addWidget(del_btn)
        self._props_layout.addLayout(btn_row)

        self._props_layout.addStretch()

    # ── 渲染 helper ──────────────────────────────────────────

    def _add_section_title(self, text: str) -> None:
        th = current_theme()
        sm = qt_scale_manager()
        title = QLabel(text)
        title.setStyleSheet(
            f"color: {th.text_muted}; font-size: {sm.s(9)}px; font-weight: bold;"
        )
        self._props_layout.addWidget(title)

    def _build_move_to_row(self, index: int, total: int, th, sm) -> QHBoxLayout:
        row = QHBoxLayout()
        label = QLabel(t("chain.detail.move_to"))
        label.setStyleSheet(f"color: {th.text_muted}; font-size: {sm.s(9)}px;")
        row.addWidget(label)
        spin = QSpinBox()
        spin.setRange(1, total)
        spin.setValue(index + 1)
        spin.setFixedHeight(sm.s(22))
        spin.setStyleSheet(self._input_style(th, sm))
        row.addWidget(spin)
        confirm = QPushButton(t("chain.detail.move_confirm"))
        confirm.setFixedHeight(sm.s(22))
        confirm.setStyleSheet(self._btn_style(th, sm))
        # 实时读取 SpinBox 值（1-based → 0-based target）
        confirm.clicked.connect(lambda _c, sp=spin: self._on_move_to_index(sp.value() - 1))
        row.addWidget(confirm)
        row.addStretch()
        return row

    def _build_param_grid(self, rows: list[tuple[str, str]], th, sm, font_px: int) -> QFrame:
        """构建「标签 : 值」两列网格（rows = [(label, value), ...]）。"""
        grid = QGridLayout()
        grid.setHorizontalSpacing(sm.s(8))
        grid.setVerticalSpacing(sm.s(2))
        label_style = f"color: {th.text_muted}; font-size: {font_px}px;"
        value_style = f"color: {th.text_primary}; font-size: {font_px}px;"
        for row, (label_text, value_text) in enumerate(rows):
            lbl = QLabel(label_text)
            lbl.setStyleSheet(label_style)
            val = QLabel(value_text)
            val.setStyleSheet(value_style)
            val.setWordWrap(True)
            grid.addWidget(lbl, row, 0)
            grid.addWidget(val, row, 1)
        wrap = QFrame()
        wrap.setLayout(grid)
        return wrap

    def _add_collapsible_fields(self, pairs: list[tuple[str, str]], th, sm) -> None:
        """「全部字段」折叠区：默认收起，点击标题切换可见。"""
        n = len(pairs)
        title_text = f"{t('chain.detail.all_fields')} ({n})"

        toggle = QToolButton()
        toggle.setText("▷ " + title_text)
        toggle.setStyleSheet(
            f"color: {th.text_muted}; font-size: {sm.s(9)}px; border: none; text-align: left;"
        )
        toggle.setCheckable(True)

        body = self._build_param_grid(pairs, th, sm, sm.s(8))
        body.setVisible(False)

        def _toggle(checked: bool) -> None:
            body.setVisible(checked)
            toggle.setText(("▸ " if checked else "▷ ") + title_text)

        toggle.clicked.connect(_toggle)
        self._props_layout.addWidget(toggle)
        self._props_layout.addWidget(body)

    # ── 样式 helper（随主题刷新）──────────────────────────────

    def _input_style(self, th, sm) -> str:
        return f"""
            QLineEdit, QSpinBox {{
                background-color: {th.input_bg};
                color: {th.text_primary};
                border: 1px solid {th.border_default};
                border-radius: 3px;
                padding: 2px 4px;
                font-size: {sm.s(10)}px;
            }}
            QLineEdit:focus, QSpinBox:focus {{ border-color: {th.accent_blue}; }}
        """

    def _btn_style(self, th, sm) -> str:
        return f"""
            QPushButton {{
                background-color: {th.btn_bg};
                color: {th.text_primary};
                border: 1px solid {th.border_default};
                border-radius: 3px;
                padding: {sm.s(4)}px;
                font-size: {sm.s(10)}px;
            }}
            QPushButton:hover {{
                background-color: {th.btn_bg_hover};
                border-color: {th.accent_blue};
            }}
        """

    def _delete_btn_style(self, th, sm) -> str:
        return f"""
            QPushButton {{
                background-color: transparent;
                color: {th.accent_red};
                border: 1px solid {th.accent_red};
                border-radius: 3px;
                padding: {sm.s(4)}px;
                font-size: {sm.s(10)}px;
            }}
            QPushButton:hover {{
                background-color: {th.accent_red};
                color: white;
            }}
        """
