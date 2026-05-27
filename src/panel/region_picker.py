"""区域框选器 — 截图后显示在画布上让用户拖拽选择"""

import tkinter as tk

from PIL import Image, ImageTk

from src.core.vision import ScreenCapture
from src.panel.canvas.theme import current_theme
from src.panel.region_coords import RegionCoordConverter
from src.utils.i18n import t


class RegionPicker:
    """截图后在新窗口中让用户拖拽选择矩形区域，回调返回逻辑像素坐标"""

    def __init__(self, callback_or_capture, callback=None, *, on_cancel=None):
        """截图后在新窗口中让用户拖拽选择矩形区域

        支持两种调用方式:
            RegionPicker(callback)                      — 兼容旧调用
            RegionPicker(capture, callback, on_cancel=) — 新调用(传入已有 capture)
        """
        if callable(callback_or_capture) and callback is None:
            # 旧调用: RegionPicker(callback)
            self.callback = callback_or_capture
            capture = ScreenCapture()
            own_capture = True
        else:
            # 新调用: RegionPicker(capture, callback, on_cancel=)
            self.callback = callback
            capture = callback_or_capture
            own_capture = False
        self._on_cancel = on_cancel
        self.start_x = 0
        self.start_y = 0
        self.rect_id = None
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

        # 使用截图尺寸和 tkinter 屏幕尺寸计算缩放
        root_w = pil_img.width
        root_h = pil_img.height
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        max_w = screen_w - 60   # 留边距
        max_h = screen_h - 80   # 留出标题栏空间
        display_scale = min(max_w / root_w, max_h / root_h, 1.0)
        display_w = int(root_w * display_scale)
        display_h = int(root_h * display_scale)
        self._converter = RegionCoordConverter.from_capture(capture, display_scale)

        pil_resized = pil_img.resize((display_w, display_h), Image.LANCZOS)

        # 配置窗口
        self.root.title(t("region.title"))
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)
        # 居中显示在屏幕上
        pos_x = (screen_w - display_w) // 2
        pos_y = (screen_h - display_h) // 2
        self.root.geometry(f"{display_w}x{display_h}+{pos_x}+{pos_y}")

        self._photo = ImageTk.PhotoImage(pil_resized)

        self.canvas = tk.Canvas(self.root, width=display_w, height=display_h, cursor="cross")
        self.canvas.pack()
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self._photo)

        self._destroyed = False

        # 事件绑定
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.root.bind("<Escape>", lambda _: self._cancel())
        self.root.protocol("WM_DELETE_WINDOW", self._cancel)

        # 等待窗口关闭
        self.root.grab_set()
        self.root.wait_window()

    def _cancel(self):
        """取消选择（Esc 或窗口关闭按钮）"""
        if self._destroyed:
            return
        self._destroyed = True
        self.root.destroy()
        if self._on_cancel:
            self._on_cancel()

    def _on_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        self._clear_overlay()
        if self.rect_id:
            self.canvas.coords(self.rect_id, event.x, event.y, event.x, event.y)
        else:
            self.rect_id = self.canvas.create_rectangle(
                event.x, event.y, event.x, event.y,
                outline=current_theme().accent_red, width=2,
            )

    def _on_drag(self, event):
        if not self.rect_id:
            return
        x1 = min(self.start_x, event.x)
        y1 = min(self.start_y, event.y)
        x2 = max(self.start_x, event.x)
        y2 = max(self.start_y, event.y)
        self.canvas.coords(self.rect_id, x1, y1, x2, y2)
        self._update_overlay(x1, y1, x2, y2)

    def _on_release(self, event):
        x1 = min(self.start_x, event.x)
        y1 = min(self.start_y, event.y)
        x2 = max(self.start_x, event.x)
        y2 = max(self.start_y, event.y)

        # 画布坐标 → 逻辑坐标
        lx, ly, width, height = self._converter.to_logical_rect(x1, y1, x2, y2)

        self.root.destroy()

        if width > 10 and height > 10:
            self.callback(lx, ly, width, height)

    def _ensure_overlay_items(self) -> None:
        """首次调用时创建 4 个遮罩矩形，后续复用（coords 更新而非销毁重建）"""
        if self._overlay_created:
            return
        theme = current_theme()
        kw = dict(fill=theme.region_dim_color, stipple=theme.region_dim_stipple, outline="")
        for _ in range(4):
            self._overlay_ids.append(
                self.canvas.create_rectangle(0, 0, 0, 0, **kw)
            )
        self._canvas_w = self.canvas.winfo_width()
        self._canvas_h = self.canvas.winfo_height()
        self._overlay_created = True

    def _update_overlay(self, x1: int, y1: int, x2: int, y2: int) -> None:
        """更新选区外半透明遮罩 — 选区内保持清晰可见"""
        self._ensure_overlay_items()
        cw, ch = self._canvas_w, self._canvas_h
        # top, bottom, left, right
        rects = [
            (0, 0, cw, y1) if y1 > 0 else None,
            (0, y2, cw, ch) if y2 < ch else None,
            (0, y1, x1, y2) if x1 > 0 else None,
            (x2, y1, cw, y2) if x2 < cw else None,
        ]
        for i, coords in enumerate(rects):
            if coords:
                self.canvas.coords(self._overlay_ids[i], *coords)
                self.canvas.itemconfigure(self._overlay_ids[i], state="normal")
            else:
                self.canvas.itemconfigure(self._overlay_ids[i], state="hidden")
        if self.rect_id:
            self.canvas.tag_raise(self.rect_id)

    def _clear_overlay(self) -> None:
        for oid in self._overlay_ids:
            self.canvas.itemconfigure(oid, state="hidden")
