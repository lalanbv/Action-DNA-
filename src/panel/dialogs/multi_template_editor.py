"""多模板图片管理器(tkinter 可复用组件)。

ClickImage / Condition / Monitor 对话框共用。规格与 Qt 版一致:
- 主图置顶、不可删;备用图可增删、上下移动
- 每行:缩略图 + 路径 + 阈值单元(spinbox + 自定义复选框) + 排序 + 删除
- 阈值模式联动:PER_TEMPLATE 显示阈值单元;AUTO 隐藏全局阈值与每行单元;GLOBAL 显示全局阈值
"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import filedialog
from typing import Callable

from src.core.action import MatchStrategy, ThresholdMode
from src.panel.canvas.theme import current_theme
from src.panel.widgets import themed_button, themed_dropdown, themed_frame, themed_label
from src.utils.i18n import t

try:
    from PIL import Image, ImageTk
except ImportError:  # pragma: no cover - PIL 可选
    Image = None  # type: ignore[assignment,misc]
    ImageTk = None  # type: ignore[assignment]


_THRESHOLD_MODE_OPTIONS = [
    (ThresholdMode.AUTO.name, "dialog.threshold_mode.auto"),
    (ThresholdMode.GLOBAL.name, "dialog.threshold_mode.global"),
    (ThresholdMode.PER_TEMPLATE.name, "dialog.threshold_mode.per_template"),
]

_MATCH_STRATEGY_OPTIONS = [
    (MatchStrategy.ADAPTIVE.name, "dialog.match_strategy.adaptive"),
    (MatchStrategy.FIRST_MATCH.name, "dialog.match_strategy.first_match"),
    (MatchStrategy.BEST_CONFIDENCE.name, "dialog.match_strategy.best_confidence"),
]


class MultiTemplateEditor:
    """tkinter 多模板图片管理器。

    持有一个 frame 与内部状态。用法:
        editor = MultiTemplateEditor(parent_frame)
        editor.set_state(image_path, alt_paths, alt_thresholds, mode, strategy, gthr)
        ...
        state = editor.get_state()  # → (image_path, alts, thr, mode, strategy, gthr)
    """

    def __init__(
        self,
        parent: tk.Widget,
        on_change: Callable[[], None] | None = None,
        show_match_settings: bool = True,
    ) -> None:
        self._th = current_theme()
        self._on_change = on_change
        self._show_match_settings = show_match_settings
        self._frame = themed_frame(parent)
        self._rows: list[dict] = []
        self._photo_refs: list[object] = []
        self._primary_path_var = tk.StringVar()
        self._global_thr_var = tk.DoubleVar(value=0.8)
        # 统一状态源:StringVar 永远存在;控件(show_match_settings=True)只是其视图
        self._threshold_mode_var = tk.StringVar(value=ThresholdMode.GLOBAL.name)
        self._match_strategy_var = tk.StringVar(value=MatchStrategy.ADAPTIVE.name)
        # 控件引用(精简模式下保持 None,_apply_mode_visibility 据此守卫)
        self._mode_dd = None
        self._strategy_dd = None
        self._global_thr_label = None
        self._global_thr_sb = None
        if show_match_settings:
            self._build_controls()
        self._rows_frame = themed_frame(self._frame)
        self._rows_frame.pack(fill=tk.X)
        self._build_add_bar()
        self._render_rows()

    @property
    def frame(self) -> tk.Widget:
        return self._frame

    # ---- 控制区 ----

    def _build_controls(self) -> None:
        th = self._th
        ctrl = themed_frame(self._frame)
        ctrl.pack(fill=tk.X, pady=th.pad_xs)

        themed_label(ctrl, text=t("dialog.label.threshold_mode")).grid(
            row=0, column=0, sticky=tk.W, padx=th.pad_xs,
        )
        self._mode_dd = themed_dropdown(
            ctrl, options=_THRESHOLD_MODE_OPTIONS,
            value=self._threshold_mode_var.get(), state="readonly", width=20,
            command=lambda _v: (self._threshold_mode_var.set(_v), self._on_mode_changed()),
        )
        self._mode_dd.grid(row=0, column=1, sticky=tk.W, padx=th.pad_xs)

        themed_label(ctrl, text=t("dialog.label.match_strategy")).grid(
            row=1, column=0, sticky=tk.W, padx=th.pad_xs,
        )
        self._strategy_dd = themed_dropdown(
            ctrl, options=_MATCH_STRATEGY_OPTIONS,
            value=self._match_strategy_var.get(), state="readonly", width=20,
            command=lambda _v: self._match_strategy_var.set(_v),
        )
        self._strategy_dd.grid(row=1, column=1, sticky=tk.W, padx=th.pad_xs)

        self._global_thr_label = themed_label(ctrl, text=t("dialog.label.global_threshold"))
        self._global_thr_sb = tk.Spinbox(
            ctrl, from_=0.1, to=1.0, increment=0.05,
            textvariable=self._global_thr_var, width=6,
        )
        self._global_thr_label.grid(row=2, column=0, sticky=tk.W, padx=th.pad_xs)
        self._global_thr_sb.grid(row=2, column=1, sticky=tk.W, padx=th.pad_xs)

    def _build_add_bar(self) -> None:
        th = self._th
        bar = themed_frame(self._frame)
        bar.pack(fill=tk.X)
        themed_button(bar, text=t("dialog.multi_template.add"), command=self._add_alt).pack(side=tk.LEFT)
        themed_label(
            bar, text="  " + t("dialog.multi_template.hint_order"), fg=th.text_muted,
        ).pack(side=tk.LEFT)

    # ---- 模式联动 ----

    def _current_mode_name(self) -> str:
        return self._threshold_mode_var.get()

    def _apply_mode_visibility(self) -> None:
        mode = self._current_mode_name()
        show_global = mode != ThresholdMode.AUTO.name
        # 全局阈值框仅在控制区渲染时存在(精简模式跳过)
        if self._global_thr_label is not None and self._global_thr_sb is not None:
            if show_global:
                self._global_thr_label.grid()
                self._global_thr_sb.grid()
            else:
                self._global_thr_label.grid_remove()
                self._global_thr_sb.grid_remove()
        # 每行阈值单元的显隐由 _render_rows 按模式重建(避免 pack/grid 混用)

    def _on_mode_changed(self) -> None:
        # 模式切换 → 重渲染行(阈值单元按新模式 pack),全局框由 _apply_mode_visibility 处理
        self._render_rows()
        if self._on_change:
            self._on_change()

    # ---- 行渲染 ----

    def _render_rows(self) -> None:
        for w in self._rows_frame.winfo_children():
            w.destroy()
        self._photo_refs.clear()
        th = self._th
        # 主图行(置顶、不可删)
        self._render_primary_row(th)
        # 备用图行
        for idx, row in enumerate(self._rows):
            self._render_alt_row(idx, row, th)
        self._apply_mode_visibility()

    def _render_primary_row(self, th) -> None:
        row_frame = themed_frame(self._rows_frame)
        row_frame.pack(fill=tk.X, padx=th.pad_xs, pady=2)
        self._render_thumbnail(row_frame, self._primary_path_var.get())
        themed_label(row_frame, text=t("dialog.multi_template.primary")).pack(side=tk.LEFT, padx=th.pad_xs)
        tk.Entry(row_frame, textvariable=self._primary_path_var, width=26).pack(side=tk.LEFT, fill=tk.X, expand=True)
        themed_button(row_frame, text=t("dialog.btn.select_image"), command=self._browse_primary).pack(side=tk.LEFT)

    def _render_alt_row(self, idx: int, row: dict, th) -> None:
        row_frame = themed_frame(self._rows_frame)
        row_frame.pack(fill=tk.X, padx=th.pad_xs, pady=2)
        self._render_thumbnail(row_frame, row["path_var"].get())
        themed_label(row_frame, text=t("dialog.multi_template.alt", n=idx + 1)).pack(side=tk.LEFT, padx=th.pad_xs)
        tk.Entry(row_frame, textvariable=row["path_var"], width=26).pack(side=tk.LEFT, fill=tk.X, expand=True)
        thr_frame = themed_frame(row_frame)
        row["thr_frame"] = thr_frame
        # 阈值单元仅在 PER_TEMPLATE 模式 pack(避免 pack/grid 混用;模式切换时重渲染)
        if self._current_mode_name() == ThresholdMode.PER_TEMPLATE.name:
            thr_frame.pack(side=tk.LEFT, padx=th.pad_xs)
        tk.Checkbutton(
            thr_frame, text=t("dialog.multi_template.custom_threshold"),
            variable=row["custom_var"],
        ).pack(side=tk.LEFT)
        tk.Spinbox(
            thr_frame, from_=0.1, to=1.0, increment=0.05,
            textvariable=row["thr_var"], width=5,
        ).pack(side=tk.LEFT)
        themed_button(row_frame, text="↑", width=2, command=lambda i=idx: self._move(i, -1)).pack(side=tk.LEFT)
        themed_button(row_frame, text="↓", width=2, command=lambda i=idx: self._move(i, 1)).pack(side=tk.LEFT)
        themed_button(
            row_frame, text=t("dialog.multi_template.delete"), command=lambda i=idx: self._delete(i),
        ).pack(side=tk.LEFT)

    def _render_thumbnail(self, parent: tk.Widget, path: str) -> None:
        lbl = themed_label(parent, text=t("dialog.multi_template.no_preview"))
        lbl.pack(side=tk.LEFT)
        if not path or not os.path.exists(path) or Image is None:
            return
        try:
            img = Image.open(path)
            img.thumbnail((40, 40))
            photo = ImageTk.PhotoImage(img)
            self._photo_refs.append(photo)
            lbl.configure(image=photo, text="")
        except (OSError, ValueError):
            pass

    # ---- 操作 ----

    def _browse_primary(self) -> None:
        p = self._pick_image(t("dialog.title.select_template_image"))
        if p:
            self._primary_path_var.set(p)
            self._render_rows()
            self._notify()

    def _add_alt(self) -> None:
        p = self._pick_image(t("dialog.multi_template.add"))
        if p:
            self._rows.append(self._make_row(p, None))
            self._render_rows()
            self._notify()

    def _pick_image(self, title: str) -> str:
        return filedialog.askopenfilename(
            title=title,
            filetypes=[
                (t("dialog.filetype.image"), "*.png *.jpg *.jpeg *.bmp"),
                (t("dialog.filetype.all"), "*.*"),
            ],
        ) or ""

    def _make_row(self, path: str, threshold: float | None) -> dict:
        return {
            "path_var": tk.StringVar(value=path),
            "custom_var": tk.BooleanVar(value=threshold is not None),
            "thr_var": tk.DoubleVar(value=threshold if threshold is not None else 0.8),
            "thr_frame": None,
        }

    def _move(self, idx: int, delta: int) -> None:
        new = idx + delta
        if 0 <= new < len(self._rows):
            self._rows[idx], self._rows[new] = self._rows[new], self._rows[idx]
            self._render_rows()
            self._notify()

    def _delete(self, idx: int) -> None:
        if 0 <= idx < len(self._rows):
            del self._rows[idx]
            self._render_rows()
            self._notify()

    def _notify(self) -> None:
        if self._on_change:
            self._on_change()

    # ---- 状态读写 ----

    def set_state(
        self,
        image_path: str,
        alt_paths: list[str],
        alt_thresholds: list[float | None],
        mode: ThresholdMode,
        strategy: MatchStrategy,
        global_threshold: float,
    ) -> None:
        self._primary_path_var.set(image_path)
        self._rows = [
            self._make_row(p, alt_thresholds[i] if i < len(alt_thresholds) else None)
            for i, p in enumerate(alt_paths)
        ]
        self._threshold_mode_var.set(mode.name)
        self._match_strategy_var.set(strategy.name)
        self._global_thr_var.set(global_threshold)
        # 控件视图同步(精简模式下控件不存在,跳过)
        if self._mode_dd is not None:
            self._mode_dd.set_value(mode.name)
        if self._strategy_dd is not None:
            self._strategy_dd.set_value(strategy.name)
        self._render_rows()

    def get_state(self) -> tuple[str, list[str], list[float | None], ThresholdMode, MatchStrategy, float]:
        """返回 (image_path, alt_paths, alt_thresholds, mode, strategy, global_threshold)。

        alt_thresholds[i]:custom 勾选 → thr_var 值;未勾选 → None(继承)。
        """
        alt_paths = [r["path_var"].get() for r in self._rows]
        alt_thresholds: list[float | None] = []
        for r in self._rows:
            if r["custom_var"].get():
                try:
                    alt_thresholds.append(float(r["thr_var"].get()))
                except (tk.TclError, ValueError):
                    alt_thresholds.append(None)
            else:
                alt_thresholds.append(None)
        mode_name = self._threshold_mode_var.get()
        strategy_name = self._match_strategy_var.get()
        mode = ThresholdMode[mode_name] if mode_name in ThresholdMode.__members__ else ThresholdMode.GLOBAL
        strategy = MatchStrategy[strategy_name] if strategy_name in MatchStrategy.__members__ else MatchStrategy.ADAPTIVE
        try:
            gthr = float(self._global_thr_var.get())
        except (tk.TclError, ValueError):
            gthr = 0.8
        return self._primary_path_var.get(), alt_paths, alt_thresholds, mode, strategy, gthr
