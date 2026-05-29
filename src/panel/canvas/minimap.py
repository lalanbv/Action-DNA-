"""Minimap — 画布右下角小地图 (改进版 v2)

改进:
- 260x195px 叠加在主画布右下角
- 节点以双色调矩形显示 (header 强调色 + body 暗色)
- 连线以类型着色 (true/false/loop 不同颜色)
- 选中节点蓝色边框高亮
- 鼠标悬停显示节点名称
- 鼠标滚轮缩放主画布
- 视口矩形蓝色虚线 + 缩放百分比
- 点击/拖动 → 视口中心移动到点击位置
- 边界框缓存避免重复计算
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from typing import TYPE_CHECKING

from src.panel.canvas.edge_geometry import estimate_text_width
from src.panel.canvas.node_shared import execution_state_theme_key
from src.panel.models.enums import NodeExecutionState
from src.utils.platform import IS_MACOS, IS_LINUX

from src.core.flow import FlowGraph

if TYPE_CHECKING:
    from src.panel.canvas.graph_canvas import GraphCanvas
from src.panel.canvas.minimap_settings import MinimapSettings
from src.panel.canvas.node_renderer import node_size
from src.panel.canvas.viewport import graph_bounds
from src.panel.canvas.theme import (
    CanvasTheme,
    current_theme,
    edge_color_by_label,
    node_fill_color,
    node_border_color,
)
from src.panel.canvas.scale import scale_manager


SIZE_MAP: dict[str, int] = {
    "small": 180,
    "medium": 260,
    "large": 340,
}

_ADAPTIVE_MIN: int = 150
_ADAPTIVE_MAX: int = 380


class Minimap:
    """画布小地图控制器"""

    def __init__(
        self,
        canvas: GraphCanvas,
        get_graph: Callable[[], FlowGraph | None],
        get_viewport: Callable[[], tuple[float, float, float]],
        on_pan: Callable[[float, float], None],
        get_selected_nodes: Callable[[], set[str]] | None = None,
        get_node_states: Callable[[], dict[str, str]] | None = None,
        get_selected_edge: Callable[[], str | None] | None = None,
        on_refresh_grid: Callable[[], None] | None = None,
    ):
        self._canvas = canvas
        self._get_graph = get_graph
        self._get_viewport = get_viewport
        self._on_pan = on_pan
        self._get_selected_nodes: Callable[[], set[str]] = get_selected_nodes or (lambda: set())
        self._get_node_states: Callable[[], dict[str, str]] = get_node_states or (lambda: {})
        self._get_selected_edge: Callable[[], str | None] = get_selected_edge or (lambda: None)
        self._on_refresh_grid: Callable[[], None] = on_refresh_grid or (lambda: None)

        theme = current_theme()
        sm = scale_manager()
        self._margin = theme.minimap_margin
        self._size = SIZE_MAP.get("medium", 260)
        self._height = int(self._size * 0.75)

        # 小地图容器 (在主画布上叠加)
        self._minimap_canvas = tk.Canvas(
            canvas,
            width=self._size,
            height=self._height,
            bg=theme.minimap_bg_panel,
            highlightthickness=1,
            highlightbackground=theme.minimap_border,
            cursor="crosshair",
        )

        # 视口矩形
        self._viewport_rect: int | None = None
        self._viewport_shadow: int | None = None

        # 去抖
        self._redraw_id: str | None = None

        # 拖拽状态
        self._dragging_minimap = False

        # 位置追踪: 区分默认位置和用户拖拽后的自定义位置
        self._user_positioned = False  # 用户是否手动拖拽过小地图
        self._last_canvas_size: tuple[int, int] = (0, 0)  # 上次画布尺寸

        # 边界缓存
        self._cached_bounds: tuple | None = None
        self._destroyed: bool = False

        # 节点命中区域: node_id -> (x1, y1, x2, y2)
        self._node_rects: dict[str, tuple[float, float, float, float]] = {}

        # 增量渲染缓存: node_id -> {body, header, label, state_dot}
        self._node_items_cache: dict[str, dict[str, int]] = {}
        # 增量渲染缓存: edge_id -> line item id
        self._edge_items_cache: dict[str, int] = {}
        # 缩放百分比文本 item
        self._zoom_text_id: int | None = None

        # 悬停标签
        self._hover_label: int | None = None
        self._hover_bg: int | None = None

        # 设置面板
        self._settings = MinimapSettings(
            self._minimap_canvas,
            on_change=self.schedule_full_redraw,
        )

        # 布局 — 延迟定位，确保画布已获得实际尺寸
        self._minimap_canvas.place_forget()
        self._canvas.after(100, self._initial_show)

        # 事件绑定
        self._minimap_canvas.bind("<ButtonPress-1>", self._on_minimap_click)
        self._minimap_canvas.bind("<B1-Motion>", self._on_minimap_drag)
        self._minimap_canvas.bind("<ButtonRelease-1>", self._on_minimap_release)
        self._minimap_canvas.bind("<Motion>", self._on_minimap_motion)
        self._minimap_canvas.bind("<Leave>", self._on_minimap_leave)
        self._minimap_canvas.bind("<MouseWheel>", self._on_minimap_scroll)
        if IS_LINUX:
            self._minimap_canvas.bind("<Button-4>", lambda e: self._do_zoom(1.15))
            self._minimap_canvas.bind("<Button-5>", lambda e: self._do_zoom(1 / 1.15))
        self._canvas_configure_id = canvas.bind("<Configure>", self._on_canvas_resize, add="+")

        # 齿轮图标按钮 (右上角, 右对齐防止溢出)
        self._gear_btn = tk.Label(
            self._minimap_canvas, text="⚙",
            bg=theme.minimap_bg_panel, fg=theme.text_muted,
            font=(theme.font_family, sm.s(10)),
            cursor="hand2",
        )
        self._gear_btn.place(relx=1.0, y=2, x=-4, anchor="ne")
        self._gear_btn.bind("<Button-1>", lambda _: self._settings.toggle())
        self._gear_btn.bind("<Enter>", lambda e: self._gear_btn.configure(fg=theme.text_primary))
        self._gear_btn.bind("<Leave>", lambda e: self._gear_btn.configure(fg=theme.text_muted))

        # 拖拽手柄 (左上角, 按住拖拽移动小地图)
        self._is_dragging_handle = False
        self._drag_start_root_x = 0
        self._drag_start_root_y = 0
        self._drag_start_place_x = 0
        self._drag_start_place_y = 0
        self._drag_btn = tk.Label(
            self._minimap_canvas, text="✥",
            bg=theme.minimap_bg_panel, fg=theme.text_muted,
            font=(theme.font_family, sm.s(10)),
            cursor="fleur",
        )
        self._drag_btn.place(x=4, y=2, anchor="nw")
        self._drag_btn.bind("<ButtonPress-1>", self._on_drag_handle_press)
        self._drag_btn.bind("<B1-Motion>", self._on_drag_handle_motion)
        self._drag_btn.bind("<ButtonRelease-1>", self._on_drag_handle_release)
        self._drag_btn.bind("<Enter>", lambda e: self._drag_btn.configure(fg=theme.text_primary))
        self._drag_btn.bind("<Leave>", lambda e: self._drag_btn.configure(fg=theme.text_muted))

    def _initial_show(self) -> None:
        """首次显示：等待画布有真实尺寸后再 place + 重绘。"""
        if self._destroyed:
            return
        w = self._canvas.winfo_width()
        h = self._canvas.winfo_height()
        if w < 10 or h < 10:
            self._canvas.after(50, self._initial_show)
            return
        self._last_canvas_size = (w, h)
        x, y = self._default_position()
        self._minimap_canvas.place(x=x, y=y)
        self.schedule_full_redraw()

    def _default_position(self) -> tuple[int, int]:
        """计算默认右下角位置（避免与浮动缩放控件重叠）。"""
        w = self._canvas.winfo_width()
        h = self._canvas.winfo_height()
        x = w - self._size - self._margin
        # 浮动缩放控件约 40px 高，留出空间避免重叠
        y = h - self._height - self._margin - 44
        return max(0, x), max(0, y)

    def reposition(self):
        w = self._canvas.winfo_width()
        h = self._canvas.winfo_height()
        if w < 10 or h < 10:
            self._canvas.after(50, self.reposition)
            return

        old_w, old_h = self._last_canvas_size
        if self._user_positioned and old_w > 10 and old_h > 10:
            cur_x = self._minimap_canvas.winfo_x()
            cur_y = self._minimap_canvas.winfo_y()
            ratio_x = min(max(cur_x / old_w, 0.0), 1.0)
            ratio_y = min(max(cur_y / old_h, 0.0), 1.0)
            x = int(ratio_x * w)
            y = int(ratio_y * h)
        else:
            x, y = self._default_position()

        # 限制在画布范围内
        x = max(0, min(x, w - self._size))
        y = max(0, min(y, h - self._height))

        self._last_canvas_size = (w, h)
        cur_x = self._minimap_canvas.winfo_x()
        cur_y = self._minimap_canvas.winfo_y()
        if cur_x == x and cur_y == y:
            return
        self._minimap_canvas.place(x=x, y=y)

    # ── 拖拽手柄 ───────────────────────────────────────────

    def _on_drag_handle_press(self, event: tk.Event) -> None:
        """开始拖拽小地图。"""
        self._is_dragging_handle = True
        self._drag_start_root_x = event.x_root
        self._drag_start_root_y = event.y_root
        self._drag_start_place_x = self._minimap_canvas.winfo_x()
        self._drag_start_place_y = self._minimap_canvas.winfo_y()

    def _on_drag_handle_motion(self, event: tk.Event) -> None:
        """拖拽中 — 小地图跟随鼠标。"""
        if not self._is_dragging_handle:
            return
        dx = event.x_root - self._drag_start_root_x
        dy = event.y_root - self._drag_start_root_y
        new_x = self._drag_start_place_x + dx
        new_y = self._drag_start_place_y + dy
        canvas_w = self._canvas.winfo_width()
        canvas_h = self._canvas.winfo_height()
        new_x = max(0, min(new_x, canvas_w - self._size))
        new_y = max(0, min(new_y, canvas_h - self._height))
        self._minimap_canvas.place(x=new_x, y=new_y)

    def _on_drag_handle_release(self, event: tk.Event) -> None:
        """结束拖拽 — 标记为用户自定义位置。"""
        self._is_dragging_handle = False
        self._user_positioned = True
        self._last_canvas_size = (
            self._canvas.winfo_width(),
            self._canvas.winfo_height(),
        )

    def _on_canvas_resize(self, event):
        """Canvas 尺寸变化时重新定位小地图并自适应尺寸。

        全量重绘由 GraphCanvas._on_resize_end → schedule_full_redraw 统一调度，
        避免双重 <Configure> 导致的重复绘制。
        """
        self._apply_size()
        self.reposition()

    # ── 坐标映射 ──────────────────────────────────────────

    def _compute_bounds(
        self, graph: FlowGraph
    ) -> tuple[float, float, float, float, float]:
        """计算图的边界框和缩放因子

        Returns: (min_wx, min_wy, world_w, world_h, scale)
        """
        if not graph.nodes:
            return 0, 0, 600, 400, min(self._size / 600, self._height / 400)

        min_x, min_y, max_x, max_y = graph_bounds(graph)

        pad = 50
        min_x -= pad
        min_y -= pad
        max_x += pad
        max_y += pad

        world_w = max_x - min_x
        world_h = max_y - min_y
        scale_x = self._size / world_w if world_w > 0 else 1
        scale_y = self._height / world_h if world_h > 0 else 1
        return min_x, min_y, world_w, world_h, min(scale_x, scale_y)

    def _get_bounds(self, graph: FlowGraph) -> tuple[float, float, float, float, float]:
        """获取边界 (带缓存)"""
        if self._cached_bounds is None:
            self._cached_bounds = self._compute_bounds(graph)
        return self._cached_bounds

    def _world_to_minimap(
        self, wx: float, wy: float, min_wx: float, min_wy: float, scale: float,
    ) -> tuple[float, float]:
        return (wx - min_wx) * scale, (wy - min_wy) * scale

    def _minimap_to_world(
        self, mx: float, my: float, min_wx: float, min_wy: float, scale: float,
    ) -> tuple[float, float]:
        return mx / scale + min_wx, my / scale + min_wy

    # ── 绘制 ──────────────────────────────────────────────

    def full_redraw(self):
        """增量重绘 — 对比前后差异，复用已有 canvas item。"""
        graph = self._get_graph()
        theme = current_theme()
        sm = scale_manager()
        mc = self._minimap_canvas

        mc.configure(bg=theme.minimap_bg_panel, highlightbackground=theme.minimap_border)
        self._node_rects.clear()
        self._clear_hover()

        self.reposition()

        if not graph or not graph.nodes:
            self._clear_all_items()
            self._cached_bounds = None
            return

        if self._cached_bounds is None:
            self._cached_bounds = self._compute_bounds(graph)
        min_wx, min_wy, world_w, world_h, scale = self._cached_bounds
        selected = self._get_selected_nodes()

        _sizes: dict[str, tuple[float, float]] = {
            nid: node_size(n) for nid, n in graph.nodes.items()
        }

        # ── 1. 增量更新边 ──
        selected_edge_id = self._get_selected_edge()
        if self._settings.show_edges:
            new_edge_ids = set()
            for edge in graph.edges:
                src = graph.get_node(edge.from_node)
                tgt = graph.get_node(edge.to_node)
                if not src or not tgt:
                    continue
                sw_s, sh_s = _sizes[src.node_id]
                sw_t, sh_t = _sizes[tgt.node_id]
                sx, sy = self._world_to_minimap(
                    src.pos_x + sw_s / 2, src.pos_y + sh_s / 2,
                    min_wx, min_wy, scale,
                )
                tx, ty = self._world_to_minimap(
                    tgt.pos_x + sw_t / 2, tgt.pos_y + sh_t / 2,
                    min_wx, min_wy, scale,
                )
                is_sel_edge = edge.edge_id == selected_edge_id
                line_width = 2.5 if is_sel_edge else 1.5
                color = edge_color_by_label(edge.label, theme)
                line_color = theme.accent_blue if is_sel_edge else color

                existing = self._edge_items_cache.get(edge.edge_id)
                if existing:
                    mc.coords(existing, sx, sy, tx, ty)
                    mc.itemconfigure(existing, fill=line_color, width=line_width)
                else:
                    iid = mc.create_line(sx, sy, tx, ty, fill=line_color, width=line_width)
                    self._edge_items_cache[edge.edge_id] = iid
                new_edge_ids.add(edge.edge_id)

            # 删除已移除的边
            for eid in list(self._edge_items_cache):
                if eid not in new_edge_ids:
                    mc.delete(self._edge_items_cache.pop(eid))
        else:
            self._clear_edge_items()

        # ── 2. 增量更新节点 ──
        node_states = self._get_node_states()
        new_node_ids: set[str] = set()
        for node in graph.nodes.values():
            if not self._settings.show_disabled and not node.enabled:
                continue
            nw, nh = _sizes[node.node_id]
            sx, sy = self._world_to_minimap(
                node.pos_x, node.pos_y, min_wx, min_wy, scale,
            )
            sw = max(nw * scale, 10)
            sh = max(nh * scale, 8)
            self._node_rects[node.node_id] = (sx, sy, sx + sw, sy + sh)

            accent = node_fill_color(node.node_type, theme)
            accent_dim = node_border_color(node.node_type, theme)
            is_selected = node.node_id in selected
            outline_color = theme.minimap_viewport if is_selected else accent_dim
            outline_width = 2 if is_selected else 1
            header_h = max(3, sh * 0.35)

            cached = self._node_items_cache.get(node.node_id)
            if cached:
                # 更新位置
                mc.coords(cached["body"], sx, sy, sx + sw, sy + sh)
                mc.itemconfigure(cached["body"], fill=accent_dim, outline=outline_color, width=outline_width)
                mc.coords(cached["header"], sx + 1, sy + 1, sx + sw - 1, sy + header_h)
                mc.itemconfigure(cached["header"], fill=accent)
                # 标签
                if "label" in cached:
                    if self._settings.show_labels and sw > 20:
                        desc = node.describe()
                        if len(desc) > 6:
                            desc = desc[:5] + "…"
                        mc.coords(cached["label"], sx + sw / 2, sy + sh + 6)
                        mc.itemconfigure(cached["label"], text=desc)
                    else:
                        mc.itemconfigure(cached["label"], state="hidden")
                # 状态圆点
                state = node_states.get(node.node_id)
                state_color = self._state_color(state, theme) if state else None
                if "state_dot" in cached:
                    if state_color:
                        r = max(2, min(4, sw * 0.1))
                        mc.coords(cached["state_dot"],
                                  sx + sw - r - 1, sy + 1,
                                  sx + sw - 1, sy + 1 + 2 * r)
                        mc.itemconfigure(cached["state_dot"], fill=state_color, state="normal")
                    else:
                        mc.itemconfigure(cached["state_dot"], state="hidden")
            else:
                # 创建新节点 items
                items: dict[str, int] = {}
                items["body"] = mc.create_rectangle(
                    sx, sy, sx + sw, sy + sh,
                    fill=accent_dim, outline=outline_color, width=outline_width,
                )
                items["header"] = mc.create_rectangle(
                    sx + 1, sy + 1, sx + sw - 1, sy + header_h,
                    fill=accent, outline="", width=0,
                )
                if self._settings.show_labels and sw > 20:
                    desc = node.describe()
                    if len(desc) > 6:
                        desc = desc[:5] + "…"
                    items["label"] = mc.create_text(
                        sx + sw / 2, sy + sh + 6,
                        text=desc, fill=theme.text_muted,
                        font=(theme.font_family, sm.s(6)), anchor="center",
                    )
                else:
                    # 创建隐藏标签供后续复用
                    items["label"] = mc.create_text(
                        0, 0, text="", fill=theme.text_muted,
                        font=(theme.font_family, sm.s(6)), anchor="center", state="hidden",
                    )
                state = node_states.get(node.node_id)
                state_color = self._state_color(state, theme) if state else None
                if state_color:
                    r = max(2, min(4, sw * 0.1))
                    items["state_dot"] = mc.create_oval(
                        sx + sw - r - 1, sy + 1,
                        sx + sw - 1, sy + 1 + 2 * r,
                        fill=state_color, outline="",
                    )
                else:
                    items["state_dot"] = mc.create_oval(
                        0, 0, 1, 1, fill="", outline="", state="hidden",
                    )
                self._node_items_cache[node.node_id] = items

            new_node_ids.add(node.node_id)

        # 删除已移除的节点
        for nid in list(self._node_items_cache):
            if nid not in new_node_ids:
                items = self._node_items_cache.pop(nid)
                for iid in items.values():
                    mc.delete(iid)

        # ── 3. 视口矩形 ──
        self._draw_viewport_rect(min_wx, min_wy, scale, theme)

        # ── 4. 缩放百分比 (复用 item) ──
        _, _, zoom = self._get_viewport()
        zoom_text = f"{zoom * 100:.0f}%"
        zoom_x = self._size - 8
        zoom_y = self._height - 4
        if self._zoom_text_id:
            mc.coords(self._zoom_text_id, zoom_x, zoom_y)
            mc.itemconfigure(self._zoom_text_id, text=zoom_text)
        else:
            self._zoom_text_id = mc.create_text(
                zoom_x, zoom_y,
                text=zoom_text,
                fill=theme.text_muted,
                font=(theme.font_family, sm.s(7)),
                anchor="se",
            )

    def _clear_all_items(self) -> None:
        """清空所有缓存的 canvas items。"""
        mc = self._minimap_canvas
        for items in self._node_items_cache.values():
            for iid in items.values():
                mc.delete(iid)
        self._node_items_cache.clear()
        self._clear_edge_items()
        if self._viewport_rect:
            mc.delete(self._viewport_rect)
            self._viewport_rect = None
        if self._viewport_shadow:
            mc.delete(self._viewport_shadow)
            self._viewport_shadow = None
        if self._zoom_text_id:
            mc.delete(self._zoom_text_id)
            self._zoom_text_id = None
        self._hover_label = None
        self._hover_bg = None

    def _clear_edge_items(self) -> None:
        mc = self._minimap_canvas
        for iid in self._edge_items_cache.values():
            mc.delete(iid)
        self._edge_items_cache.clear()

    def update_viewport(self):
        """仅更新视口框位置 (平移/缩放时调用)"""
        graph = self._get_graph()
        if not graph or not graph.nodes:
            return
        if self._cached_bounds is None:
            self._cached_bounds = self._compute_bounds(graph)
        min_wx, min_wy, _, _, scale = self._cached_bounds
        self._draw_viewport_rect(min_wx, min_wy, scale, current_theme())

    def _draw_viewport_rect(
        self,
        min_wx: float,
        min_wy: float,
        scale: float,
        theme: CanvasTheme,
    ):
        mc = self._minimap_canvas
        offset_x, offset_y, zoom = self._get_viewport()

        canvas_w = self._canvas.winfo_width()
        canvas_h = self._canvas.winfo_height()

        vp_wx1 = offset_x
        vp_wy1 = offset_y
        vp_wx2 = offset_x + canvas_w / zoom
        vp_wy2 = offset_y + canvas_h / zoom

        sx1, sy1 = self._world_to_minimap(vp_wx1, vp_wy1, min_wx, min_wy, scale)
        sx2, sy2 = self._world_to_minimap(vp_wx2, vp_wy2, min_wx, min_wy, scale)

        # 外发光轮廓: 提升视口矩形可见性
        glow_pad = 1
        if self._viewport_shadow:
            mc.coords(self._viewport_shadow,
                      sx1 - glow_pad, sy1 - glow_pad,
                      sx2 + glow_pad, sy2 + glow_pad)
        else:
            self._viewport_shadow = mc.create_rectangle(
                sx1 - glow_pad, sy1 - glow_pad,
                sx2 + glow_pad, sy2 + glow_pad,
                fill="", outline=theme.minimap_viewport_shadow, width=1,
            )

        if self._viewport_rect:
            mc.coords(self._viewport_rect, sx1, sy1, sx2, sy2)
        else:
            self._viewport_rect = mc.create_rectangle(
                sx1, sy1, sx2, sy2,
                fill="", outline=theme.minimap_viewport, width=2, dash=(6, 3),
            )

        # 确保 shadow 在 rect 下方
        if self._viewport_shadow and self._viewport_rect:
            mc.tag_lower(self._viewport_shadow, self._viewport_rect)

    @staticmethod
    def _state_color(state: str, theme: CanvasTheme) -> str | None:
        key = execution_state_theme_key(state)
        return getattr(theme, key, None) if key else None

    @staticmethod
    def _estimate_text_width(text: str, font_size: int) -> float:
        return estimate_text_width(text, font_size, latin_width=max(3, font_size - 2))

    # ── 去抖 ──────────────────────────────────────────────

    def schedule_full_redraw(self, invalidate_bounds: bool = True):
        """去抖调度全量重绘

        Args:
            invalidate_bounds: 是否使边界缓存失效。
                节点增删需传 True（位置变化影响边界），
                边增删传 False（边不影响节点边界框）。
        """
        if not self.is_shown():
            return
        if self._redraw_id:
            self._canvas.after_cancel(self._redraw_id)
        if invalidate_bounds:
            self._cached_bounds = None
        self._apply_size()
        self._redraw_id = self._canvas.after(30, self._do_full_redraw)

    def _compute_adaptive_size(self) -> int:
        """根据 size_mode 返回小地图宽度。"""
        base = SIZE_MAP.get(self._settings.size_mode, 260)
        return max(_ADAPTIVE_MIN, min(base, _ADAPTIVE_MAX))

    def _apply_size(self):
        """根据 settings.size_mode 调整小地图尺寸"""
        new_size = self._compute_adaptive_size()
        if new_size != self._size:
            self._size = new_size
            self._height = int(new_size * 0.75)
            self._minimap_canvas.configure(width=self._size, height=self._height)
            self._gear_btn.place(relx=1.0, y=2, x=-4, anchor="ne")
            self._user_positioned = False
            self.reposition()

    def _do_full_redraw(self):
        self._redraw_id = None
        if self._destroyed:
            return
        self.full_redraw()

    def _do_resize_redraw(self):
        """Resize 完成后的轻量刷新：先更新视口矩形，再延迟全量重绘。"""
        self._redraw_id = None
        if self._destroyed:
            return
        self.update_viewport()
        self._redraw_id = self._canvas.after(80, self._do_full_redraw)

    # ── 交互 ──────────────────────────────────────────────

    def _on_minimap_click(self, event: tk.Event):
        self._dragging_minimap = True
        self._clear_hover()
        self._pan_to_minimap(event.x, event.y)

    def _on_minimap_drag(self, event: tk.Event):
        if self._dragging_minimap:
            self._pan_to_minimap(event.x, event.y)

    def _on_minimap_release(self, event: tk.Event):
        self._dragging_minimap = False
        self._on_refresh_grid()

    def _on_minimap_motion(self, event: tk.Event):
        """悬停显示节点名称"""
        if self._dragging_minimap:
            return

        self._clear_hover()

        graph = self._get_graph()
        if not graph:
            return

        theme = current_theme()
        sm = scale_manager()

        font_size = sm.s(7)
        font = (theme.font_family, font_size)
        for node_id, (x1, y1, x2, y2) in reversed(self._node_rects.items()):
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                node = graph.get_node(node_id)
                if node:
                    desc = node.describe()
                    if len(desc) > 18:
                        desc = desc[:17] + "…"

                    text_w = self._estimate_text_width(desc, font_size) + 8
                    text_h = 12
                    tx = max(4, min(event.x + 8, self._size - text_w - 4))
                    ty = max(10, min(event.y - 10, self._height - text_h - 4))

                    self._hover_bg = self._minimap_canvas.create_rectangle(
                        tx - 2, ty - text_h / 2,
                        tx + text_w, ty + text_h / 2,
                        fill=theme.bg_surface, outline=theme.border_default,
                    )
                    self._hover_label = self._minimap_canvas.create_text(
                        tx, ty,
                        text=desc,
                        fill=theme.text_primary,
                        font=font,
                        anchor="w",
                    )
                break

    def _on_minimap_leave(self, event: tk.Event):
        self._clear_hover()

    def _clear_hover(self):
        mc = self._minimap_canvas
        if self._hover_label:
            mc.delete(self._hover_label)
            self._hover_label = None
        if self._hover_bg:
            mc.delete(self._hover_bg)
            self._hover_bg = None

    def _on_minimap_scroll(self, event: tk.Event):
        """鼠标滚轮缩放主画布"""
        if IS_MACOS:
            factor = 1.08 if event.delta > 0 else 1 / 1.08
        else:
            factor = 1.15 if event.delta > 0 else 1 / 1.15
        self._do_zoom(factor)

    def _do_zoom(self, factor: float):
        self._canvas.zoom_by(factor)

    def _pan_to_minimap(self, mx: float, my: float):
        """将主画布视口中心移动到小地图点击位置"""
        graph = self._get_graph()
        if not graph or not graph.nodes:
            return

        min_wx, min_wy, world_w, world_h, scale = self._get_bounds(graph)
        wx, wy = self._minimap_to_world(mx, my, min_wx, min_wy, scale)

        offset_x, offset_y, zoom = self._get_viewport()
        canvas_w = self._canvas.winfo_width()
        canvas_h = self._canvas.winfo_height()

        new_ox = wx - canvas_w / zoom / 2
        new_oy = wy - canvas_h / zoom / 2

        dx = (new_ox - offset_x) * zoom
        dy = (new_oy - offset_y) * zoom

        self._on_pan(-dx, -dy)
        self._on_refresh_grid()
        self.update_viewport()

    # ── 可见性 ────────────────────────────────────────────

    def show(self):
        self._apply_size()
        self.reposition()
        self.schedule_full_redraw()

    def is_shown(self) -> bool:
        return self._minimap_canvas.winfo_ismapped()

    def hide(self):
        self._minimap_canvas.place_forget()

    def toggle(self):
        """切换小地图显示/隐藏 (Alt+M)"""
        if self._minimap_canvas.winfo_ismapped():
            self.hide()
        else:
            self.show()

    def apply_theme(self):
        """主题切换时更新 canvas 和按钮配色"""
        theme = current_theme()
        self._minimap_canvas.configure(
            bg=theme.minimap_bg_panel,
            highlightbackground=theme.minimap_border,
        )
        self._gear_btn.configure(bg=theme.minimap_bg_panel, fg=theme.text_muted)
        self._drag_btn.configure(bg=theme.minimap_bg_panel, fg=theme.text_muted)
        self.full_redraw()

    def destroy(self):
        self._destroyed = True
        if self._redraw_id:
            self._canvas.after_cancel(self._redraw_id)
            self._redraw_id = None
        self._settings.destroy()
        self._node_items_cache.clear()
        self._edge_items_cache.clear()
        try:
            self._canvas.unbind("<Configure>", self._canvas_configure_id)
        except Exception:
            pass
        self._minimap_canvas.destroy()
