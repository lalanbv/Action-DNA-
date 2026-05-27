"""NodeCreationPopup — 可搜索的节点创建弹窗

右键画布空白处弹出，支持搜索筛选、键盘导航、分类列表。
"""

import tkinter as tk

from src.panel.canvas.theme import current_theme
from src.panel.canvas.scale import scale_manager
from src.panel.components.palette_data import ACTION_PALETTE, FLOW_PALETTE
from src.utils.i18n import t


class _Entry(tk.Entry):
    """搜索框 — 拦截按键，阻止传播到画布。"""

    def __init__(self, master: tk.Widget, **kw):
        super().__init__(master, **kw)
        self.bind("<Key>", self._swallow, add=True)

    def _swallow(self, _event: tk.Event) -> str:
        return "break"


class NodeCreationPopup(tk.Toplevel):
    """可搜索的节点创建弹窗。"""

    def __init__(
        self,
        parent: tk.Widget,
        screen_x: int,
        screen_y: int,
        on_create_action,
        on_create_flow,
    ) -> None:
        super().__init__(parent)
        self._on_create_action = on_create_action
        self._on_create_flow = on_create_flow

        self._items: list[tuple[str, str, str, object]] = []
        self._row_to_item: list[int | None] = []
        self._selected_idx: int = -1
        self._ready: bool = False

        self._build(screen_x, screen_y)

    def _build(self, sx: int, sy: int) -> None:
        th = current_theme()
        sm = scale_manager()

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=th.bg_surface)

        w = sm.s(220)
        h = sm.s(320)

        # 搜索框
        self._search_var = tk.StringVar()
        entry = _Entry(
            self,
            textvariable=self._search_var,
            font=th.font_small,
            bg=th.input_bg,
            fg=th.text_primary,
            insertbackground=th.text_primary,
            relief=tk.FLAT,
            bd=0,
        )
        entry.pack(fill=tk.X, padx=sm.s(4), pady=sm.s(4))
        entry.bind("<KeyRelease>", self._on_search)
        entry.bind("<Up>", self._on_up)
        entry.bind("<Down>", self._on_down)
        entry.bind("<Return>", self._on_enter)
        entry.bind("<Escape>", lambda _: self.destroy())
        entry.focus_set()

        # 列表
        self._listbox = tk.Listbox(
            self,
            width=sm.s(28),
            height=sm.s(16),
            font=th.font_small,
            bg=th.bg_surface,
            fg=th.text_primary,
            selectbackground=th.accent_blue,
            selectforeground=th.text_on_accent,
            relief=tk.FLAT,
            bd=0,
            highlightthickness=0,
            activestyle="none",
        )
        self._listbox.pack(fill=tk.BOTH, expand=True, padx=sm.s(4), pady=(0, sm.s(4)))
        self._listbox.bind("<Return>", self._on_enter)
        self._listbox.bind("<Escape>", lambda _: self.destroy())
        self._listbox.bind("<Double-Button-1>", self._on_enter)
        self._listbox.bind("<<ListboxSelect>>", self._on_listbox_select)

        self._populate_items()
        self._apply_filter("")

        self.bind("<FocusOut>", self._on_focus_out)

        self.update_idletasks()
        self.geometry(f"{w}x{min(h, self.winfo_reqheight())}+{sx}+{sy}")

        # Delay ready flag so FocusOut doesn't fire during initial setup
        self.after(150, self._mark_ready)

    def _populate_items(self) -> None:
        action_section = t("workflow.palette.section_action")
        for at, i18n_key in ACTION_PALETTE:
            self._items.append((t(i18n_key), action_section, "action", at))

        flow_section = t("workflow.palette.section_flow")
        for nt, i18n_key in FLOW_PALETTE:
            self._items.append((t(i18n_key), flow_section, "flow", nt))

    def _apply_filter(self, query: str) -> None:
        self._listbox.delete(0, tk.END)
        self._row_to_item = []
        q = query.lower().strip()
        current_section = ""

        for i, (label, section, *_rest) in enumerate(self._items):
            if q and q not in label.lower() and q not in section.lower():
                continue
            if section != current_section:
                self._listbox.insert(tk.END, f"── {section} ──")
                self._listbox.itemconfig(tk.END, fg=current_theme().text_muted)
                self._row_to_item.append(None)
                current_section = section
            self._listbox.insert(tk.END, f"  {label}")
            self._row_to_item.append(i)

        for row_idx, item_idx in enumerate(self._row_to_item):
            if item_idx is not None:
                self._listbox.selection_set(row_idx)
                self._listbox.activate(row_idx)
                break

    def _on_search(self, _event: tk.Event) -> None:
        self._apply_filter(self._search_var.get())

    def _on_up(self, _event: tk.Event) -> str:
        sel = self._listbox.curselection()
        if not sel:
            return "break"
        new_idx = sel[0] - 1
        while new_idx >= 0 and self._row_to_item[new_idx] is None:
            new_idx -= 1
        if new_idx < 0:
            return "break"
        self._listbox.selection_clear(0, tk.END)
        self._listbox.selection_set(new_idx)
        self._listbox.see(new_idx)
        return "break"

    def _on_down(self, _event: tk.Event) -> str:
        sel = self._listbox.curselection()
        size = self._listbox.size()
        if not sel:
            return "break"
        new_idx = sel[0] + 1
        while new_idx < size and self._row_to_item[new_idx] is None:
            new_idx += 1
        if new_idx >= size:
            return "break"
        self._listbox.selection_clear(0, tk.END)
        self._listbox.selection_set(new_idx)
        self._listbox.see(new_idx)
        return "break"

    def _on_enter(self, _event: tk.Event) -> None:
        sel = self._listbox.curselection()
        if not sel:
            return

        item_idx = self._row_to_item[sel[0]]
        if item_idx is None:
            return

        item = self._items[item_idx]
        kind, data = item[2], item[3]

        self.destroy()

        if kind == "action":
            self._on_create_action(data)
        elif kind == "flow":
            self._on_create_flow(data)

    def _on_listbox_select(self, _event: tk.Event) -> None:
        """Single-click on listbox item → create node and close."""
        self._on_enter(_event)

    def _mark_ready(self) -> None:
        self._ready = True

    def _on_focus_out(self, _event: tk.Event) -> None:
        if not self._ready:
            return
        # Check if focus moved to a widget outside this popup
        try:
            focus_widget = self.focus_get()
            if focus_widget is None or str(focus_widget).startswith(str(self)):
                return
        except tk.TclError:
            pass
        self.destroy()
