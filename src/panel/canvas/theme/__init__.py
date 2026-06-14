"""CanvasTheme — 统一设计令牌系统（VS Code Dark+ / Light+ inspired）

此包是主题系统的模块化拆分，保持与原始 theme.py 完全向后兼容。
所有公开 API 通过此文件 re-export。
"""

# ── 令牌数据类 ──
from src.panel.canvas.theme.tokens import CanvasTheme

# ── 主题管理器（核心 API） ──
from src.panel.canvas.theme.theme_manager import (
    ThemeCallbackMixin,
    ThemeRegistry,
    Themeable,
    current_theme,
    current_theme_mode,
    on_theme_change,
    refresh_theme,
    remove_theme_change,
    resolved_theme_mode,
    restore_from_config,
    set_theme_mode,
    theme_registry,
)

# ── 系统主题同步编排（D1 去重 + B1 worker 线程） ──
from src.panel.canvas.theme.theme_sync import SystemThemeSync, ThemeSyncBackend

# ── 颜色工具 ──
from src.panel.canvas.theme.color_utils import (
    hex_to_rgb,
    hex_to_rgba,
    mix_colors,
    darken,
    lighten,
    desaturate,
)

# ── 节点/端口/边颜色映射 ──
from src.panel.canvas.theme.node_colors import (
    node_fill_color,
    node_border_color,
    port_fill_color,
    edge_color_by_label,
)

# ── 字体检测（高级用例） ──
from src.panel.canvas.theme.font_detection import (
    detect_font_family,
    detect_mono_font,
    build_font_kwargs,
)

__all__ = [
    # 令牌
    "CanvasTheme",
    # 管理器
    "ThemeCallbackMixin",
    "ThemeRegistry",
    "Themeable",
    "current_theme",
    "current_theme_mode",
    "on_theme_change",
    "refresh_theme",
    "remove_theme_change",
    "resolved_theme_mode",
    "restore_from_config",
    "set_theme_mode",
    "theme_registry",
    "SystemThemeSync",
    "ThemeSyncBackend",
    # 颜色工具
    "hex_to_rgb",
    "hex_to_rgba",
    "mix_colors",
    "darken",
    "lighten",
    "desaturate",
    # 节点颜色
    "node_fill_color",
    "node_border_color",
    "port_fill_color",
    "edge_color_by_label",
    # 字体
    "detect_font_family",
    "detect_mono_font",
    "build_font_kwargs",
]
