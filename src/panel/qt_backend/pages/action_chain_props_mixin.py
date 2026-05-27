"""Qt 动作链页面的属性面板渲染。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QHBoxLayout, QLabel, QLineEdit, QPushButton,
)

from src.panel.canvas.theme import current_theme, node_fill_color
from src.panel.qt_backend.scale import qt_scale_manager
from src.utils.i18n import t


class QtActionChainPropsMixin:
    """属性面板渲染 Mixin。

    要求宿主类提供:
      - self._props_layout: QVBoxLayout
      - self._selected_step_idx: int | None
      - self._on_step_enabled_change()
      - self._on_move_up()
      - self._on_move_down()
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
        self._clear_props()
        th = current_theme()
        sm = qt_scale_manager()

        type_name = step.action_type.value if hasattr(step.action_type, "value") else str(step.action_type)
        pill = QLabel(f"  {type_name}  ")
        pill.setStyleSheet(f"""
            background-color: {node_fill_color("ACTION")};
            color: {th.text_on_accent_bright};
            font-weight: bold;
            font-size: {sm.s(9)}px;
            border-radius: 3px;
            padding: 2px 6px;
        """)
        self._props_layout.addWidget(pill)

        desc = QLabel(f"#{index + 1} / {total}")
        desc.setStyleSheet(f"color: {th.text_muted}; font-size: {sm.s(9)}px;")
        self._props_layout.addWidget(desc)

        enable_cb = QCheckBox(t("common.enabled"))
        enable_cb.setChecked(step.enabled)
        enable_cb.setStyleSheet(f"color: {th.text_primary};")
        enable_cb.stateChanged.connect(
            lambda state, s=step: (setattr(s, "enabled", bool(state)), self._on_step_enabled_change()),
        )
        self._props_layout.addWidget(enable_cb)

        comment_label = QLabel(f"{t('chain.col.comment')}:")
        comment_label.setStyleSheet(f"color: {th.text_muted}; font-size: {sm.s(9)}px;")
        self._props_layout.addWidget(comment_label)
        comment_edit = QLineEdit(step.comment or "")
        comment_edit.setStyleSheet(f"""
            QLineEdit {{
                background-color: {th.input_bg};
                color: {th.text_primary};
                border: 1px solid {th.border_default};
                border-radius: 3px;
                padding: 2px 4px;
                font-size: {sm.s(10)}px;
            }}
            QLineEdit:focus {{ border-color: {th.accent_blue}; }}
        """)
        comment_edit.textChanged.connect(lambda text: setattr(step, "comment", text))
        self._props_layout.addWidget(comment_edit)

        btn_style = f"""
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
        btn_row = QHBoxLayout()
        up_btn = QPushButton("↑")
        up_btn.setStyleSheet(btn_style)
        up_btn.clicked.connect(self._on_move_up)
        btn_row.addWidget(up_btn)

        down_btn = QPushButton("↓")
        down_btn.setStyleSheet(btn_style)
        down_btn.clicked.connect(self._on_move_down)
        btn_row.addWidget(down_btn)

        edit_btn = QPushButton(t("common.edit"))
        edit_btn.setStyleSheet(btn_style)
        edit_btn.clicked.connect(self._on_edit_step)
        btn_row.addWidget(edit_btn)

        del_btn = QPushButton(t("common.delete"))
        del_btn.setStyleSheet(f"""
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
        """)
        del_btn.clicked.connect(self._on_delete_step)
        btn_row.addWidget(del_btn)
        self._props_layout.addLayout(btn_row)

        self._props_layout.addStretch()
