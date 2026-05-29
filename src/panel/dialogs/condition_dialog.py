"""条件构建器对话框 — 可视化构建条件表达式"""

import tkinter as tk
from tkinter import ttk, filedialog

from src.core.condition import Condition, ConditionType
from src.panel.canvas.scale import scale_manager
from src.panel.canvas.theme import current_theme
from src.panel.dialogs._dialog_utils import make_dialog
from src.panel.widgets import themed_button, themed_dropdown, themed_entry, themed_frame, themed_label, themed_labelframe, themed_radiobutton, themed_spinbox
from src.utils.i18n import t

# 简单条件类型选项（不含复合类型）
_SIMPLE_CONDITION_OPTIONS = [
    (ct.name, key)
    for ct, key in [
        (ConditionType.IMAGE_FOUND, "dialog.condition_type.image_found"),
        (ConditionType.IMAGE_NOT_FOUND, "dialog.condition_type.image_not_found"),
        (ConditionType.VARIABLE_EXISTS, "dialog.condition_type.variable_exists"),
        (ConditionType.VARIABLE_COMPARE, "dialog.condition_type.variable_compare"),
        (ConditionType.ELAPSED_TIME, "dialog.condition_type.elapsed_time"),
    ]
]

# 比较运算符选项（非 i18n，直接显示符号）
_COMPARE_OP_OPTIONS = [
    ("==", "=="), ("!=", "!="), (">", ">"), ("<", "<"), (">=", ">="), ("<=", "<="),
]



def open_condition_dialog(parent, condition: Condition | None, title: str, on_done):
    """打开条件构建器对话框"""
    th = current_theme()
    if condition is None:
        condition = Condition(condition_type=ConditionType.IMAGE_FOUND)

    dlg = make_dialog(parent, title, 560, 580)
    dlg.resizable(True, True)

    # 主框架（可滚动）
    main = themed_frame(dlg)
    main.pack(fill=tk.BOTH, expand=True, padx=th.pad_sm, pady=th.pad_sm)

    # 条件类型选择
    themed_label(main, text=t("dialog.label.condition_type"), style="body").grid(row=0, column=0, sticky=tk.W, pady=th.pad_xs)
    type_dropdown = themed_dropdown(
        main, options=_SIMPLE_CONDITION_OPTIONS,
        value=condition.condition_type.name, state="readonly", width=28,
        command=lambda _: rebuild_fields(),
    )
    type_dropdown.grid(row=0, column=1, sticky=tk.W, pady=th.pad_xs, padx=th.pad_sm)

    # 动态字段容器
    fields_frame = themed_labelframe(main, text=t("dialog.label.condition_params"))
    fields_frame.grid(row=1, column=0, columnspan=2, sticky=tk.NSEW, pady=th.pad_sm)
    main.rowconfigure(1, weight=1)
    main.columnconfigure(1, weight=1)

    # 变量字典
    var_image = tk.StringVar(value=condition.image_path)
    var_threshold = tk.DoubleVar(value=condition.threshold)
    var_var_name = tk.StringVar(value=condition.variable_name)
    var_compare_op = tk.StringVar(value=condition.compare_op or "==")
    var_compare_x = tk.IntVar(value=condition.compare_value_x)
    var_compare_y = tk.IntVar(value=condition.compare_value_y)
    var_timer_name = tk.StringVar(value=condition.timer_name)
    var_timeout = tk.DoubleVar(value=condition.timeout_seconds)

    # 复合条件子列表
    children_list: list[Condition] = list(condition.children) if condition.children else []

    def _get_selected_type() -> ConditionType:
        val = type_dropdown.get_value()
        if val in ConditionType.__members__:
            return ConditionType[val]
        return ConditionType.IMAGE_FOUND

    def rebuild_fields(*_):
        """根据条件类型重建动态字段"""
        for w in fields_frame.winfo_children():
            w.destroy()

        selected = _get_selected_type()

        r = 0
        if selected in (ConditionType.IMAGE_FOUND, ConditionType.IMAGE_NOT_FOUND):
            _build_image_fields(fields_frame, r, var_image, var_threshold)
        elif selected == ConditionType.VARIABLE_EXISTS:
            _build_var_exists_fields(fields_frame, r, var_var_name)
        elif selected == ConditionType.VARIABLE_COMPARE:
            _build_var_compare_fields(fields_frame, r, var_var_name, var_compare_op, var_compare_x, var_compare_y)
        elif selected == ConditionType.ELAPSED_TIME:
            _build_time_fields(fields_frame, r, var_timer_name, var_timeout)

    rebuild_fields()

    # ── 复合条件区域 ──────────────────────────────────────
    compound_frame = themed_labelframe(main, text=t("dialog.label.compound_condition"))
    compound_frame.grid(row=2, column=0, columnspan=2, sticky=tk.EW, pady=(th.pad_sm, th.pad_xs))

    sm = scale_manager()
    children_lb = tk.Listbox(
        compound_frame, height=3, exportselection=False,
        bg=th.bg_surface, fg=th.text_primary,
        selectbackground=th.accent_blue, selectforeground=th.text_on_accent,
        font=(th.font_family, sm.s(9)), bd=0, activestyle="none",
    )
    children_lb.pack(fill=tk.X, padx=th.pad_xs, pady=th.pad_xs)

    def refresh_children_list():
        children_lb.delete(0, tk.END)
        for c in children_list:
            children_lb.insert(tk.END, c.describe())

    refresh_children_list()

    child_btns = themed_frame(compound_frame)
    child_btns.pack(fill=tk.X, padx=th.pad_xs, pady=th.pad_xs)

    def add_child():
        """添加子条件"""
        child = Condition(condition_type=ConditionType.IMAGE_FOUND)

        def on_child_done(c):
            children_list.append(c)
            refresh_children_list()

        open_condition_dialog(dlg, child, t("dialog.title.add_child_condition"), on_child_done)

    def remove_child():
        sel = children_lb.curselection()
        if sel:
            del children_list[sel[0]]
            refresh_children_list()

    themed_button(child_btns, text=t("dialog.btn.add_child"), command=add_child).pack(side=tk.LEFT, padx=th.pad_xs)
    themed_button(child_btns, text=t("dialog.btn.remove_child"), command=remove_child).pack(side=tk.LEFT, padx=th.pad_xs)

    # 复合类型选择
    compound_row = themed_frame(main)
    compound_row.grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=th.pad_xs)
    var_compound = tk.StringVar(value="NONE")
    themed_label(compound_row, text=t("dialog.label.compound_mode")).pack(side=tk.LEFT)
    for text, val in [
        (t("dialog.compound_mode.none"), "NONE"),
        (t("dialog.compound_mode.and"), ConditionType.COMPOUND_AND.name),
        (t("dialog.compound_mode.or"), ConditionType.COMPOUND_OR.name),
        (t("dialog.compound_mode.not"), ConditionType.COMPOUND_NOT.name),
    ]:
        themed_radiobutton(compound_row, text=text, variable=var_compound, value=val).pack(side=tk.LEFT, padx=th.pad_xs)

    # ── 按钮 ──────────────────────────────────────────────
    btn_frame = themed_frame(main)
    btn_frame.grid(row=4, column=0, columnspan=2, pady=th.pad_sm)

    def on_ok():
        compound_mode = var_compound.get()
        if compound_mode != "NONE" and children_list:
            ct = ConditionType[compound_mode] if compound_mode in ConditionType.__members__ else ConditionType.COMPOUND_AND
            result = Condition(condition_type=ct, children=list(children_list))
        else:
            result = Condition(
                condition_type=_get_selected_type(),
                image_path=var_image.get().strip(),
                threshold=var_threshold.get(),
                variable_name=var_var_name.get().strip(),
                compare_op=var_compare_op.get(),
                compare_value_x=var_compare_x.get(),
                compare_value_y=var_compare_y.get(),
                timer_name=var_timer_name.get().strip(),
                timeout_seconds=var_timeout.get(),
            )
        dlg.destroy()
        on_done(result)

    themed_button(btn_frame, text=t("common.ok"), command=on_ok, width=10).pack(side=tk.LEFT, padx=th.pad_sm)
    themed_button(btn_frame, text=t("common.cancel"), command=dlg.destroy, width=10).pack(side=tk.LEFT, padx=th.pad_sm)


# ── 动态字段构建器 ──────────────────────────────────────────

def _build_image_fields(parent, start_row, var_image, var_threshold):
    """图片检测条件字段"""
    th = current_theme()
    themed_label(parent, text=t("dialog.label.image_path")).grid(row=start_row, column=0, sticky=tk.W, padx=th.pad_sm, pady=th.pad_xs)
    img_frame = themed_frame(parent)
    img_frame.grid(row=start_row, column=1, sticky=tk.EW, padx=th.pad_sm, pady=th.pad_xs)
    themed_entry(img_frame, textvariable=var_image, width=30).pack(side=tk.LEFT, fill=tk.X, expand=True)
    themed_button(img_frame, text=t("dialog.btn.browse"), command=lambda: _browse_cond_image(var_image)).pack(side=tk.LEFT, padx=(th.pad_xs, 0))

    themed_label(parent, text=t("dialog.label.match_threshold")).grid(row=start_row + 1, column=0, sticky=tk.W, padx=th.pad_sm, pady=th.pad_xs)
    thresh_frame = themed_frame(parent)
    thresh_frame.grid(row=start_row + 1, column=1, sticky=tk.W, padx=th.pad_sm, pady=th.pad_xs)
    ttk.Scale(thresh_frame, from_=0.5, to=1.0, variable=var_threshold,
              orient=tk.HORIZONTAL, length=180).pack(side=tk.LEFT)
    themed_label(thresh_frame, textvariable=var_threshold, width=5).pack(side=tk.LEFT, padx=th.pad_xs)

    parent.columnconfigure(1, weight=1)


def _build_var_exists_fields(parent, start_row, var_name):
    """变量存在条件字段"""
    th = current_theme()
    themed_label(parent, text=t("dialog.label.variable_name")).grid(row=start_row, column=0, sticky=tk.W, padx=th.pad_sm, pady=th.pad_xs)
    themed_entry(parent, textvariable=var_name, width=24).grid(
        row=start_row, column=1, sticky=tk.W, padx=th.pad_sm, pady=th.pad_xs
    )
    themed_label(parent, text=t("dialog.hint.set_by_output_coord"), fg=th.text_muted).grid(
        row=start_row + 1, column=0, columnspan=2, sticky=tk.W, padx=th.pad_sm
    )


def _build_var_compare_fields(parent, start_row, var_name, var_op, var_x, var_y):
    """变量比较条件字段"""
    th = current_theme()
    themed_label(parent, text=t("dialog.label.variable_name")).grid(row=start_row, column=0, sticky=tk.W, padx=th.pad_sm, pady=th.pad_xs)
    themed_entry(parent, textvariable=var_name, width=16).grid(
        row=start_row, column=1, sticky=tk.W, padx=th.pad_sm, pady=th.pad_xs
    )

    themed_label(parent, text=t("dialog.label.compare_operator")).grid(row=start_row + 1, column=0, sticky=tk.W, padx=th.pad_sm, pady=th.pad_xs)
    op_dropdown = themed_dropdown(
        parent, options=_COMPARE_OP_OPTIONS,
        value=var_op.get(), state="readonly", width=6,
        i18n=False, command=lambda v: var_op.set(v),
    )
    op_dropdown.grid(row=start_row + 1, column=1, sticky=tk.W, padx=th.pad_sm, pady=th.pad_xs)

    themed_label(parent, text=t("dialog.label.target_value_x")).grid(row=start_row + 2, column=0, sticky=tk.W, padx=th.pad_sm, pady=th.pad_xs)
    themed_spinbox(parent, from_=-9999, to=9999, textvariable=var_x, width=8).grid(
        row=start_row + 2, column=1, sticky=tk.W, padx=th.pad_sm, pady=th.pad_xs
    )

    themed_label(parent, text=t("dialog.label.target_value_y")).grid(row=start_row + 3, column=0, sticky=tk.W, padx=th.pad_sm, pady=th.pad_xs)
    themed_spinbox(parent, from_=-9999, to=9999, textvariable=var_y, width=8).grid(
        row=start_row + 3, column=1, sticky=tk.W, padx=th.pad_sm, pady=th.pad_xs
    )


def _build_time_fields(parent, start_row, var_timer, var_timeout):
    """经过时间条件字段"""
    th = current_theme()
    themed_label(parent, text=t("dialog.label.timer_name")).grid(row=start_row, column=0, sticky=tk.W, padx=th.pad_sm, pady=th.pad_xs)
    themed_entry(parent, textvariable=var_timer, width=16).grid(
        row=start_row, column=1, sticky=tk.W, padx=th.pad_sm, pady=th.pad_xs
    )

    themed_label(parent, text=t("dialog.label.timeout_seconds")).grid(row=start_row + 1, column=0, sticky=tk.W, padx=th.pad_sm, pady=th.pad_xs)
    themed_spinbox(parent, from_=0.1, to=3600.0, increment=0.5,
                textvariable=var_timeout, width=10).grid(
        row=start_row + 1, column=1, sticky=tk.W, padx=th.pad_sm, pady=th.pad_xs
    )

    themed_label(parent, text=t("dialog.hint.need_timer_step"), fg=th.text_muted).grid(
        row=start_row + 2, column=0, columnspan=2, sticky=tk.W, padx=th.pad_sm
    )


def _browse_cond_image(var: tk.StringVar) -> None:
    """浏览选择条件图片"""
    import os
    from src.utils.paths import get_assets_dir
    assets = get_assets_dir()
    initial_dir = assets if os.path.isdir(assets) else os.path.expanduser("~")
    path = filedialog.askopenfilename(
        title=t("dialog.title.select_condition_image"),
        initialdir=initial_dir,
        filetypes=[(t("dialog.filetype.image_files"), "*.png *.jpg *.jpeg *.bmp"), (t("dialog.filetype.all"), "*.*")],
    )
    if path:
        var.set(path)
