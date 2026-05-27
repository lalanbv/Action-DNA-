"""GridRenderer — 优化的网格渲染器，使用对象池避免 delete/create 循环"""

import math
import tkinter as tk

_MIN_SPACING_PX = 8
_MAX_DOT_RADIUS = 2
_SUB_DOT_MIN_ZOOM = 1.5
_SUB_DOT_MIN_SPACING = 6


class GridRenderer:
    """使用预分配 oval 池渲染背景点阵网格。

    核心优化:
    - 预分配 canvas oval 项，密度变化时仅扩容不缩减
    - 缩放/平移时通过 coords() 原地更新位置
    - 缓存上次颜色，仅在颜色变化时调用 itemconfigure
    - 隐藏/显示标记避免重复 itemconfigure
    - 增量更新：视口未实际移动时跳过全部计算
    """

    __slots__ = (
        "_canvas", "_main_pool", "_sub_pool",
        "_origin_h", "_origin_v",
        "_visible_main", "_visible_sub",
        "_last_dot_color", "_last_sub_color", "_last_origin_color",
        "_last_pixel_ox", "_last_pixel_oy", "_last_zoom", "_last_grid_spacing",
        "_last_canvas_w", "_last_canvas_h",
    )

    def __init__(self, canvas: tk.Canvas) -> None:
        self._canvas = canvas
        self._main_pool: list[int] = []
        self._sub_pool: list[int] = []
        self._origin_h = canvas.create_line(0, 0, 0, 0, fill="", width=1, tags=("grid",))
        self._origin_v = canvas.create_line(0, 0, 0, 0, fill="", width=1, tags=("grid",))
        self._visible_main: set[int] = set()
        self._visible_sub: set[int] = set()
        self._reset_cache()

    def _reset_cache(self) -> None:
        self._last_dot_color: str = ""
        self._last_sub_color: str = ""
        self._last_origin_color: str = ""
        self._last_pixel_ox: float = float("nan")
        self._last_pixel_oy: float = float("nan")
        self._last_zoom: float = float("nan")
        self._last_grid_spacing: int = -1
        self._last_canvas_w: int = -1
        self._last_canvas_h: int = -1

    def update(
        self,
        offset_x: float,
        offset_y: float,
        zoom: float,
        grid_spacing: int,
        dot_color: str,
        sub_dot_color: str,
        origin_color: str,
    ) -> None:
        """根据当前视口状态更新所有网格点位置。"""
        canvas = self._canvas
        w = canvas.winfo_width()
        h = canvas.winfo_height()
        if w < 2 or h < 2:
            self._hide_all()
            return

        spacing = grid_spacing * zoom
        if spacing < _MIN_SPACING_PX:
            self._hide_all()
            return

        # 增量判断：像素偏移 + 画布尺寸是否实际变化
        pixel_ox = offset_x * zoom
        pixel_oy = offset_y * zoom
        color_changed = dot_color != self._last_dot_color
        zoom_changed = zoom != self._last_zoom or grid_spacing != self._last_grid_spacing
        size_changed = w != self._last_canvas_w or h != self._last_canvas_h

        if not zoom_changed and not color_changed and not size_changed:
            dx = abs(pixel_ox - self._last_pixel_ox)
            dy = abs(pixel_oy - self._last_pixel_oy)
            if dx < 0.5 and dy < 0.5:
                return

        self._last_pixel_ox = pixel_ox
        self._last_pixel_oy = pixel_oy
        self._last_zoom = zoom
        self._last_grid_spacing = grid_spacing
        self._last_dot_color = dot_color
        self._last_canvas_w = w
        self._last_canvas_h = h

        pr = max(1, min(_MAX_DOT_RADIUS, int(zoom)))
        ox = math.fmod(pixel_ox, spacing)
        oy = math.fmod(pixel_oy, spacing)

        cols = int(w / spacing) + 4
        rows = int(h / spacing) + 4

        self._visible_main = self._position_dots(
            pool=self._main_pool,
            cols=cols, rows=rows,
            spacing=spacing, radius=pr,
            ox=ox, oy=oy,
            start_x=-ox - spacing, start_y=-oy - spacing,
            color=dot_color, color_changed=color_changed,
            prev_visible=self._visible_main,
            trim_threshold=50, trim_buffer=20,
        )

        show_sub = zoom >= _SUB_DOT_MIN_ZOOM and spacing / 2 >= _SUB_DOT_MIN_SPACING
        if show_sub:
            sub_color_changed = sub_dot_color != self._last_sub_color
            self._last_sub_color = sub_dot_color
            sr = max(1, pr - 1)
            sub_spacing = spacing / 2
            self._visible_sub = self._position_dots(
                pool=self._sub_pool,
                cols=cols, rows=rows,
                spacing=spacing, radius=sr,
                ox=ox, oy=oy,
                start_x=-ox - spacing + sub_spacing,
                start_y=-oy - spacing + sub_spacing,
                color=sub_dot_color, color_changed=sub_color_changed,
                prev_visible=self._visible_sub,
                trim_threshold=30, trim_buffer=10,
            )
        else:
            self._hide_sub()

        # 世界原点十字线
        if origin_color != self._last_origin_color:
            self._last_origin_color = origin_color
            canvas.itemconfigure(self._origin_h, fill=origin_color)
            canvas.itemconfigure(self._origin_v, fill=origin_color)
        origin_sx = -offset_x * zoom
        origin_sy = -offset_y * zoom
        canvas.coords(self._origin_h, 0, origin_sy, w, origin_sy)
        canvas.coords(self._origin_v, origin_sx, 0, origin_sx, h)

        canvas.tag_lower("grid")

    def _position_dots(
        self,
        pool: list[int],
        cols: int,
        rows: int,
        spacing: float,
        radius: int,
        ox: float,
        oy: float,
        start_x: float,
        start_y: float,
        color: str,
        color_changed: bool,
        prev_visible: set[int],
        trim_threshold: int,
        trim_buffer: int,
    ) -> set[int]:
        canvas = self._canvas
        needed = cols * rows

        prev_len = len(pool)
        while len(pool) < needed:
            pool.append(
                canvas.create_oval(0, 0, 0, 0, fill=color, outline="", tags=("grid",))
            )
        new_items: set[int] = set()
        if prev_len < needed:
            new_items = set(pool[prev_len:])

        new_visible: set[int] = set()
        idx = 0
        x = start_x
        for _ in range(cols):
            y = start_y
            for _ in range(rows):
                item = pool[idx]
                canvas.coords(item, x - radius, y - radius, x + radius, y + radius)
                if (color_changed or item not in prev_visible) and item not in new_items:
                    canvas.itemconfigure(item, fill=color)
                new_visible.add(item)
                idx += 1
                y += spacing
            x += spacing

        excess = len(pool) - needed
        if excess > trim_threshold:
            trim = excess - trim_buffer
            canvas.delete(*pool[-trim:])
            del pool[-trim:]

        return new_visible

    def _hide_sub(self) -> None:
        canvas = self._canvas
        if self._sub_pool:
            canvas.delete(*self._sub_pool)
        self._sub_pool.clear()
        self._visible_sub = set()
        self._last_sub_color = ""

    def _hide_all(self) -> None:
        canvas = self._canvas
        for item in self._visible_main:
            canvas.coords(item, -10, -10, -10, -10)
            canvas.itemconfigure(item, fill="")
        self._visible_main = set()
        self._last_dot_color = ""
        self._hide_sub()
        canvas.coords(self._origin_h, 0, 0, 0, 0)
        canvas.itemconfigure(self._origin_h, fill="")
        canvas.coords(self._origin_v, 0, 0, 0, 0)
        canvas.itemconfigure(self._origin_v, fill="")
        self._last_origin_color = ""

    def invalidate(self) -> None:
        """canvas.delete('all') 后调用 — 清除无效的 item id，下次 update 会重新分配"""
        self._main_pool.clear()
        self._sub_pool.clear()
        self._origin_h = self._canvas.create_line(0, 0, 0, 0, fill="", width=1, tags=("grid",))
        self._origin_v = self._canvas.create_line(0, 0, 0, 0, fill="", width=1, tags=("grid",))
        self._visible_main = set()
        self._visible_sub = set()
        self._reset_cache()

    def destroy(self) -> None:
        canvas = self._canvas
        if self._main_pool:
            canvas.delete(*self._main_pool)
        if self._sub_pool:
            canvas.delete(*self._sub_pool)
        canvas.delete(self._origin_h)
        canvas.delete(self._origin_v)
        self._main_pool.clear()
        self._sub_pool.clear()
