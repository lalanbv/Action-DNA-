"""监控器配置对话框 — 配置后台弹窗检测与处理"""

import os

import tkinter as tk
from tkinter import ttk, filedialog

from src.core.action import FoundAction
from src.core.monitor import MonitorConfig
from src.panel.canvas.theme import current_theme
from src.panel.dialogs._dialog_utils import make_dialog
from src.panel.dialogs.click_image_dialog import _FOUND_ACTION_OPTIONS
from src.utils.paths import get_assets_dir
from src.panel.widgets import themed_button, themed_checkbutton, themed_dropdown, themed_entry, themed_frame, themed_label, themed_separator, themed_spinbox
from src.utils.i18n import t

# 处理动作选项（排除 OUTPUT_COORD，监控器不需要输出坐标）
_MONITOR_ACTION_OPTIONS = [
    (val, key) for val, key in _FOUND_ACTION_OPTIONS
    if val != FoundAction.OUTPUT_COORD.name
]


def open_monitor_dialog(parent, monitor: MonitorConfig, title: str, on_done):
    """打开监控器配置对话框"""
    th = current_theme()
    dlg = make_dialog(parent, title, 500, 520)

    # 配置变量
    var_name = tk.StringVar(value=monitor.name)
    var_enabled = tk.BooleanVar(value=monitor.enabled)
    var_image = tk.StringVar(value=monitor.image_path)
    var_threshold = tk.DoubleVar(value=monitor.threshold)
    var_interval = tk.DoubleVar(value=monitor.check_interval)
    var_handler_action = tk.StringVar(value=monitor.handler_action.value)
    var_handler_image = tk.StringVar(value=monitor.handler_image_path)
    var_max_consecutive = tk.IntVar(value=monitor.max_consecutive)
    var_cooldown = tk.DoubleVar(value=monitor.cooldown)

    row = 0

    # 名称
    themed_label(dlg, text=t("dialog.label.monitor_name")).grid(row=row, column=0, sticky=tk.W, padx=th.pad_sm, pady=th.pad_xs)
    themed_entry(dlg, textvariable=var_name, width=30).grid(row=row, column=1, padx=th.pad_sm, pady=th.pad_xs)
    row += 1

    # 启用
    themed_checkbutton(dlg, text=t("common.enabled"), variable=var_enabled).grid(
        row=row, column=0, columnspan=2, sticky=tk.W, padx=th.pad_sm, pady=th.pad_xs
    )
    row += 1

    themed_separator(dlg).grid(
        row=row, column=0, columnspan=2, sticky=tk.EW, padx=th.pad_sm, pady=th.pad_xs
    )
    row += 1

    # ── 检测配置 ──────────────────────────────────────────
    themed_label(dlg, text=t("dialog.label.detection_config"), style="body").grid(
        row=row, column=0, columnspan=2, sticky=tk.W, padx=th.pad_sm, pady=(th.pad_xs, 0)
    )
    row += 1

    # 检测图片
    themed_label(dlg, text=t("dialog.label.detect_image")).grid(row=row, column=0, sticky=tk.W, padx=th.pad_sm, pady=th.pad_xs)
    img_frame = themed_frame(dlg)
    img_frame.grid(row=row, column=1, padx=th.pad_sm, pady=th.pad_xs, sticky=tk.EW)
    themed_entry(img_frame, textvariable=var_image, width=22).pack(side=tk.LEFT, fill=tk.X, expand=True)
    themed_button(img_frame, text=t("dialog.btn.browse"), command=lambda: _browse_image(var_image)).pack(side=tk.LEFT, padx=(th.pad_xs, 0))
    row += 1

    # 阈值
    themed_label(dlg, text=t("dialog.label.match_threshold")).grid(row=row, column=0, sticky=tk.W, padx=th.pad_sm, pady=th.pad_xs)
    threshold_frame = themed_frame(dlg)
    threshold_frame.grid(row=row, column=1, padx=th.pad_sm, pady=th.pad_xs, sticky=tk.W)
    ttk.Scale(threshold_frame, from_=0.5, to=1.0, variable=var_threshold,
              orient=tk.HORIZONTAL, length=150).pack(side=tk.LEFT)
    var_threshold_display = tk.StringVar(value=f"{var_threshold.get():.2f}")

    def _format_threshold(*_):
        try:
            var_threshold_display.set(f"{var_threshold.get():.2f}")
        except tk.TclError:
            pass

    var_threshold.trace_add("write", _format_threshold)
    themed_label(threshold_frame, textvariable=var_threshold_display, width=4).pack(side=tk.LEFT, padx=th.pad_xs)
    row += 1

    # 检测间隔
    themed_label(dlg, text=t("dialog.label.detect_interval")).grid(row=row, column=0, sticky=tk.W, padx=th.pad_sm, pady=th.pad_xs)
    themed_spinbox(dlg, from_=0.5, to=30.0, increment=0.5,
                textvariable=var_interval, width=8).grid(row=row, column=1, sticky=tk.W, padx=th.pad_sm, pady=th.pad_xs)
    row += 1

    themed_separator(dlg).grid(
        row=row, column=0, columnspan=2, sticky=tk.EW, padx=th.pad_sm, pady=th.pad_xs
    )
    row += 1

    # ── 处理配置 ──────────────────────────────────────────
    themed_label(dlg, text=t("dialog.label.handler_config"), style="body").grid(
        row=row, column=0, columnspan=2, sticky=tk.W, padx=th.pad_sm, pady=(th.pad_xs, 0)
    )
    row += 1

    # 处理动作
    themed_label(dlg, text=t("dialog.label.handler_action")).grid(row=row, column=0, sticky=tk.W, padx=th.pad_sm, pady=th.pad_xs)
    handler_dropdown = themed_dropdown(
        dlg, options=_MONITOR_ACTION_OPTIONS,
        value=monitor.handler_action.name,
        state="readonly", width=16,
    )
    handler_dropdown.grid(row=row, column=1, sticky=tk.W, padx=th.pad_sm, pady=th.pad_xs)
    row += 1

    # 处理目标图片
    themed_label(dlg, text=t("dialog.label.handler_target_image")).grid(row=row, column=0, sticky=tk.W, padx=th.pad_sm, pady=th.pad_xs)
    himg_frame = themed_frame(dlg)
    himg_frame.grid(row=row, column=1, padx=th.pad_sm, pady=th.pad_xs, sticky=tk.EW)
    themed_entry(himg_frame, textvariable=var_handler_image, width=22).pack(side=tk.LEFT, fill=tk.X, expand=True)
    themed_button(himg_frame, text=t("dialog.btn.browse"), command=lambda: _browse_image(var_handler_image)).pack(side=tk.LEFT, padx=(th.pad_xs, 0))
    row += 1

    themed_label(dlg, text=t("dialog.hint.optional_handler_image")).grid(
        row=row, column=0, columnspan=2, sticky=tk.W, padx=th.pad_sm
    )
    row += 1

    themed_separator(dlg).grid(
        row=row, column=0, columnspan=2, sticky=tk.EW, padx=th.pad_sm, pady=th.pad_xs
    )
    row += 1

    # ── 限制配置 ──────────────────────────────────────────
    themed_label(dlg, text=t("dialog.label.max_consecutive")).grid(row=row, column=0, sticky=tk.W, padx=th.pad_sm, pady=th.pad_xs)
    themed_spinbox(dlg, from_=1, to=20, textvariable=var_max_consecutive,
                width=8).grid(row=row, column=1, sticky=tk.W, padx=th.pad_sm, pady=th.pad_xs)
    row += 1

    themed_label(dlg, text=t("dialog.label.trigger_cooldown")).grid(row=row, column=0, sticky=tk.W, padx=th.pad_sm, pady=th.pad_xs)
    themed_spinbox(dlg, from_=0.5, to=60.0, increment=0.5,
                textvariable=var_cooldown, width=8).grid(row=row, column=1, sticky=tk.W, padx=th.pad_sm, pady=th.pad_xs)
    row += 1

    # ── 按钮 ──────────────────────────────────────────────
    btn_frame = themed_frame(dlg)
    btn_frame.grid(row=row, column=0, columnspan=2, pady=th.pad_lg)

    def on_ok():
        # 将显示值转换回 FoundAction 枚举
        handler_val = handler_dropdown.get_value()
        handler_action = FoundAction[handler_val] if handler_val in FoundAction.__members__ else FoundAction.LEFT_CLICK

        result = MonitorConfig(
            name=var_name.get().strip() or t("common.unnamed_monitor"),
            enabled=var_enabled.get(),
            image_path=var_image.get().strip(),
            threshold=var_threshold.get(),
            check_interval=var_interval.get(),
            handler_action=handler_action,
            handler_image_path=var_handler_image.get().strip(),
            max_consecutive=var_max_consecutive.get(),
            cooldown=var_cooldown.get(),
        )
        dlg.destroy()
        on_done(result)

    themed_button(btn_frame, text=t("common.ok"), command=on_ok, width=10).pack(side=tk.LEFT, padx=th.pad_sm)
    themed_button(btn_frame, text=t("common.cancel"), command=dlg.destroy, width=10).pack(side=tk.LEFT, padx=th.pad_sm)

    dlg.columnconfigure(1, weight=1)


def _browse_image(var: tk.StringVar) -> None:
    """浏览选择图片文件"""
    initial_dir = get_assets_dir() if os.path.isdir(get_assets_dir()) else os.path.expanduser("~")
    path = filedialog.askopenfilename(
        title=t("dialog.title.select_image"),
        initialdir=initial_dir,
        filetypes=[(t("dialog.filetype.image_files"), "*.png *.jpg *.jpeg *.bmp"), (t("dialog.filetype.all"), "*.*")],
    )
    if path:
        var.set(path)
