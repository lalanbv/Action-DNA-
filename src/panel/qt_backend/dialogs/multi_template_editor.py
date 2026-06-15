"""多模板图片管理器(Qt 可复用组件,规格同 tkinter 版)。

API 与 tkinter 版 MultiTemplateEditor 一致:
    set_state(image_path, alt_paths, alt_thresholds, mode, strategy, global_threshold)
    get_state() -> (image_path, alt_paths, alt_thresholds, mode, strategy, global_threshold)

注意:本组件需在安装 PySide6 的环境运行/验证(本项目 venv 当前未装 PySide6)。
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from src.core.action import MatchStrategy, ThresholdMode
from src.utils.i18n import t


class MultiTemplateEditorQt(QWidget):
    """Qt 多模板图片管理器。

    主图置顶不可删;备用图可增删、上下移动;阈值模式联动显隐。
    """

    def __init__(self, parent=None, show_match_settings: bool = True) -> None:
        super().__init__(parent)
        self._rows: list[dict] = []
        self._primary_path = ""
        # 统一状态源(控件只是视图);精简模式下不渲染控件但状态仍可读写
        self._mode = ThresholdMode.GLOBAL
        self._strategy = MatchStrategy.ADAPTIVE
        self._global_threshold = 0.8
        self._show_match_settings = show_match_settings

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if show_match_settings:
            layout.addWidget(self._build_controls())

        # 行容器
        self._rows_layout = QVBoxLayout()
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._rows_layout)

        # 添加按钮 + 提示
        bar = QHBoxLayout()
        add_btn = QPushButton(t("dialog.multi_template.add"))
        add_btn.clicked.connect(self._add_alt)
        bar.addWidget(add_btn)
        bar.addWidget(QLabel(t("dialog.multi_template.hint_order")))
        layout.addLayout(bar)

    def _build_controls(self) -> "QWidget":
        """构建阈值模式/策略/全局阈值控制区(返回容器 QWidget)。"""
        ctrl = QWidget()
        cl = QVBoxLayout(ctrl)
        cl.setContentsMargins(0, 0, 0, 0)
        # 阈值模式
        r1 = QHBoxLayout()
        r1.addWidget(QLabel(t("dialog.label.threshold_mode")))
        self._mode_cb = QComboBox()
        for m, key in [
            (ThresholdMode.AUTO, "dialog.threshold_mode.auto"),
            (ThresholdMode.GLOBAL, "dialog.threshold_mode.global"),
            (ThresholdMode.PER_TEMPLATE, "dialog.threshold_mode.per_template"),
        ]:
            self._mode_cb.addItem(t(key), userData=m)
        self._mode_cb.currentIndexChanged.connect(self._on_mode_changed)
        r1.addWidget(self._mode_cb)
        cl.addLayout(r1)
        # 匹配策略
        r2 = QHBoxLayout()
        r2.addWidget(QLabel(t("dialog.label.match_strategy")))
        self._strategy_cb = QComboBox()
        for s, key in [
            (MatchStrategy.ADAPTIVE, "dialog.match_strategy.adaptive"),
            (MatchStrategy.FIRST_MATCH, "dialog.match_strategy.first_match"),
            (MatchStrategy.BEST_CONFIDENCE, "dialog.match_strategy.best_confidence"),
        ]:
            self._strategy_cb.addItem(t(key), userData=s)
        r2.addWidget(self._strategy_cb)
        cl.addLayout(r2)
        # 全局阈值
        r3 = QHBoxLayout()
        self._global_thr_label = QLabel(t("dialog.label.global_threshold"))
        self._global_thr_sb = QDoubleSpinBox()
        self._global_thr_sb.setRange(0.1, 1.0)
        self._global_thr_sb.setSingleStep(0.05)
        self._global_thr_sb.setDecimals(2)
        self._global_thr_sb.valueChanged.connect(lambda v: setattr(self, "_global_threshold", v))
        r3.addWidget(self._global_thr_label)
        r3.addWidget(self._global_thr_sb)
        cl.addLayout(r3)
        return ctrl

    # ---- 模式联动 ----

    def _on_mode_changed(self) -> None:
        if self._show_match_settings:
            self._mode = self._mode_cb.currentData()
            self._strategy = self._strategy_cb.currentData()
            self._global_threshold = self._global_thr_sb.value()
        self._render_rows()

    def _apply_mode_visibility(self) -> None:
        mode = self._mode
        show_global = mode != ThresholdMode.AUTO
        if self._show_match_settings:
            self._global_thr_label.setVisible(show_global)
            self._global_thr_sb.setVisible(show_global)
        for row in self._rows:
            row["thr_widget"].setVisible(mode == ThresholdMode.PER_TEMPLATE)

    # ---- 行渲染 ----

    def _render_rows(self) -> None:
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._rows_layout.addWidget(self._build_primary_row())
        for idx, row in enumerate(self._rows):
            self._rows_layout.addWidget(self._build_alt_row(idx, row))
        self._apply_mode_visibility()

    def _build_primary_row(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        self._add_thumb(lay, self._primary_path)
        lay.addWidget(QLabel(t("dialog.multi_template.primary")))
        le = QLineEdit(self._primary_path)
        le.editingFinished.connect(lambda: self._set_primary(le.text()))
        lay.addWidget(le)
        browse = QPushButton(t("dialog.btn.select_image"))
        browse.clicked.connect(self._browse_primary)
        lay.addWidget(browse)
        return w

    def _set_primary(self, p: str) -> None:
        self._primary_path = p

    def _browse_primary(self) -> None:
        p, _ = QFileDialog.getOpenFileName(
            self, t("dialog.title.select_template_image"), "",
            f"{t('dialog.filetype.image')} (*.png *.jpg *.jpeg *.bmp);;{t('dialog.filetype.all')} (*.*)",
        )
        if p:
            self._primary_path = p
            self._render_rows()

    def _build_alt_row(self, idx: int, row: dict) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        self._add_thumb(lay, row["path"])
        lay.addWidget(QLabel(t("dialog.multi_template.alt", n=idx + 1)))
        le = QLineEdit(row["path"])
        le.editingFinished.connect(lambda v=le: row.update(path=v.text()))
        lay.addWidget(le)
        # 阈值单元
        thr_w = QWidget()
        tl = QHBoxLayout(thr_w)
        tl.setContentsMargins(0, 0, 0, 0)
        chk = QCheckBox(t("dialog.multi_template.custom_threshold"))
        chk.setChecked(row["custom"])
        chk.toggled.connect(lambda v: row.update(custom=v))
        tl.addWidget(chk)
        sb = QDoubleSpinBox()
        sb.setRange(0.1, 1.0)
        sb.setSingleStep(0.05)
        sb.setDecimals(2)
        sb.setValue(row["thr"])
        sb.valueChanged.connect(lambda v: row.update(thr=v))
        tl.addWidget(sb)
        lay.addWidget(thr_w)
        row["thr_widget"] = thr_w
        up = QPushButton("↑")
        up.clicked.connect(lambda: self._move(idx, -1))
        down = QPushButton("↓")
        down.clicked.connect(lambda: self._move(idx, 1))
        dele = QPushButton(t("dialog.multi_template.delete"))
        dele.clicked.connect(lambda: self._delete(idx))
        lay.addWidget(up)
        lay.addWidget(down)
        lay.addWidget(dele)
        return w

    def _add_thumb(self, layout, path: str) -> None:
        lbl = QLabel(t("dialog.multi_template.no_preview"))
        if path and os.path.exists(path):
            pm = QPixmap(path)
            if not pm.isNull():
                lbl.setPixmap(pm.scaled(40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        layout.addWidget(lbl)

    def _add_alt(self) -> None:
        p, _ = QFileDialog.getOpenFileName(
            self, t("dialog.multi_template.add"), "",
            f"{t('dialog.filetype.image')} (*.png *.jpg *.jpeg *.bmp);;{t('dialog.filetype.all')} (*.*)",
        )
        if p:
            self._rows.append({"path": p, "custom": False, "thr": 0.8})
            self._render_rows()

    def _move(self, idx: int, delta: int) -> None:
        new = idx + delta
        if 0 <= new < len(self._rows):
            self._rows[idx], self._rows[new] = self._rows[new], self._rows[idx]
            self._render_rows()

    def _delete(self, idx: int) -> None:
        if 0 <= idx < len(self._rows):
            del self._rows[idx]
            self._render_rows()

    # ---- 状态读写 ----

    def set_state(self, image_path, alt_paths, alt_thresholds, mode, strategy, global_threshold) -> None:
        self._primary_path = image_path
        self._rows = [
            {
                "path": p,
                "custom": (i < len(alt_thresholds) and alt_thresholds[i] is not None),
                "thr": alt_thresholds[i] if (i < len(alt_thresholds) and alt_thresholds[i] is not None) else 0.8,
            }
            for i, p in enumerate(alt_paths)
        ]
        self._mode = mode
        self._strategy = strategy
        self._global_threshold = global_threshold
        if self._show_match_settings:
            # 程序化设置 combo 时 blockSignals，防止 setCurrentIndex 中途触发
            # _on_mode_changed 用尚未更新的另一 combo 覆盖实例变量
            # （根因：原 mode combo 在 strategy combo 之前 setCurrentIndex，
            #  mode 变更触发 _on_mode_changed 用默认 strategy combo 污染 _strategy）
            for cb in (self._mode_cb, self._strategy_cb):
                cb.blockSignals(True)
            try:
                self._mode_cb.setCurrentIndex(self._mode_cb.findData(mode))
                self._strategy_cb.setCurrentIndex(self._strategy_cb.findData(strategy))
            finally:
                for cb in (self._mode_cb, self._strategy_cb):
                    cb.blockSignals(False)
            self._global_thr_sb.setValue(global_threshold)
        self._render_rows()

    def get_state(self):
        alt_paths = [r["path"] for r in self._rows]
        alt_thresholds = [r["thr"] if r["custom"] else None for r in self._rows]
        return (
            self._primary_path,
            alt_paths,
            alt_thresholds,
            self._mode,
            self._strategy,
            self._global_threshold,
        )
