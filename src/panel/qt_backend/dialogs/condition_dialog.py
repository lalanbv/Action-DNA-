"""QtConditionDialog — PySide6 条件构建器对话框。

替代 tkinter open_condition_dialog，使用 QDialog。
支持简单条件和复合条件（AND/OR/NOT）的可视化构建。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QPushButton, QRadioButton, QSlider, QVBoxLayout, QWidget,
)

from src.core.action import MatchStrategy, ThresholdMode
from src.core.condition import Condition, ConditionType
from src.panel.canvas.theme import current_theme
from src.panel.qt_backend.scale import qt_scale_manager
from src.panel.qt_backend.widgets import themed_button, themed_entry, themed_frame, themed_label
from src.utils.i18n import t

_SIMPLE_CONDITION_TYPES = [
    ConditionType.IMAGE_FOUND,
    ConditionType.IMAGE_NOT_FOUND,
    ConditionType.VARIABLE_EXISTS,
    ConditionType.VARIABLE_COMPARE,
    ConditionType.ELAPSED_TIME,
]

_COMPARE_OPS = ["==", "!=", ">", "<", ">=", "<="]


class QtConditionDialog(QDialog):
    """条件构建器对话框。"""

    def __init__(
        self,
        parent: QWidget,
        condition: Condition | None = None,
        title: str | None = None,
    ) -> None:
        super().__init__(parent)
        th = current_theme()
        sm = qt_scale_manager()

        self.setWindowTitle(title or t("dialog.title.condition_builder"))
        self.setMinimumSize(sm.s(500), sm.s(480))
        self.setModal(True)

        if condition is None:
            condition = Condition(condition_type=ConditionType.IMAGE_FOUND)

        self._condition = condition
        self._children: list[Condition] = list(condition.children) if condition.children else []
        self._result: Condition | None = None
        self._fields_widgets: list[QWidget] = []

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(sm.s(th.pad_md), sm.s(th.pad_md), sm.s(th.pad_md), sm.s(th.pad_md))
        main_layout.setSpacing(sm.s(8))

        form = QFormLayout()
        form.setSpacing(sm.s(6))

        type_label = themed_label(self, text=t("dialog.label.condition_type"))
        self._type_combo = QComboBox()
        for ct in _SIMPLE_CONDITION_TYPES:
            self._type_combo.addItem(Condition.type_label(ct), ct.name)
        self._type_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {th.input_bg};
                color: {th.text_primary};
                border: 1px solid {th.border_default};
                border-radius: {sm.s(4)}px;
                padding: {sm.s(4)}px {sm.s(8)}px;
                min-width: {sm.s(200)}px;
            }}
        """)
        form.addRow(type_label, self._type_combo)

        if condition.condition_type in _SIMPLE_CONDITION_TYPES:
            idx = _SIMPLE_CONDITION_TYPES.index(condition.condition_type)
            self._type_combo.setCurrentIndex(idx)

        main_layout.addLayout(form)

        self._fields_container = QWidget()
        self._fields_layout = QVBoxLayout(self._fields_container)
        self._fields_layout.setContentsMargins(0, 0, 0, 0)
        self._fields_layout.setSpacing(sm.s(4))
        main_layout.addWidget(self._fields_container, 1)

        self._type_combo.currentIndexChanged.connect(self._rebuild_fields)
        self._rebuild_fields()

        self._build_compound_section(main_layout, th, sm)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = themed_button(self, text=t("common.cancel"), command=self.reject, style="secondary")
        btn_layout.addWidget(cancel_btn)
        ok_btn = themed_button(self, text=t("common.ok"), command=self._on_ok, style="primary")
        btn_layout.addWidget(ok_btn)
        main_layout.addLayout(btn_layout)

        self._center_on_parent(parent)

    def _rebuild_fields(self) -> None:
        for w in self._fields_widgets:
            w.setParent(None)
            w.deleteLater()
        self._fields_widgets.clear()

        cond = self._condition
        type_name = self._type_combo.currentData()
        if type_name is None:
            return
        selected = ConditionType[type_name]

        sm = qt_scale_manager()

        if selected in (ConditionType.IMAGE_FOUND, ConditionType.IMAGE_NOT_FOUND):
            self._build_image_fields(cond, sm)
        elif selected == ConditionType.VARIABLE_EXISTS:
            self._build_var_exists_fields(cond, sm)
        elif selected == ConditionType.VARIABLE_COMPARE:
            self._build_var_compare_fields(cond, sm)
        elif selected == ConditionType.ELAPSED_TIME:
            self._build_time_fields(cond, sm)

    def _build_image_fields(self, cond: Condition, sm) -> None:
        """图片条件字段 — 嵌入多模板管理器(主图 + 备用图 + 策略/阈值模式)。"""
        from src.panel.qt_backend.dialogs.multi_template_editor import MultiTemplateEditorQt

        self._image_editor = MultiTemplateEditorQt(parent=self)
        self._image_editor.set_state(
            cond.image_path, cond.alt_image_paths, cond.alt_thresholds,
            cond.threshold_mode, cond.match_strategy, cond.threshold,
        )
        self._fields_layout.addWidget(self._image_editor)
        self._fields_widgets.append(self._image_editor)

    def _build_var_exists_fields(self, cond: Condition, sm) -> None:
        th = current_theme()
        form = QFormLayout()
        form.setSpacing(sm.s(4))

        self._var_name_entry = QLineEdit(cond.variable_name)
        self._var_name_entry.setStyleSheet(f"""
            QLineEdit {{
                background-color: {th.input_bg}; color: {th.text_primary};
                border: 1px solid {th.border_default}; border-radius: {sm.s(3)}px;
                padding: {sm.s(3)}px {sm.s(6)}px;
            }}
        """)
        form.addRow(t("dialog.label.variable_name"), self._var_name_entry)

        hint = QLabel(t("dialog.hint.set_by_output_coord"))
        hint.setStyleSheet(f"color: {th.text_muted}; font-size: {sm.s(11)}px;")
        form.addRow(hint)

        container = QWidget()
        container.setLayout(form)
        self._fields_layout.addWidget(container)
        self._fields_widgets.append(container)

    def _build_var_compare_fields(self, cond: Condition, sm) -> None:
        th = current_theme()
        form = QFormLayout()
        form.setSpacing(sm.s(4))

        entry_style = f"""
            QLineEdit {{
                background-color: {th.input_bg}; color: {th.text_primary};
                border: 1px solid {th.border_default}; border-radius: {sm.s(3)}px;
                padding: {sm.s(3)}px {sm.s(6)}px;
            }}
        """

        self._var_name_entry = QLineEdit(cond.variable_name)
        self._var_name_entry.setStyleSheet(entry_style)
        form.addRow(t("dialog.label.variable_name"), self._var_name_entry)

        self._op_combo = QComboBox()
        self._op_combo.addItems(_COMPARE_OPS)
        if cond.compare_op in _COMPARE_OPS:
            self._op_combo.setCurrentText(cond.compare_op)
        self._op_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {th.input_bg}; color: {th.text_primary};
                border: 1px solid {th.border_default}; border-radius: {sm.s(3)}px;
                padding: {sm.s(3)}px {sm.s(6)}px; min-width: {sm.s(60)}px;
            }}
        """)
        form.addRow(t("dialog.label.compare_operator"), self._op_combo)

        self._val_x_entry = QLineEdit(str(cond.compare_value_x))
        self._val_x_entry.setStyleSheet(entry_style)
        form.addRow(t("dialog.label.target_value_x"), self._val_x_entry)

        self._val_y_entry = QLineEdit(str(cond.compare_value_y))
        self._val_y_entry.setStyleSheet(entry_style)
        form.addRow(t("dialog.label.target_value_y"), self._val_y_entry)

        container = QWidget()
        container.setLayout(form)
        self._fields_layout.addWidget(container)
        self._fields_widgets.append(container)

    def _build_time_fields(self, cond: Condition, sm) -> None:
        th = current_theme()
        form = QFormLayout()
        form.setSpacing(sm.s(4))

        entry_style = f"""
            QLineEdit {{
                background-color: {th.input_bg}; color: {th.text_primary};
                border: 1px solid {th.border_default}; border-radius: {sm.s(3)}px;
                padding: {sm.s(3)}px {sm.s(6)}px;
            }}
        """

        self._timer_entry = QLineEdit(cond.timer_name)
        self._timer_entry.setStyleSheet(entry_style)
        form.addRow(t("dialog.label.timer_name"), self._timer_entry)

        self._timeout_entry = QLineEdit(str(cond.timeout_seconds))
        self._timeout_entry.setStyleSheet(entry_style)
        form.addRow(t("dialog.label.timeout_seconds"), self._timeout_entry)

        hint = QLabel(t("dialog.hint.need_timer_step"))
        hint.setStyleSheet(f"color: {th.text_muted}; font-size: {sm.s(11)}px;")
        form.addRow(hint)

        container = QWidget()
        container.setLayout(form)
        self._fields_layout.addWidget(container)
        self._fields_widgets.append(container)

    def _build_compound_section(self, main_layout: QVBoxLayout, th, sm) -> None:
        compound_label = themed_label(self, text=t("dialog.label.compound_condition"))
        main_layout.addWidget(compound_label)

        self._children_list = QListWidget()
        self._children_list.setMaximumHeight(sm.s(80))
        self._children_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {th.bg_surface}; color: {th.text_primary};
                border: 1px solid {th.border_default}; border-radius: {sm.s(3)}px;
                font-size: {sm.s(12)}px;
            }}
            QListWidget::item:selected {{
                background-color: {th.accent_blue}; color: {th.text_on_accent};
            }}
        """)
        self._refresh_children_list()
        main_layout.addWidget(self._children_list)

        child_btn_layout = QHBoxLayout()
        add_btn = themed_button(
            self, text=t("dialog.btn.add_child"),
            command=self._add_child, style="secondary",
        )
        child_btn_layout.addWidget(add_btn)
        remove_btn = themed_button(
            self, text=t("dialog.btn.remove_child"),
            command=self._remove_child, style="secondary",
        )
        child_btn_layout.addWidget(remove_btn)
        child_btn_layout.addStretch()
        main_layout.addLayout(child_btn_layout)

        mode_row = QHBoxLayout()
        mode_label = themed_label(self, text=t("dialog.label.compound_mode"))
        mode_row.addWidget(mode_label)
        self._compound_radio_vars: dict[str, QRadioButton] = {}
        for text_val, val in [
            (t("dialog.compound_mode.none"), "NONE"),
            (t("dialog.compound_mode.and"), "AND"),
            (t("dialog.compound_mode.or"), "OR"),
            (t("dialog.compound_mode.not"), "NOT"),
        ]:
            rb = QRadioButton(text_val)
            rb.setStyleSheet(f"color: {th.text_primary};")
            self._compound_radio_vars[val] = rb
            mode_row.addWidget(rb)
        self._compound_radio_vars["NONE"].setChecked(True)
        mode_row.addStretch()
        main_layout.addLayout(mode_row)

    def _refresh_children_list(self) -> None:
        self._children_list.clear()
        for c in self._children:
            self._children_list.addItem(c.describe())

    def _add_child(self) -> None:
        child = Condition(condition_type=ConditionType.IMAGE_FOUND)
        dlg = QtConditionDialog(self, condition=child, title=t("dialog.title.add_child_condition"))
        if dlg.exec() == QDialog.Accepted:
            result = dlg.get_result()
            if result is not None:
                self._children.append(result)
                self._refresh_children_list()

    def _remove_child(self) -> None:
        row = self._children_list.currentRow()
        if 0 <= row < len(self._children):
            del self._children[row]
            self._refresh_children_list()

    def _browse_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            t("dialog.title.select_condition_image"),
            "",
            f"{t('dialog.filetype.image_files')} (*.png *.jpg *.jpeg *.bmp);;{t('dialog.filetype.all')} (*.*)",
        )
        if path:
            self._image_entry.setText(path)

    def _on_ok(self) -> None:
        compound_mode = self._get_compound_mode()
        if compound_mode != "NONE" and self._children:
            ct_map = {
                "AND": ConditionType.COMPOUND_AND,
                "OR": ConditionType.COMPOUND_OR,
                "NOT": ConditionType.COMPOUND_NOT,
            }
            self._result = Condition(
                condition_type=ct_map[compound_mode],
                children=list(self._children),
            )
        else:
            type_name = self._type_combo.currentData()
            selected = ConditionType[type_name] if type_name else ConditionType.IMAGE_FOUND

            image_path = ""
            threshold = 0.8
            alt_paths: list[str] = []
            alt_thresholds: list[float | None] = []
            mode = ThresholdMode.GLOBAL
            strategy = MatchStrategy.ADAPTIVE
            var_name = ""
            compare_op = ""
            val_x = 0
            val_y = 0
            timer_name = ""
            timeout = 0.0

            if selected in (ConditionType.IMAGE_FOUND, ConditionType.IMAGE_NOT_FOUND):
                if hasattr(self, "_image_editor"):
                    (image_path, alt_paths, alt_thresholds,
                     mode, strategy, threshold) = self._image_editor.get_state()
            elif selected == ConditionType.VARIABLE_EXISTS:
                var_name = self._var_name_entry.text().strip() if hasattr(self, "_var_name_entry") else ""
            elif selected == ConditionType.VARIABLE_COMPARE:
                var_name = self._var_name_entry.text().strip() if hasattr(self, "_var_name_entry") else ""
                compare_op = self._op_combo.currentText() if hasattr(self, "_op_combo") else "=="
                try:
                    val_x = int(self._val_x_entry.text()) if hasattr(self, "_val_x_entry") else 0
                except ValueError:
                    val_x = 0
                try:
                    val_y = int(self._val_y_entry.text()) if hasattr(self, "_val_y_entry") else 0
                except ValueError:
                    val_y = 0
            elif selected == ConditionType.ELAPSED_TIME:
                timer_name = self._timer_entry.text().strip() if hasattr(self, "_timer_entry") else ""
                try:
                    timeout = float(self._timeout_entry.text()) if hasattr(self, "_timeout_entry") else 0.0
                except ValueError:
                    timeout = 0.0

            self._result = Condition(
                condition_type=selected,
                image_path=image_path,
                threshold=threshold,
                alt_image_paths=alt_paths,
                alt_thresholds=alt_thresholds,
                match_strategy=strategy,
                threshold_mode=mode,
                variable_name=var_name,
                compare_op=compare_op,
                compare_value_x=val_x,
                compare_value_y=val_y,
                timer_name=timer_name,
                timeout_seconds=timeout,
            )

        self.accept()

    def _get_compound_mode(self) -> str:
        for val, rb in self._compound_radio_vars.items():
            if rb.isChecked():
                return val
        return "NONE"

    def get_result(self) -> Condition | None:
        return self._result

    def _center_on_parent(self, parent: QWidget) -> None:
        if parent is None:
            return
        geo = parent.geometry()
        self.move(
            geo.x() + (geo.width() - self.width()) // 2,
            geo.y() + (geo.height() - self.height()) // 2,
        )


def open_condition_dialog(
    parent: QWidget,
    condition: Condition | None,
    title: str,
    on_done,
) -> None:
    """打开条件构建器对话框（与 tkinter 版本签名一致）。"""
    dlg = QtConditionDialog(parent, condition=condition, title=title)
    if dlg.exec() == QDialog.Accepted:
        result = dlg.get_result()
        if result is not None:
            on_done(result)
