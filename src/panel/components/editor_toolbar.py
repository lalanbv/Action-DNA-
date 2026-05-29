"""通用编辑器工具栏构建器

为动作链页面和工作流页面提供一致的 toolbar 布局:
  导航(返回+标题) → 配置管理 → 循环控制 → 区域选择 → spacer → 运行控制
"""

import tkinter as tk
from typing import TYPE_CHECKING, Callable

from src.panel.canvas.theme import current_theme
from src.panel.components.loop_controls import LoopControls
from src.panel.components.profile_bar import ProfileBar
from src.panel.components.region_bar import RegionBar
from src.panel.components.toolbar import RunControls, ToolbarFrame
from src.panel.widgets import themed_label
from src.utils.i18n import t

if TYPE_CHECKING:
    from src.panel.pages.base_page import BasePage


def add_editor_toolbar_sections(
    toolbar: ToolbarFrame,
    *,
    title_text: str,
    on_back: Callable,
    profile_bar: ProfileBar,
    loop_controls: LoopControls,
    region_bar: RegionBar,
    run_controls: RunControls,
) -> None:
    """按标准顺序添加通用编辑器工具栏节。

    调用方在创建各组件后调用此函数，确保两个编辑器页面布局一致。
    额外的节（如动作链的 clear/status，工作流的 undo/debug）在调用后自行追加。
    """
    # 导航
    toolbar.make_button(
        "nav", text=t("common.back"), icon="back",
        command=on_back,
        tooltip=t("common.back"), shortcut_hint="Esc",
    )
    toolbar.add_widget(
        "nav", themed_label(toolbar, text=title_text, style="section"),
    )

    # 配置管理
    toolbar.add_section("profile")
    profile_bar.add_to_toolbar(toolbar, "profile")

    # 循环控制
    toolbar.add_section("loop")
    loop_controls.add_to_toolbar(toolbar, "loop")

    # 区域选择
    toolbar.add_section("region")
    region_bar.add_to_toolbar(toolbar, "region")

    # 弹性间隔（右对齐运行控制）
    toolbar.add_spacer()

    # 运行控制
    toolbar.add_section("run")
    run_controls.add_to_toolbar(toolbar, "run")
