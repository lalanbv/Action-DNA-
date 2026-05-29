"""NodeRenderer — 分段式卡片节点渲染器 (Phase 2)

节点结构:
+──── Header (强调色背景, 24px) ──────+
│  ⚡  Click Enemy (标题, 10pt bold)   │
+──── Body (深色表面, 36px) ──────────+
│  模板匹配 · 点击 (类型描述, 8pt)     │
+──── Port Strip (12px) ──────────────+
│  ●(in)                    ●(out)    │
+─────────────────────────────────────+
"""

import math
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Literal

import tkinter as tk
import tkinter.font as tkFont

from src.core.flow import FlowNode
from src.panel.canvas.node_shared import (
    CORNER_RADIUS,
    FONT_BOLD,
    LOD_FULL,
    LOD_MINIMAL,
    LOD_SIMPLIFIED,
    PORT_RADIUS,
    PORT_VISUAL_RADIUS,
    TAG_PORT,
    TAG_PORT_IN,
    TAG_PORT_IN_ARROW,
    TAG_PORT_OUT,
    TAG_PORT_OUT_ARROW,
    TAG_SELECTABLE,
    TAG_SELECTION_RING,
    NODE_SPECS as _NODE_SPECS,
    NODE_ICONS as _NODE_ICONS,
    node_spec as _node_spec,
    node_intersects_rect,
    node_size,
    port_label as _port_label,
    port_positions,
    type_label as _type_label,
    lod_level as _lod_level,
    body_text_lines as _body_text_lines,
)
from src.panel.canvas.theme import (
    current_theme,
    mix_colors,
    desaturate,
    node_fill_color,
    node_border_color,
    port_fill_color,
)


# ── tkinter-only 常量 ──────────────────────────────────────
SHADOW_OFFSET = 4

# ── 字体缓存 (避免 tkFont.Font 泄漏) ─────────────────────────
_font_cache: dict[tuple[str, int, Literal["normal", "bold"]], tkFont.Font] = {}


def _get_cached_font(family: str, size: int, weight: Literal["normal", "bold"]) -> tkFont.Font:
    key = (family, size, weight)
    if key not in _font_cache:
        _font_cache[key] = tkFont.Font(family=family, size=size, weight=weight)
    return _font_cache[key]


_ARC_STEPS = 10


def _arc_points(cx: float, cy: float, r: float, start_angle: float) -> list[float]:
    """Generate polygon points for a 90° arc starting at *start_angle*."""
    pts: list[float] = []
    for i in range(1, _ARC_STEPS + 1):
        a = start_angle + math.pi / 2 * i / _ARC_STEPS
        pts.append(cx + r * math.cos(a))
        pts.append(cy + r * math.sin(a))
    return pts


@lru_cache(maxsize=128)
def _rounded_rect_coords(
    x: float, y: float, w: float, h: float, r: float
) -> list[float]:
    """生成近似圆角矩形的 polygon 坐标点"""
    if r > w / 2:
        r = w / 2
    if r > h / 2:
        r = h / 2
    pts: list[float] = []
    pts += [x + r, y, x + w - r, y]
    pts += _arc_points(x + w - r, y + r, r, -math.pi / 2)
    pts += [x + w, y + h - r]
    pts += _arc_points(x + w - r, y + h - r, r, 0)
    pts += [x + r, y + h]
    pts += _arc_points(x + r, y + h - r, r, math.pi / 2)
    pts += [x, y + r]
    pts += _arc_points(x + r, y + r, r, math.pi)
    return pts


@lru_cache(maxsize=64)
def _header_clip_coords(
    x: float, y: float, w: float, header_h: float, r: float
) -> list[float]:
    """只有顶部两角圆角的 header 区域 polygon 坐标"""
    if r > w / 2:
        r = w / 2
    pts: list[float] = []
    pts += [x + r, y, x + w - r, y]
    pts += _arc_points(x + w - r, y + r, r, -math.pi / 2)
    pts += [x + w, y + header_h, x, y + header_h, x, y + r]
    pts += _arc_points(x + r, y + r, r, math.pi)
    return pts


# ── 向后兼容别名 ─────────────────────────────────────────

NODE_WIDTH = 200
NODE_HEIGHT = 72
CONDITION_WIDTH = 220
CONDITION_HEIGHT = 80
LOOP_WIDTH = 220
LOOP_HEIGHT = 80


@dataclass
class NodeCanvasItems:
    """一个节点在 canvas 上的所有图形元素 ID"""

    body: int = 0
    header: int = 0
    shadow: int = 0
    shadow_outer: int = 0
    title: int = 0
    type_label: int = 0
    summary: int = 0
    icon: int = 0
    selection_ring_glow: int = 0
    selection_ring: int = 0
    disabled_overlay: int = 0
    disabled_badge: int = 0
    # 端口: {label: canvas_item_id}
    ports_in: dict[str, int] = field(default_factory=dict)
    ports_out: dict[str, int] = field(default_factory=dict)
    # 端口方向指示箭头: {label: canvas_item_id}
    port_arrows: dict[str, int] = field(default_factory=dict)
    # 端口标签: {label: canvas_item_id}
    port_labels: dict[str, int] = field(default_factory=dict)
    port_label_bgs: dict[str, int] = field(default_factory=dict)


def node_color(node: FlowNode) -> str:
    return node_fill_color(node.node_type)


def node_border(node: FlowNode) -> str:
    return node_border_color(node.node_type)


def render_node(
    canvas: tk.Canvas,
    node: FlowNode,
    offset_x: float,
    offset_y: float,
    zoom: float,
    theme=None,
) -> NodeCanvasItems:
    """绘制分段式卡片节点"""

    if theme is None:
        theme = current_theme()
    items = NodeCanvasItems()
    lod = _lod_level(zoom)
    w, h, header_h, body_h, *_ = _node_spec(node)
    accent = node_fill_color(node.node_type)
    accent_dim = node_border_color(node.node_type)
    disabled = not node.enabled

    if disabled:
        accent = desaturate(accent, 0.55)
        accent_dim = desaturate(accent_dim, 0.55)

    # 世界坐标 → 屏幕坐标
    sx = (node.pos_x - offset_x) * zoom
    sy = (node.pos_y - offset_y) * zoom
    sw = w * zoom
    sh = h * zoom
    s_header_h = header_h * zoom
    s_body_h = body_h * zoom
    cr = max(2, CORNER_RADIUS * zoom)

    tag = f"node:{node.node_id}"

    # ── 选择环 (外层辉光) ──
    glow_pad = theme.selection_ring_glow_pad
    glow_coords = _rounded_rect_coords(
        sx - glow_pad, sy - glow_pad, sw + 2 * glow_pad, sh + 2 * glow_pad,
        cr + glow_pad,
    )
    items.selection_ring_glow = canvas.create_polygon(
        *glow_coords,
        fill="", outline="", width=4, smooth=False,
        tags=(tag, TAG_SELECTABLE, TAG_SELECTION_RING),
    )

    # ── 选择环 (内层实线) ──
    ring_pad = 3
    ring_coords = _rounded_rect_coords(
        sx - ring_pad, sy - ring_pad, sw + 2 * ring_pad, sh + 2 * ring_pad,
        cr + ring_pad,
    )
    items.selection_ring = canvas.create_polygon(
        *ring_coords,
        fill="", outline="", width=2, smooth=False,
        tags=(tag, TAG_SELECTABLE, TAG_SELECTION_RING),
    )

    # ── 阴影（双层渐变，LOD simplified/minimal 时跳过）──
    if lod == LOD_FULL:
        outer_offset = SHADOW_OFFSET + 2
        outer_color = mix_colors(theme.bg_primary, theme.shadow_color, theme.shadow_outer_alpha)
        shadow_outer_coords = _rounded_rect_coords(
            sx + outer_offset, sy + outer_offset, sw, sh, cr,
        )
        items.shadow_outer = canvas.create_polygon(
            *shadow_outer_coords,
            fill=outer_color, outline="", smooth=False,
            tags=(tag,),
        )
        inner_color = mix_colors(theme.bg_primary, theme.shadow_color, theme.shadow_inner_alpha)
        shadow_coords = _rounded_rect_coords(
            sx + SHADOW_OFFSET, sy + SHADOW_OFFSET, sw, sh, cr,
        )
        items.shadow = canvas.create_polygon(
            *shadow_coords,
            fill=inner_color, outline="", smooth=False,
            tags=(tag,),
        )

    # ── 节点主体 (Body + PortStrip 背景) ──
    body_coords = _rounded_rect_coords(sx, sy, sw, sh, cr)
    items.body = canvas.create_polygon(
        *body_coords,
        fill=theme.bg_surface, outline=accent_dim,
        width=max(1, int(1.5 * zoom)),
        dash=(4, 2) if disabled else (),
        smooth=False,
        tags=(tag, TAG_SELECTABLE),
    )

    # ── Header 区域 (强调色填充，顶部圆角) ──
    header_coords = _header_clip_coords(sx, sy, sw, s_header_h, cr)
    items.header = canvas.create_polygon(
        *header_coords,
        fill=accent, outline="",
        smooth=False,
        tags=(tag, TAG_SELECTABLE),
    )

    # ── Header 图标 (LOD simplified 以下跳过) ──
    if lod != LOD_MINIMAL:
        icon_char = _NODE_ICONS.get(node.node_type, "")
        icon_size = max(8, int(10 * zoom))
        items.icon = canvas.create_text(
            sx + 10 * zoom, sy + s_header_h / 2,
            text=icon_char, fill=theme.text_on_accent_bright,
            font=(theme.font_family, icon_size, FONT_BOLD),
            anchor="w",
            tags=(tag, TAG_SELECTABLE),
        )

    # ── Header 标题 ──
    desc = node.describe()
    max_len = 8 if lod == LOD_MINIMAL else 22
    if len(desc) > max_len:
        desc = desc[:max_len - 1] + "…"
    title_size = max(7, int(10 * zoom))
    title_x = sx + 10 * zoom if lod == LOD_MINIMAL else sx + 24 * zoom
    items.title = canvas.create_text(
        title_x, sy + s_header_h / 2,
        text=desc,
        fill=theme.text_on_accent_bright if not disabled else theme.text_muted,
        font=(theme.font_family, title_size, FONT_BOLD),
        anchor="w",
        tags=(tag, TAG_SELECTABLE),
    )

    # ── Body 文本 ──
    line1, line2 = _body_text_lines(node)

    if body_h > 20 and lod in (LOD_FULL, LOD_SIMPLIFIED):
        label_size = max(7, int(8 * zoom))
        items.type_label = canvas.create_text(
            sx + 10 * zoom, sy + s_header_h + s_body_h * 0.32,
            text=line1,
            fill=theme.text_secondary if not disabled else theme.text_muted,
            font=(theme.font_family, label_size, FONT_BOLD),
            anchor="w",
            tags=(tag, TAG_SELECTABLE),
        )

    if body_h >= 40 and lod == LOD_FULL and line2:
        summary_size = max(6, int(7 * zoom))
        items.summary = canvas.create_text(
            sx + 10 * zoom, sy + s_header_h + s_body_h * 0.68,
            text=line2,
            fill=theme.text_muted,
                font=(theme.font_family, summary_size),
                anchor="w",
                tags=(tag, TAG_SELECTABLE),
            )

    # ── 端口 ──
    # 输入端口: 菱形轮廓（空心）+ 向内箭头 ▼ (上方, 数据流入)
    # 输出端口: 实心圆 + 向外箭头 ▼ (下方, 数据流出)
    ports = port_positions(node)
    for label, (wx, wy) in ports.items():
        px = (wx - offset_x) * zoom
        py = (wy - offset_y) * zoom
        vr = PORT_VISUAL_RADIUS * zoom  # 可见半径

        if label == "in":
            # 可见菱形轮廓（空心）
            d = vr
            diamond_coords = [px, py - d, px + d, py, px, py + d, px - d, py]
            item_id = canvas.create_polygon(
                *diamond_coords,
                fill=theme.bg_surface, outline=theme.port_in_outline, width=max(1.5, 2 * zoom),
                tags=(tag, f"port:{node.node_id}:in", TAG_PORT, TAG_PORT_IN),
            )
            items.ports_in[label] = item_id
            # 方向指示 ▼ (指向节点内部)
            if lod != LOD_MINIMAL:
                arrow_r = max(2, 2.5 * zoom)
                aid = canvas.create_polygon(
                    px - arrow_r, py - arrow_r * 0.5,
                    px + arrow_r, py - arrow_r * 0.5,
                    px, py + arrow_r,
                    fill=theme.port_in_outline, outline="",
                    tags=(tag, f"port:{node.node_id}:in", TAG_PORT, TAG_PORT_IN_ARROW),
                )
                items.port_arrows[label] = aid
        else:
            port_color = port_fill_color(label, theme)
            # 可见实心圆
            item_id = canvas.create_oval(
                px - vr, py - vr, px + vr, py + vr,
                fill=port_color, outline=theme.port_out_outline, width=max(1, 1.5 * zoom),
                tags=(tag, f"port:{node.node_id}:{label}", TAG_PORT, TAG_PORT_OUT),
            )
            items.ports_out[label] = item_id
            # 方向指示 ▼ (指向节点外部)
            if lod != LOD_MINIMAL:
                arrow_r = max(2, 2.5 * zoom)
                aid = canvas.create_polygon(
                    px - arrow_r, py + arrow_r * 0.5,
                    px + arrow_r, py + arrow_r * 0.5,
                    px, py - arrow_r,
                    fill=port_color, outline="",
                    tags=(tag, f"port:{node.node_id}:{label}", TAG_PORT, TAG_PORT_OUT_ARROW),
                )
                items.port_arrows[label] = aid

            # 端口标签 (仅 full LOD)
            if lod == LOD_FULL:
                short = _port_label(node.node_type, label)
                if short:
                    label_font_size = max(7, int(8 * zoom))
                    font_obj = _get_cached_font(theme.font_family, label_font_size, FONT_BOLD)
                    text_w = font_obj.measure(short) + 8 * zoom
                    text_h = 10 * zoom
                    label_y = py + vr + 2 * zoom + text_h / 2
                    lbl_bg = canvas.create_rectangle(
                        px - text_w / 2, label_y - text_h / 2,
                        px + text_w / 2, label_y + text_h / 2,
                        fill=port_color, outline="",
                        tags=(tag, f"port_label:{node.node_id}:{label}"),
                    )
                    lbl_id = canvas.create_text(
                        px, label_y,
                        text=short, fill=theme.text_on_accent_bright,
                        font=(theme.font_family, label_font_size, FONT_BOLD),
                        tags=(tag, f"port_label:{node.node_id}:{label}"),
                    )
                    items.port_labels[label] = lbl_id
                    items.port_label_bgs[label] = lbl_bg

    # ── 禁用标识 ──
    if disabled:
        badge_r = max(7, int(9 * zoom))
        badge_cx = sx + sw - badge_r - 2
        badge_cy = sy + badge_r + 2
        items.disabled_badge = canvas.create_oval(
            badge_cx - badge_r, badge_cy - badge_r,
            badge_cx + badge_r, badge_cy + badge_r,
            fill=theme.accent_red, outline=theme.accent_red_dim, width=1,
            tags=(tag,),
        )
        items.disabled_overlay = canvas.create_text(
            badge_cx, badge_cy,
            text="×", fill=theme.text_on_accent_bright,
            font=(theme.font_family, max(7, int(9 * zoom)), FONT_BOLD),
            tags=(tag,),
        )

    return items


def update_node_position(
    canvas: tk.Canvas,
    items: NodeCanvasItems,
    node: FlowNode,
    offset_x: float,
    offset_y: float,
    zoom: float,
    theme=None,
) -> None:
    """增量更新节点位置（拖拽时用）"""
    if theme is None:
        theme = current_theme()
    w, h, header_h, body_h, *_ = _node_spec(node)
    sx = (node.pos_x - offset_x) * zoom
    sy = (node.pos_y - offset_y) * zoom
    sw = w * zoom
    sh = h * zoom
    s_header_h = header_h * zoom
    s_body_h = body_h * zoom
    cr = max(2, CORNER_RADIUS * zoom)

    # 更新选择环
    glow_pad = theme.selection_ring_glow_pad
    glow_coords = _rounded_rect_coords(
        sx - glow_pad, sy - glow_pad, sw + 2 * glow_pad, sh + 2 * glow_pad,
        cr + glow_pad,
    )
    canvas.coords(items.selection_ring_glow, *glow_coords)

    ring_pad = 3
    ring_coords = _rounded_rect_coords(
        sx - ring_pad, sy - ring_pad, sw + 2 * ring_pad, sh + 2 * ring_pad,
        cr + ring_pad,
    )
    canvas.coords(items.selection_ring, *ring_coords)

    # 更新阴影（LOD simplified/minimal 时 shadow 不存在，guard 防止 TclError）
    outer_offset = SHADOW_OFFSET + 2
    if items.shadow_outer:
        shadow_outer_coords = _rounded_rect_coords(
            sx + outer_offset, sy + outer_offset, sw, sh, cr,
        )
        canvas.coords(items.shadow_outer, *shadow_outer_coords)
    if items.shadow:
        shadow_coords = _rounded_rect_coords(
            sx + SHADOW_OFFSET, sy + SHADOW_OFFSET, sw, sh, cr,
        )
        canvas.coords(items.shadow, *shadow_coords)

    # 更新主体
    body_coords = _rounded_rect_coords(sx, sy, sw, sh, cr)
    canvas.coords(items.body, *body_coords)

    # 更新 header
    header_coords = _header_clip_coords(sx, sy, sw, s_header_h, cr)
    canvas.coords(items.header, *header_coords)

    lod = _lod_level(zoom)

    # 更新图标位置 + 字体大小
    if items.icon:
        canvas.coords(items.icon, sx + 10 * zoom, sy + s_header_h / 2)
        icon_size = max(8, int(10 * zoom))
        canvas.itemconfigure(items.icon, font=(theme.font_family, icon_size, FONT_BOLD))

    # 更新标题位置 + 字体大小
    if items.title:
        title_x = sx + 10 * zoom if lod == LOD_MINIMAL else sx + 24 * zoom
        canvas.coords(items.title, title_x, sy + s_header_h / 2)
        title_size = max(7, int(10 * zoom))
        canvas.itemconfigure(items.title, font=(theme.font_family, title_size, FONT_BOLD))

    # 更新类型标签位置 + 字体大小
    if items.type_label and body_h > 20:
        canvas.coords(items.type_label, sx + 10 * zoom, sy + s_header_h + s_body_h * 0.32)
        label_size = max(7, int(8 * zoom))
        canvas.itemconfigure(items.type_label, font=(theme.font_family, label_size, FONT_BOLD))

    # 更新摘要行位置 + 字体大小
    if items.summary and body_h >= 40:
        canvas.coords(items.summary, sx + 10 * zoom, sy + s_header_h + s_body_h * 0.68)
        summary_size = max(6, int(7 * zoom))
        canvas.itemconfigure(items.summary, font=(theme.font_family, summary_size))

    # 更新禁用徽标
    if items.disabled_badge or items.disabled_overlay:
        badge_r = max(7, int(9 * zoom))
        badge_cx = sx + sw - badge_r - 2
        badge_cy = sy + badge_r + 2
        if items.disabled_badge:
            canvas.coords(items.disabled_badge,
                           badge_cx - badge_r, badge_cy - badge_r,
                           badge_cx + badge_r, badge_cy + badge_r)
        if items.disabled_overlay:
            canvas.coords(items.disabled_overlay, badge_cx, badge_cy)
        canvas.itemconfigure(
            items.disabled_overlay,
            font=(theme.font_family, max(7, int(9 * zoom)), FONT_BOLD),
        )

    # 更新端口和标签位置 + 字体大小
    ports = port_positions(node)
    for label, (wx, wy) in ports.items():
        px = (wx - offset_x) * zoom
        py = (wy - offset_y) * zoom
        vr = PORT_VISUAL_RADIUS * zoom

        if label == "in" and label in items.ports_in:
            # 菱形: 更新 polygon 坐标
            d = vr
            diamond_coords = [px, py - d, px + d, py, px, py + d, px - d, py]
            canvas.coords(items.ports_in[label], *diamond_coords)
            if label in items.port_arrows:
                arrow_r = max(2, 2.5 * zoom)
                canvas.coords(
                    items.port_arrows[label],
                    px - arrow_r, py - arrow_r * 0.5,
                    px + arrow_r, py - arrow_r * 0.5,
                    px, py + arrow_r,
                )
        elif label in items.ports_out:
            # 圆形: 更新 oval 坐标
            canvas.coords(items.ports_out[label], px - vr, py - vr, px + vr, py + vr)
            if label in items.port_arrows:
                arrow_r = max(2, 2.5 * zoom)
                canvas.coords(
                    items.port_arrows[label],
                    px - arrow_r, py + arrow_r * 0.5,
                    px + arrow_r, py + arrow_r * 0.5,
                    px, py - arrow_r,
                )

        if label in items.port_labels:
            label_font_size = max(7, int(8 * zoom))
            text_h = 10 * zoom
            label_y = py + vr + 2 * zoom + text_h / 2
            short = _port_label(node.node_type, label)
            if label in items.port_label_bgs:
                if short:
                    font_obj = _get_cached_font(theme.font_family, label_font_size, FONT_BOLD)
                    text_w = font_obj.measure(short) + 8 * zoom
                else:
                    text_w = 20 * zoom
                canvas.coords(
                    items.port_label_bgs[label],
                    px - text_w / 2, label_y - text_h / 2,
                    px + text_w / 2, label_y + text_h / 2,
                )
            canvas.coords(items.port_labels[label], px, label_y)
            canvas.itemconfigure(
                items.port_labels[label],
                font=(theme.font_family, label_font_size, FONT_BOLD),
            )
