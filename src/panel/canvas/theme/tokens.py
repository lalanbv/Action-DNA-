"""CanvasTheme — 统一设计令牌（纯数据，VS Code Dark+ / Light+ inspired）"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CanvasTheme:
    """画布设计令牌 — 所有颜色、字体、间距集中管理"""

    # ── 背景 ──
    bg_primary: str = "#1e1e1e"
    bg_secondary: str = "#181818"
    bg_surface: str = "#2d2d2d"
    bg_surface_hover: str = "#383838"
    bg_surface_dark: str = "#2d2d2d"
    bg_overlay: str = "#111111"

    # ── 文本 ──
    text_primary: str = "#e0e0e0"
    text_secondary: str = "#bfbfbf"
    text_muted: str = "#999999"
    text_on_accent: str = "#ffffff"
    text_on_accent_bright: str = "#1e1e1e"

    # ── 强调色 (节点类型) ──
    accent_blue: str = "#0078d4"
    accent_blue_dim: str = "#005a9e"
    accent_green: str = "#4ec9b0"
    accent_green_dim: str = "#3a9a80"
    accent_red: str = "#f44747"
    accent_red_dim: str = "#c43030"
    accent_orange: str = "#d4a056"
    accent_orange_dim: str = "#a07840"
    accent_mauve: str = "#c586c0"
    accent_mauve_dim: str = "#9a5a90"
    accent_gray: str = "#808080"
    accent_gray_dim: str = "#606060"
    accent_teal: str = "#4ec9b0"
    accent_yellow: str = "#dcdcaa"
    accent_pink: str = "#c586c0"
    accent_warning: str = "#d4a056"
    accent_info: str = "#0078d4"

    # ── 边框 ──
    border_default: str = "#3c3c3c"
    border_selected: str = "#0078d4"
    border_hover: str = "#1a8ce8"

    # ── 边辉光 ──
    edge_glow_layer_count: int = 3
    edge_hover_glow_alphas: tuple[float, ...] = (0.15, 0.30, 0.50)
    edge_selected_glow_alphas: tuple[float, ...] = (0.20, 0.40, 0.65)
    edge_selected_dash: tuple[int, ...] = (8, 4)

    # ── 选择环 ──
    selection_ring_glow_pad: int = 6
    selection_ring_glow_alpha: float = 0.35

    # ── 拖拽 ──
    drag_shadow_lift_alpha: float = 0.30
    snap_anim_frames: int = 8
    snap_anim_interval_ms: int = 15

    # ── 端口 ──
    port_in_fill: str = "#e0e0e0"
    port_in_outline: str = "#0078d4"
    port_out_outline: str = "#3c3c3c"
    port_in_glow: str = "#0078d4"
    port_out_glow: str = "#e0e0e0"

    # ── 阴影 ──
    shadow_color: str = "#181818"
    shadow_outer_alpha: float = 0.35
    shadow_inner_alpha: float = 0.65

    # ── 网格 ──
    grid_dot: str = "#3c3c3c"
    grid_dot_sub: str = "#252525"
    grid_line: str = "#252525"

    # ── 选择框 ──
    selection_box: str = "#0078d4"
    selection_box_stipple: str = "gray12"
    region_dim_color: str = "#000000"
    region_dim_stipple: str = "gray50"

    # ── 小地图 ──
    minimap_bg: str = "#181818"
    minimap_bg_panel: str = "#141414"
    minimap_viewport: str = "#0078d4"
    minimap_viewport_shadow: str = "#0a0a0a"
    minimap_border: str = "#4a4a4a"
    minimap_edge: str = "#3c3c3c"
    minimap_node_body: str = "#3c3c3c"

    # ── 边颜色 ──
    edge_default: str = "#0078d4"
    edge_true: str = "#4ec9b0"
    edge_false: str = "#f44747"
    edge_loop: str = "#4ec9b0"
    edge_timeout: str = "#dcdcaa"
    edge_exit: str = "#4ec9b0"
    # 边端点手柄: source (尾) 圆形 / target (头) 菱形
    edge_source_handle: str = "#808080"
    edge_target_handle: str = "#e0e0e0"

    # ── 执行状态 ──
    status_running: str = "#4ec9b0"
    status_success: str = "#4ec9b0"
    status_paused: str = "#dcdcaa"
    status_error: str = "#f44747"
    status_ready: str = "#808080"

    # ── 工具栏/面板 ──
    toolbar_bg: str = "#181818"
    panel_bg: str = "#1e1e1e"
    panel_header_bg: str = "#181818"
    toolbar_secondary_bg: str = "#1a1a1a"
    panel_accent_border: str = "#0078d4"

    # ── 页面/对话框 ──
    page_bg: str = "#1e1e1e"
    card_bg: str = "#2d2d2d"
    dialog_bg: str = "#252526"
    input_bg: str = "#3c3c3c"
    input_fg: str = "#e0e0e0"
    separator_color: str = "#3c3c3c"
    success_color: str = "#4ec9b0"
    warning_color: str = "#dcdcaa"
    danger_color: str = "#f44747"

    # ── 控件状态 ──
    btn_bg: str = "#3c3c3c"
    btn_bg_hover: str = "#505050"
    btn_border: str = "#6a6a6a"
    btn_disabled_bg: str = "#333333"
    btn_disabled_fg: str = "#666666"
    row_stripe_bg: str = "#282828"
    border_strong: str = "#5c5c5c"

    # ── 区域分隔 ──
    zone_border: str = "#4a4a4a"
    breadcrumb_bg: str = "#1a1a1a"
    empty_state_icon: str = "#555555"
    hover_highlight: str = "#383838"

    # ── 字体 ──
    font_family: str = "Arial"
    font_node_title: tuple = (None, 10, "bold")
    font_node_subtitle: tuple = (None, 8)
    font_node_type_label: tuple = (None, 7)
    font_port_label: tuple = (None, 7)
    font_edge_label: tuple = (None, 9, "bold")
    font_toolbar: tuple = (None, 9)
    font_status: tuple = (None, 8)

    # ── 页面字体 ──
    font_page_title: tuple = (None, 20, "bold")
    font_section_title: tuple = (None, 13, "bold")
    font_dialog_title: tuple = (None, 14, "bold")
    font_body: tuple = (None, 10)
    font_small: tuple = (None, 8)
    font_mono: tuple = (None, 10)

    # ── 间距 (px) ──
    grid_spacing: int = 24
    node_padding_h: int = 12
    node_padding_v: int = 8
    toolbar_height: int = 36
    panel_width_left: int = 220
    panel_width_right: int = 260
    minimap_size: int = 280
    minimap_margin: int = 12

    # ── 通用 UI 尺寸 ──
    tree_row_height: int = 26
    tree_min_height: int = 6
    button_height: int = 30
    log_height: int = 5
    header_pady: tuple = (16, 4)
    section_pady: tuple = (8, 8)

    # ── 间距常量 ──
    pad_xs: int = 4
    pad_sm: int = 8
    pad_md: int = 12
    pad_lg: int = 16
    pad_xl: int = 24
    breadcrumb_height: int = 24
