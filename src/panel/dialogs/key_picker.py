"""KeyPicker — 可复用的按键选择器组件。"""

from __future__ import annotations

import tkinter as tk

from src.panel.canvas.scale import scale_manager
from src.panel.canvas.theme import current_theme
from src.panel.widgets import themed_button, themed_entry, themed_frame
from src.utils.float_utils import safe_float, safe_int
from src.utils.i18n import t
from src.utils.platform import IS_MACOS

KEY_LIST: tuple[str, ...] = (
    "mouse_left", "mouse_middle", "mouse_right",
    "a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m",
    "n", "o", "p", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z",
    "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
    "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12",
    "space", "enter", "return", "tab", "backspace", "delete", "insert",
    "home", "end", "pageup", "pagedown", "escape", "esc",
    "capslock", "numlock", "scrolllock", "printscreen", "pause",
    "up", "down", "left", "right",
    "shift", "shiftleft", "shiftright",
    "ctrl", "ctrlleft", "ctrlright",
    "alt", "altleft", "altright",
    "win", "winleft", "winright", "command", "option",
    "numpad0", "numpad1", "numpad2", "numpad3", "numpad4",
    "numpad5", "numpad6", "numpad7", "numpad8", "numpad9",
    "multiply", "add", "subtract", "decimal", "divide",
    "plus", "minus", "equal", "backslash", "semicolon",
    "quote", "comma", "period", "slash", "grave",
    "bracketleft", "bracketright",
    "volumedown", "volumeup", "volumemute",
    "medianext", "mediaprev", "mediaplay_pause", "mediastop",
    "browserback", "browserforward", "browserrefresh",
    "browserhome", "browsersearch", "browserstop", "browserfavorites",
)

_COMBO_MODIFIERS: frozenset[str] = frozenset({
    "ctrl", "ctrlleft", "ctrlright",
    "shift", "shiftleft", "shiftright",
    "alt", "altleft", "altright",
    "win", "winleft", "winright", "command", "option",
    "capslock",
})

_TK_TO_KEY = {
    "Return": "enter", "Escape": "esc", "BackSpace": "backspace",
    "Tab": "tab", "space": "space",
    "Left": "left", "Right": "right", "Up": "up", "Down": "down",
    "Prior": "pageup", "Next": "pagedown",
    "Home": "home", "End": "end",
    "Insert": "insert", "Delete": "delete",
    "Shift_L": "shiftleft", "Shift_R": "shiftright",
    "Control_L": "ctrlleft", "Control_R": "ctrlright",
    "Alt_L": "altleft", "Alt_R": "altright",
    "Super_L": "command" if IS_MACOS else "winleft",
    "Super_R": "command" if IS_MACOS else "winright",
    "Caps_Lock": "capslock", "Num_Lock": "numlock",
    "Scroll_Lock": "scrolllock",
    "Print": "printscreen", "Pause": "pause",
    **{f"F{i}": f"f{i}" for i in range(1, 13)},
}

_MOUSE_BTN_MAP = (
    {1: "mouse_left", 2: "mouse_right", 3: "mouse_middle"}
    if IS_MACOS else
    {1: "mouse_left", 2: "mouse_middle", 3: "mouse_right"}
)


class SyncedVar:
    """包装 Spinbox 控件，绕开 tkinter Spinbox 手动输入不同步 textvariable 的问题。"""

    def __init__(self, real_var: tk.Variable, spinbox: tk.Spinbox, as_float: bool) -> None:
        self._var = real_var
        self._sb = spinbox
        self._as_float = as_float

    def get(self) -> float | int:
        raw = self._sb.get()
        return safe_float(raw, default=0.0) if self._as_float else safe_int(raw, default=0)

    def set(self, value: float | int) -> None:
        self._var.set(value)

    def trace_add(self, *args: object, **kwargs: object) -> str:
        return self._var.trace_add(*args, **kwargs)  # type: ignore[arg-type]


def make_key_picker(
    parent_frame: tk.Widget,
    initial_value: str = "",
    append_mode: bool = False,
    list_height: int = 6,
) -> tk.StringVar:
    """创建按键选择器（输入框 + 列表 + 监听按钮），返回 StringVar。"""
    v = tk.StringVar(value=initial_value)
    _updating = False

    th = current_theme()
    input_row = themed_frame(parent_frame)
    input_row.pack(side=tk.TOP, fill=tk.X)
    key_entry = themed_entry(input_row, textvariable=v, width=24 if append_mode else 14)
    key_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
    listen_btn_text = t("dialog.btn.listen_combo") if append_mode else t("dialog.btn.listen")
    listen_btn = themed_button(input_row, text=listen_btn_text, width=8)
    listen_btn.pack(side=tk.LEFT, padx=(th.pad_xs, 0))

    list_frame = themed_frame(parent_frame)
    list_frame.pack(side=tk.TOP, fill=tk.BOTH, pady=th.pad_xs)
    sm = scale_manager()
    key_lb = tk.Listbox(
        list_frame, height=list_height, width=18, exportselection=False,
        bg=th.bg_surface, fg=th.text_primary,
        selectbackground=th.accent_blue, selectforeground=th.text_on_accent,
        font=(th.font_family, sm.s(9)), bd=0, activestyle="none",
    )
    key_sb = tk.Scrollbar(list_frame, orient=tk.VERTICAL, command=key_lb.yview)
    key_lb.configure(yscrollcommand=key_sb.set)
    key_lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    key_sb.pack(side=tk.RIGHT, fill=tk.Y)

    _last_keys: list[str] | None = None

    def _populate(keys: list[str] | None = None) -> None:
        nonlocal _last_keys
        new_keys = keys or KEY_LIST
        if new_keys is _last_keys:
            return
        _last_keys = new_keys
        key_lb.delete(0, tk.END)
        for k in new_keys:
            key_lb.insert(tk.END, k)

    def _highlight() -> None:
        cur = v.get().split(",")[-1].strip() if append_mode else v.get()
        if not cur:
            return
        for i in range(key_lb.size()):
            if key_lb.get(i) == cur:
                key_lb.selection_set(i)
                key_lb.see(i)
                break

    _populate()
    _highlight()

    def _set_key(name: str) -> None:
        """统一处理按键赋值：append_mode 追加，否则替换。"""
        nonlocal _updating
        _updating = True
        if append_mode:
            current = v.get()
            v.set(f"{current},{name}" if current else name)
        else:
            v.set(name)
            _populate()
            _highlight()
        _updating = False

    def _set_keys_csv(names: list[str]) -> None:
        """设置逗号分隔的多个按键（组合键监听结果）。"""
        nonlocal _updating
        _updating = True
        if append_mode:
            current = v.get()
            joined = ",".join(names)
            v.set(f"{current},{joined}" if current else joined)
        else:
            v.set(",".join(names))
        _updating = False

    def _on_select(evt: tk.Event) -> None:
        sel = key_lb.curselection()
        if not sel:
            return
        _set_key(key_lb.get(sel[0]))

    key_lb.bind("<<ListboxSelect>>", _on_select)

    def _on_search(*_: object) -> None:
        nonlocal _updating
        if _updating:
            return
        q = v.get().split(",")[-1].strip().lower() if append_mode else v.get().lower()
        filtered = [k for k in KEY_LIST if q in k] if q else KEY_LIST
        _populate(filtered)
        _highlight()

    v.trace_add("write", _on_search)

    _listen_active = False
    _dlg_ref: tk.Toplevel | None = None

    # ── 组合键监听状态 ──
    _combo_keys: list[str] = []
    _combo_held: set[str] = set()
    _combo_finished = False

    def _stop_listen() -> None:
        nonlocal _listen_active, _dlg_ref, _combo_keys, _combo_held, _combo_finished
        _listen_active = False
        listen_btn.config(text=listen_btn_text)
        key_entry.config(state="normal")
        if _dlg_ref:
            _dlg_ref.unbind("<Key>")
            _dlg_ref.unbind("<KeyRelease>")
            _dlg_ref.unbind("<Button-1>")
            _dlg_ref.unbind("<Button-2>")
            _dlg_ref.unbind("<Button-3>")
        _combo_keys = []
        _combo_held = set()
        _combo_finished = False

    def _finish_combo() -> None:
        """组合键捕获完成，写入结果并停止监听。"""
        nonlocal _combo_finished
        if _combo_finished:
            return
        _combo_finished = True
        if _combo_keys:
            _set_keys_csv(_combo_keys)
        _stop_listen()

    def _on_combo_key_down(evt: tk.Event) -> str:
        nonlocal _combo_finished
        if not _listen_active or _combo_finished:
            return ""
        if evt.keysym == "Escape":
            _stop_listen()
            return "break"

        name = _TK_TO_KEY.get(evt.keysym, evt.keysym.lower())
        _combo_held.add(name)

        if name in _COMBO_MODIFIERS:
            # 修饰键按下 → 追加（去重），继续监听
            if name not in _combo_keys:
                _combo_keys.append(name)
            # 更新预览
            _updating = True
            preview = ",".join(_combo_keys)
            if append_mode:
                current = v.get()
                base = current.rsplit(",", 1)[0] if "," in current else ""
                v.set(f"{base},{preview}" if base else preview)
            else:
                v.set(preview)
            _updating = False
        else:
            # 非修饰键按下 → 追加并立即完成
            _combo_keys.append(name)
            _finish_combo()

        return "break"

    def _on_combo_key_up(evt: tk.Event) -> str:
        if not _listen_active or _combo_finished:
            return ""

        name = _TK_TO_KEY.get(evt.keysym, evt.keysym.lower())
        _combo_held.discard(name)

        # 所有键都松开且有收集到按键 → 完成
        if not _combo_held and _combo_keys:
            _finish_combo()

        return "break"

    def _on_listen_key(evt: tk.Event) -> str:
        """单键监听（append_mode=False）。"""
        nonlocal _listen_active
        if not _listen_active:
            return ""
        if evt.keysym == "Escape":
            _stop_listen()
            return "break"
        name = _TK_TO_KEY.get(evt.keysym, evt.keysym.lower())
        _set_key(name)
        _stop_listen()
        return "break"

    def _on_listen_mouse(evt: tk.Event) -> str:
        nonlocal _listen_active
        if not _listen_active:
            return ""
        if append_mode and _combo_keys:
            # 鼠标点击时如果有组合键在收集 → 完成
            _finish_combo()
            return "break"
        name = _MOUSE_BTN_MAP.get(evt.num)
        if name:
            _set_key(name)
        _stop_listen()
        return "break"

    def _bind_listen() -> None:
        nonlocal _listen_active, _dlg_ref
        if not _listen_active:
            return
        if _dlg_ref:
            if append_mode:
                _dlg_ref.bind("<Key>", _on_combo_key_down)
                _dlg_ref.bind("<KeyRelease>", _on_combo_key_up)
            else:
                _dlg_ref.bind("<Key>", _on_listen_key)
            _dlg_ref.bind("<Button-1>", _on_listen_mouse)
            _dlg_ref.bind("<Button-2>", _on_listen_mouse)
            _dlg_ref.bind("<Button-3>", _on_listen_mouse)
            key_entry.focus_set()

    def _start_listen() -> None:
        nonlocal _listen_active, _dlg_ref, _combo_keys, _combo_held, _combo_finished
        _listen_active = True
        _combo_keys = []
        _combo_held = set()
        _combo_finished = False
        _dlg_ref = parent_frame.winfo_toplevel()
        listen_btn.config(text=t("dialog.btn.listening"))
        key_entry.config(state="disabled")
        parent_frame.winfo_toplevel().after(200, _bind_listen)

    listen_btn.config(command=_start_listen)

    return v
