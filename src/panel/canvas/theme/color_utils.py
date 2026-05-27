"""颜色工具函数 — 混合/变暗/变亮/hex解析"""


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Parse #RRGGBB to (r, g, b)."""
    return int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)


def mix_colors(bg: str, fg: str, alpha: float) -> str:
    """将 fg 以 alpha 比例混合到 bg 上（模拟半透明）

    Tkinter 不支持 #RRGGBBAA，此函数预计算混合后的不透明颜色。
    """
    br, bg_, bb = hex_to_rgb(bg)
    fr, fg_, fb = hex_to_rgb(fg)
    r = max(0, min(255, int(br + (fr - br) * alpha)))
    g = max(0, min(255, int(bg_ + (fg_ - bg_) * alpha)))
    b = max(0, min(255, int(bb + (fb - bb) * alpha)))
    return f"#{r:02x}{g:02x}{b:02x}"


def darken(color: str, factor: float = 0.3) -> str:
    """将颜色向黑色混合 (factor=0.3 → 30% 暗)"""
    return mix_colors("#000000", color, 1.0 - factor)


def lighten(color: str, factor: float = 0.3) -> str:
    """将颜色向白色混合 (factor=0.3 → 30% 亮)"""
    return mix_colors("#ffffff", color, 1.0 - factor)


def hex_to_rgba(hex_color: str, alpha: float) -> str:
    """Convert #RRGGBB to rgba(r, g, b, a) — for QSS/CSS usage."""
    r, g, b = hex_to_rgb(hex_color)
    return f"rgba({r}, {g}, {b}, {alpha})"


def desaturate(hex_color: str, factor: float = 0.5) -> str:
    """将颜色与感知亮度灰度进行去饱和处理（ITU-R BT.601）。"""
    r, g, b = hex_to_rgb(hex_color)
    gray = int(0.299 * r + 0.587 * g + 0.114 * b)
    dr = max(0, min(255, int(r + (gray - r) * factor)))
    dg = max(0, min(255, int(g + (gray - g) * factor)))
    db = max(0, min(255, int(b + (gray - b) * factor)))
    return f"#{dr:02x}{dg:02x}{db:02x}"
