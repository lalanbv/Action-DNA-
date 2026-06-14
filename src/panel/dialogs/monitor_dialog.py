"""监控器配置对话框 — 配置后台弹窗检测与处理"""

import os

import tkinter as tk
from tkinter import ttk, filedialog

from src.core.action import FoundAction, MatchStrategy, ThresholdMode
from src.core.monitor import MonitorConfig
from src.panel.canvas.theme import current_theme
from src.panel.dialogs._dialog_utils import make_dialog
from src.panel.dialogs.click_image_dialog import _FOUND_ACTION_OPTIONS
from src.panel.dialogs.multi_template_editor import MultiTemplateEditor
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

    # 配置变量(图片/阈值由多模板编辑器管理,此处只留其余字段)
    var_name = tk.StringVar(value=monitor.name)
    var_enabled = tk.BooleanVar(value=monitor.enabled)
    var_interval = tk.DoubleVar(value=monitor.check_interval)
    var_handler_action = tk.StringVar(value=monitor.handler_action.value)
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

    # 触发图多模板管理器(完整:含阈值模式/策略/全局阈值)
    trigger_editor = MultiTemplateEditor(dlg, on_change=None)
    trigger_editor.set_state(
        monitor.image_path, monitor.alt_image_paths, monitor.alt_thresholds,
        monitor.threshold_mode, monitor.match_strategy, monitor.threshold,
    )
    trigger_editor.frame.grid(row=row, column=0, columnspan=2, sticky=tk.EW, padx=th.pad_sm, pady=th.pad_xs)
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

    # 处理图多模板管理器(精简:不显示模式/策略/全局阈值,共用触发图的)
    handler_editor = MultiTemplateEditor(dlg, on_change=None, show_match_settings=False)
    handler_editor.set_state(
        monitor.handler_image_path, monitor.alt_handler_image_paths,
        monitor.alt_handler_thresholds,
        monitor.threshold_mode, monitor.match_strategy, monitor.threshold,
    )
    handler_editor.frame.grid(row=row, column=0, columnspan=2, sticky=tk.EW, padx=th.pad_sm, pady=th.pad_xs)
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
        # 触发图状态(完整编辑器:含 mode/strategy/threshold)
        (t_path, t_alts, t_thr, mode, strategy, threshold) = trigger_editor.get_state()
        # 处理图状态(精简编辑器;mode/strategy 忽略,共用触发图的)
        (h_path, h_alts, h_thr, _h_mode, _h_strategy, _h_gthr) = handler_editor.get_state()
        # 处理动作
        handler_val = handler_dropdown.get_value()
        handler_action = FoundAction[handler_val] if handler_val in FoundAction.__members__ else FoundAction.LEFT_CLICK

        result = MonitorConfig(
            name=var_name.get().strip() or t("common.unnamed_monitor"),
            enabled=var_enabled.get(),
            image_path=t_path.strip(),
            threshold=threshold,
            check_interval=var_interval.get(),
            handler_action=handler_action,
            handler_image_path=h_path.strip(),
            max_consecutive=var_max_consecutive.get(),
            cooldown=var_cooldown.get(),
            alt_image_paths=t_alts,
            alt_thresholds=t_thr,
            alt_handler_image_paths=h_alts,
            alt_handler_thresholds=h_thr,
            match_strategy=strategy,
            threshold_mode=mode,
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
