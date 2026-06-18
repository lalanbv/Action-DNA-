"""Qt 动作链页面的属性面板渲染。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSpinBox, QToolButton,
)

from src.panel.canvas.theme import current_theme, node_fill_color
from src.panel.components.step_param_view import iter_all_fields, key_field_rows
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

    def _clear_props(self) -> None:
        """清空属性面板（递归释放 widget 与子布局项）。

        Qt 的 ``takeAt`` 对 ``addLayout`` 加入的子布局返回 layout 项
        （``widget()`` 为 None）；旧实现仅 ``deleteLater`` widget 项，
        导致按钮行/移动行等子布局及其内部 widget 在重渲染时泄漏。
        """
        self._clear_layout(self._props_layout)

    def _clear_layout(self, layout) -> None:
        """递归移除并释放 layout 内全部 widget / 子布局项。"""
        while layout.count() > 0:
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            else:
                sub = item.layout()
                if sub is not None:
                    self._clear_layout(sub)

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
        """渲染步骤详情：类型/序号 + 摘要 + 移动序号 + 关键参数 + 全部字段 + 启用/备注 + 操作按钮。"""
        self._clear_props()
        th = current_theme()
        sm = qt_scale_manager()

        self._add_type_header(step, index, total, th, sm)
        self._add_summary(step, th, sm)
        if total > 1:
            self._props_layout.addLayout(self._build_move_to_row(index, total, th, sm))
        rows = key_field_rows(step)
        if rows:
            self._add_section_title(t("chain.detail.key_fields"))
            self._props_layout.addWidget(self._build_param_grid(rows, th, sm, sm.s(9)))
        all_pairs = list(iter_all_fields(step))
        if all_pairs:
            self._add_collapsible_fields(all_pairs, th, sm)
        self._add_enable_row(step, th, sm)
        self._add_comment_row(step, th, sm)
        self._props_layout.addLayout(self._build_action_buttons(th, sm))
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

    def _add_type_header(self, step, index: int, total: int, th, sm) -> None:
        """类型胶囊 + 序号。"""
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

    def _add_summary(self, step, th, sm) -> None:
        """describe 摘要（修历史漏渲染 bug —— Qt 端此前缺失此行）。"""
        summary = step.describe() if hasattr(step, "describe") else ""
        if not summary:
            return
        label = QLabel(summary)
        label.setWordWrap(True)
        label.setStyleSheet(f"color: {th.text_primary}; font-size: {sm.s(10)}px;")
        self._props_layout.addWidget(label)

    def _build_move_to_row(self, index: int, total: int, th, sm) -> QHBoxLayout:
        row = QHBoxLayout()
        label = QLabel(t("chain.detail.move_to"))
        label.setStyleSheet(f"color: {th.text_muted}; font-size: {sm.s(9)}px;")
        row.addWidget(label)
        spin = QSpinBox()
        spin.setRange(1, total)
        spin.setValue(index + 1)
        spin.setFixedHeight(sm.s(22))
        spin.setObjectName("dnaDetailInput")
        row.addWidget(spin)
        confirm = QPushButton(t("chain.detail.move_confirm"))
        confirm.setFixedHeight(sm.s(22))
        confirm.setObjectName("dnaDetailBtn")
        # 捕获渲染时 index 作 source，避免用户改 SpinBox 后切换选中导致 source 错位
        confirm.clicked.connect(lambda _c, sp=spin, src=index: self._on_move_to_index(src, sp.value() - 1))
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

    def _add_enable_row(self, step, th, sm) -> None:
        """启用复选框。"""
        cb = QCheckBox(t("common.enabled"))
        cb.setChecked(step.enabled)
        cb.setStyleSheet(f"color: {th.text_primary};")
        cb.stateChanged.connect(
            lambda state, s=step: (setattr(s, "enabled", bool(state)), self._on_step_enabled_change()),
        )
        self._props_layout.addWidget(cb)

    def _add_comment_row(self, step, th, sm) -> None:
        """备注输入框。"""
        label = QLabel(f"{t('chain.col.comment')}:")
        label.setStyleSheet(f"color: {th.text_muted}; font-size: {sm.s(9)}px;")
        self._props_layout.addWidget(label)
        edit = QLineEdit(step.comment or "")
        edit.setObjectName("dnaDetailInput")
        edit.textChanged.connect(lambda text: setattr(step, "comment", text))
        self._props_layout.addWidget(edit)

    def _build_action_buttons(self, th, sm) -> QHBoxLayout:
        """操作按钮行：↑ ↓ 复制 编辑 删除。"""
        row = QHBoxLayout()
        for text, handler in [
            ("↑", self._on_move_up),
            ("↓", self._on_move_down),
            (t("common.duplicate"), self._on_duplicate),
            (t("common.edit"), self._on_edit_step),
        ]:
            b = QPushButton(text)
            b.setObjectName("dnaDetailBtn")
            b.clicked.connect(handler)
            row.addWidget(b)

        del_btn = QPushButton(t("common.delete"))
        del_btn.setObjectName("dnaDeleteBtn")
        del_btn.clicked.connect(self._on_delete_step)
        row.addWidget(del_btn)
        return row
