"""深色主题构建器"""

from src.panel.canvas.theme.tokens import CanvasTheme
from src.panel.canvas.theme.font_detection import build_font_kwargs


def build_dark_theme(family: str, mono: str, sf) -> CanvasTheme:
    """构建深色主题（VS Code Dark+ inspired）"""
    return CanvasTheme(**build_font_kwargs(family, mono, sf))
