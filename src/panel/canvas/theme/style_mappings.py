"""Shared style mappings for themed widgets.

Both tkinter and Qt backends import from this module to avoid duplicating
style constants and pure helper functions.
"""

from __future__ import annotations

from typing import Literal

from src.panel.canvas.theme.color_utils import hex_to_rgb


LabelStyle = Literal["title", "section", "subtitle", "dialog_title", "body", "small", "mono"]
ButtonStyle = Literal["primary", "secondary", "danger"]

_STYLE_FONTS: dict[str, str] = {
    "title": "font_page_title",
    "section": "font_section_title",
    "subtitle": "font_node_subtitle",
    "dialog_title": "font_dialog_title",
    "body": "font_body",
    "small": "font_small",
    "mono": "font_mono",
}

_BUTTON_STYLES: dict[ButtonStyle, dict[str, str]] = {
    "primary": {"bg_prop": "accent_blue", "fg_prop": "text_on_accent"},
    "secondary": {"bg_prop": "btn_bg", "fg_prop": "text_primary"},
    "danger": {"bg_prop": "danger_color", "fg_prop": "text_on_accent"},
}


def resolve_font(theme: object, style: str = "body") -> tuple:
    """Resolve a named style to a font tuple from the theme."""
    return getattr(theme, _STYLE_FONTS.get(style, "font_body"))


def derive_hover_bg(hex_color: str, factor: float = 0.18) -> str:
    """Derive hover color from background. Lightens dark colors, darkens light."""
    try:
        r, g, b = hex_to_rgb(hex_color)
    except (ValueError, IndexError):
        return hex_color
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    if luminance > 128:
        nr, ng, nb = (
            max(0, int(c * (1 - factor))) for c in (r, g, b)
        )
    else:
        nr, ng, nb = (
            min(255, int(c + (255 - c) * factor)) for c in (r, g, b)
        )
    return f"#{nr:02x}{ng:02x}{nb:02x}"
