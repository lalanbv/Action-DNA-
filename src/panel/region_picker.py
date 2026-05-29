"""区域框选器 — 截图后显示在画布上让用户拖拽选择，支持拖拽调整大小。

交互模式:
    - 绘制: 点击空白区域拖拽画新矩形
    - 调整: 拖拽角/边控制柄调整大小
    - 移动: 拖拽矩形内部移动整个选区
    - 确认: 按 Enter 确认选择
    - 取消: Esc 取消
"""

import tkinter as tk

from PIL import Image, ImageTk

from src.core.vision import ScreenCapture
from src.panel.canvas.theme import current_theme
from src.panel.region_coords import RegionCoordConverter
from src.utils.i18n import t

_HANDLE_HALF = 5
_HANDLE_HIT = 8

_HANDLE_CURSORS = [
    "top_left_corner", "top_side", "top_right_corner",
    "right_side", "bottom_right_corner", "bottom_side",
    "bottom_left_corner", "left_side",
]


class RegionPicker:
    """截图后在新窗口中让用户拖拽选择矩形区域，支持拖拽调整。"""

    def __init__(self, callback_or_capture, callback=None, *, on_cancel=None):
        """截图后在新窗口中让用户拖拽选择矩形区域，回调返回逻辑像素坐标。

        支持两种调用方式:
            RegionPicker(callback)                      — 兼容旧调用
            RegionPicker(capture, callback, on_cancel=) — 新调用(传入已有 capture)
        """
        if callable(callback_or_capture) and callback is None:
            self.callback = callback_or_capture
            capture = ScreenCapture()
            own_capture = True
        else:
            self.callback = callback
            capture = callback_or_capture
            own_capture = False
        self._on_cancel = on_cancel
        self._destroyed = False

        # 交互状态
        self._handles: list[int] = []
        self._mode: str = "draw"
        self._active_handle: int = -1
        self._move_origin: tuple[int, int] = (0, 0)
        self._move_rect_start: tuple[float, ...] = (0, 0, 0, 0)
        self._last_valid_rect: tuple[float, ...] | None = None
        self._hint_id: int | None = None

        self.start_x = 0
        self.start_y = 0
        self.rect_id: int | None = None
        self._overlay_ids: list[int] = []
        self._overlay_created: bool = False
        self._canvas_w: int = 0
        self._canvas_h: int = 0

        # 先截图
        try:
            screen_bgr = capture.grab()
        finally:
            if own_capture:
                capture.close()

        # 转换 BGR → RGB → PIL Image
        from src.core.vision._cv2_guard import cv2, require_cv2

        require_cv2("region picker")
        screen_rgb = cv2.cvtColor(screen_bgr, cv2.COLOR_BGR2RGB)
        self._screen_h, self._screen_w = screen_rgb.shape[:2]
        pil_img = Image.fromarray(screen_rgb)

        # 先创建窗口以获取屏幕尺寸
        self.root = tk.Toplevel()

        root_w = pil_img.width
        root_h = pil_img.height
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        max_w = screen_w - 60
        max_h = screen_h - 80
        display_scale = min(max_w / root_w, max_h / root_h, 1.0)
        display_w = int(root_w * display_scale)
        display_h = int(root_h * display_scale)
        self._converter = RegionCoordConverter.from_capture(capture, display_scale)

        pil_resized = pil_img.resize((display_w, display_h), Image.LANCZOS)

        # 配置窗口
        self.root.title(t("region.title"))
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)
        pos_x = (screen_w - display_w) // 2
        pos_y = (screen_h - display_h) // 2
        self.root.geometry(f"{display_w}x{display_h}+{pos_x}+{pos_y}")

        self._photo = ImageTk.PhotoImage(pil_resized)

        self.canvas = tk.Canvas(self.root, width=display_w, height=display_h, cursor="cross")
        self.canvas.pack()
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self._photo)

        self._canvas_w = display_w
        self._canvas_h = display_h

        # 提示文字（画布底部居中）
        self._hint_id = self.canvas.create_text(
            display_w // 2, display_h - 15,
            text="", fill="white",
            font=("Arial", 10),
        )

        # 事件绑定
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Motion>", self._on_motion)
        self.root.bind("<Escape>", lambda _: self._cancel())
        self.root.bind("<Return>", lambda _: self._confirm())
        self.root.protocol("WM_DELETE_WINDOW", self._cancel)

        # 等待窗口关闭
        self.root.grab_set()
        self.root.wait_window()

    # ── 事件处理 ──────────────────────────────────────────

    def _on_press(self, event):
        # 1. 检查是否在控制柄上 → 调整大小
        handle = self._hit_test_handle(event.x, event.y)
        if handle >= 0 and self.rect_id:
            self._mode = "resize"
            self._active_handle = handle
            return

        # 2. 检查是否在矩形内部 → 移动
        if self.rect_id and self._is_inside_rect(event.x, event.y):
            self._mode = "move"
            self._move_origin = (event.x, event.y)
            self._move_rect_start = tuple(self.canvas.coords(self.rect_id))
            return

        # 3. 空白区域 → 重新绘制
        self._mode = "draw"
        self.start_x = event.x
        self.start_y = event.y
        self._clear_overlay()
        self._clear_handles()
        self._hide_hint()
        if self.rect_id:
            self.canvas.coords(self.rect_id, event.x, event.y, event.x, event.y)
        else:
            self.rect_id = self.canvas.create_rectangle(
                event.x, event.y, event.x, event.y,
                outline=current_theme().accent_red, width=2,
            )

    def _on_drag(self, event):
        if self._mode == "resize":
            self._drag_resize(event)
        elif self._mode == "move":
            self._drag_move(event)
        else:
            self._drag_draw(event)

    def _on_release(self, event):
        if not self.rect_id:
            return

        coords = self.canvas.coords(self.rect_id)
        x1, y1, x2, y2 = int(coords[0]), int(coords[1]), int(coords[2]), int(coords[3])

        if x2 - x1 < 5 or y2 - y1 < 5:
            # 太小 → 恢复上一次有效选区（如果有）
            if self._last_valid_rect:
                self.canvas.coords(self.rect_id, *self._last_valid_rect)
                x1, y1, x2, y2 = (int(c) for c in self._last_valid_rect)
            else:
                self._clear_handles()
                self._mode = "draw"
                return

        self._last_valid_rect = (x1, y1, x2, y2)
        self._draw_handles()
        self._update_overlay(x1, y1, x2, y2)
        self._show_hint()
        self._mode = "idle"

    def _on_motion(self, event):
        handle = self._hit_test_handle(event.x, event.y)
        if handle >= 0:
            self.canvas.configure(cursor=_HANDLE_CURSORS[handle])
        elif self.rect_id and self._is_inside_rect(event.x, event.y):
            self.canvas.configure(cursor="fleur")
        else:
            self.canvas.configure(cursor="cross")

    # ── 绘制模式 ──────────────────────────────────────────

    def _drag_draw(self, event):
        if not self.rect_id:
            return
        x1 = min(self.start_x, event.x)
        y1 = min(self.start_y, event.y)
        x2 = max(self.start_x, event.x)
        y2 = max(self.start_y, event.y)
        self.canvas.coords(self.rect_id, x1, y1, x2, y2)
        self._update_overlay(x1, y1, x2, y2)

    # ── 调整大小模式 ──────────────────────────────────────

    def _drag_resize(self, event):
        if not self.rect_id:
            return
        coords = list(self.canvas.coords(self.rect_id))
        x1, y1, x2, y2 = coords

        h = self._active_handle
        if h in (0, 6, 7):
            x1 = event.x
        if h in (0, 1, 2):
            y1 = event.y
        if h in (2, 3, 4):
            x2 = event.x
        if h in (4, 5, 6):
            y2 = event.y

        x1, x2 = min(x1, x2), max(x1, x2)
        y1, y2 = min(y1, y2), max(y1, y2)
        self.canvas.coords(self.rect_id, x1, y1, x2, y2)
        self._update_overlay(int(x1), int(y1), int(x2), int(y2))
        self._update_handle_positions(int(x1), int(y1), int(x2), int(y2))

    # ── 移动模式 ──────────────────────────────────────────

    def _drag_move(self, event):
        if not self.rect_id:
            return
        ox, oy = self._move_origin
        rx1, ry1, rx2, ry2 = self._move_rect_start
        dx, dy = event.x - ox, event.y - oy
        nx1, ny1, nx2, ny2 = rx1 + dx, ry1 + dy, rx2 + dx, ry2 + dy
        self.canvas.coords(self.rect_id, nx1, ny1, nx2, ny2)
        self._update_overlay(int(nx1), int(ny1), int(nx2), int(ny2))
        self._update_handle_positions(int(nx1), int(ny1), int(nx2), int(ny2))

    # ── 确认 / 取消 ──────────────────────────────────────────

    def _confirm(self):
        if not self.rect_id or self._destroyed:
            return
        coords = self.canvas.coords(self.rect_id)
        x1, y1, x2, y2 = int(coords[0]), int(coords[1]), int(coords[2]), int(coords[3])
        lx, ly, width, height = self._converter.to_logical_rect(x1, y1, x2, y2)
        self._destroyed = True
        self.root.destroy()
        if width > 10 and height > 10:
            self.callback(lx, ly, width, height)

    def _cancel(self):
        if self._destroyed:
            return
        self._destroyed = True
        self.root.destroy()
        if self._on_cancel:
            self._on_cancel()

    # ── 控制柄 ──────────────────────────────────────────

    @staticmethod
    def _handle_positions(x1, y1, x2, y2) -> list[tuple[float, float]]:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        return [
            (x1, y1), (mx, y1), (x2, y1), (x2, my),
            (x2, y2), (mx, y2), (x1, y2), (x1, my),
        ]

    def _draw_handles(self):
        self._clear_handles()
        if not self.rect_id:
            return
        th = current_theme()
        coords = self.canvas.coords(self.rect_id)
        for cx, cy in self._handle_positions(*(int(c) for c in coords)):
            h = self.canvas.create_rectangle(
                cx - _HANDLE_HALF, cy - _HANDLE_HALF,
                cx + _HANDLE_HALF, cy + _HANDLE_HALF,
                fill=th.accent_red, outline="white", width=1,
            )
            self._handles.append(h)

    def _update_handle_positions(self, x1, y1, x2, y2):
        if len(self._handles) != 8:
            self._draw_handles()
            return
        for i, (cx, cy) in enumerate(self._handle_positions(x1, y1, x2, y2)):
            self.canvas.coords(
                self._handles[i],
                cx - _HANDLE_HALF, cy - _HANDLE_HALF,
                cx + _HANDLE_HALF, cy + _HANDLE_HALF,
            )

    def _clear_handles(self):
        for h in self._handles:
            self.canvas.delete(h)
        self._handles.clear()

    def _hit_test_handle(self, x, y) -> int:
        if not self._handles or not self.rect_id:
            return -1
        coords = self.canvas.coords(self.rect_id)
        for i, (cx, cy) in enumerate(self._handle_positions(*(int(c) for c in coords))):
            if abs(x - cx) <= _HANDLE_HIT and abs(y - cy) <= _HANDLE_HIT:
                return i
        return -1

    def _is_inside_rect(self, x, y) -> bool:
        if not self.rect_id:
            return False
        coords = self.canvas.coords(self.rect_id)
        return coords[0] < x < coords[2] and coords[1] < y < coords[3]

    # ── 提示文字 ──────────────────────────────────────────

    def _show_hint(self):
        if self._hint_id is not None:
            self.canvas.itemconfigure(
                self._hint_id,
                text=f"{t('region.confirm_hint')}  |  {t('region.cancel_hint')}",
            )
            self.canvas.tag_raise(self._hint_id)

    def _hide_hint(self):
        if self._hint_id is not None:
            self.canvas.itemconfigure(self._hint_id, text="")

    # ── 遮罩 ──────────────────────────────────────────

    def _ensure_overlay_items(self) -> None:
        if self._overlay_created:
            return
        theme = current_theme()
        kw = dict(fill=theme.region_dim_color, stipple=theme.region_dim_stipple, outline="")
        for _ in range(4):
            self._overlay_ids.append(self.canvas.create_rectangle(0, 0, 0, 0, **kw))
        self._overlay_created = True

    def _update_overlay(self, x1, y1, x2, y2) -> None:
        self._ensure_overlay_items()
        cw, ch = self._canvas_w, self._canvas_h
        rects = [
            (0, 0, cw, y1) if y1 > 0 else None,
            (0, y2, cw, ch) if y2 < ch else None,
            (0, y1, x1, y2) if x1 > 0 else None,
            (x2, y1, cw, y2) if x2 < cw else None,
        ]
        for i, rcoords in enumerate(rects):
            if rcoords:
                self.canvas.coords(self._overlay_ids[i], *rcoords)
                self.canvas.itemconfigure(self._overlay_ids[i], state="normal")
            else:
                self.canvas.itemconfigure(self._overlay_ids[i], state="hidden")
        if self.rect_id:
            self.canvas.tag_raise(self.rect_id)
        for h in self._handles:
            self.canvas.tag_raise(h)

    def _clear_overlay(self) -> None:
        for oid in self._overlay_ids:
            self.canvas.itemconfigure(oid, state="hidden")
