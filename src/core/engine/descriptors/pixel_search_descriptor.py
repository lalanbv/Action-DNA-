"""PixelSearchDescriptor — HSV/BGR 像素搜索描述符。

截图 → 像素颜色搜索 → 输出匹配位置到变量池。
支持 HSV 容差搜索、BGR 精确匹配、预定义颜色。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.core.engine.node_descriptor import NodeDescriptor, PortDef
from src.core.engine.node_registry import auto_register
from src.core.engine.node_result import NodeResult

if TYPE_CHECKING:
    from src.core.engine.execution_context import ExecutionContext

logger = logging.getLogger(__name__)

__all__ = ["PixelSearchDescriptor"]


@auto_register
class PixelSearchDescriptor(NodeDescriptor):
    """像素搜索描述符 — 在截图中搜索目标颜色像素。

    流程：截图 → 颜色搜索 → 输出匹配位置到变量池。
    通过 ExecutionContext.extra["pixel_searcher"] 注入 PixelSearcher。
    """

    @classmethod
    def action_type(cls) -> str:
        return "PIXEL_SEARCH"

    @classmethod
    def display_name(cls) -> str:
        return "像素搜索"

    @classmethod
    def category(cls) -> str:
        return "视觉检测"

    @classmethod
    def input_types(cls) -> dict[str, PortDef]:
        return {
            "target_color": PortDef(
                "string", "目标颜色 HSV (H,S,V) 或 BGR (B,G,R)",
                required=False, default=None,
            ),
            "color_tolerance": PortDef(
                "number", "颜色容差 (0~255)", required=False, default=10,
            ),
            "color_mode": PortDef(
                "string", "颜色模式: hsv | bgr | preset",
                required=False, default="hsv",
            ),
            "color_preset": PortDef(
                "string", "预定义颜色名 (red/green/blue/yellow/white/gray)",
                required=False, default="",
            ),
            "search_region": PortDef(
                "string", "搜索区域 (x,y,w,h) 或空=全图",
                required=False, default=None,
            ),
        }

    @classmethod
    def output_types(cls) -> dict[str, PortDef]:
        return {
            "found": PortDef("bool", "是否找到匹配像素", required=False),
            "position": PortDef("string", "第一个匹配位置 (x,y)", required=False),
            "count": PortDef("number", "匹配像素数量", required=False),
        }

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        action = ctx.current_node.action
        if action is None:
            return NodeResult.fail("PIXEL_SEARCH 节点缺少步骤配置")

        pixel_searcher = ctx.extra.get("pixel_searcher")
        if pixel_searcher is None:
            return NodeResult.fail("PixelSearcher 未注入到 ExecutionContext.extra")

        step = action  # type: PixelSearchStep  — 由 action_type() 约束
        screenshot = ctx.capture.grab()
        region = step.search_region
        mode = step.color_mode

        if mode == "preset" and step.color_preset:
            result = pixel_searcher.search_preset(screenshot, step.color_preset, region)
        elif mode == "bgr" and step.target_color:
            result = pixel_searcher.match_bgr_exact(screenshot, step.target_color, region)
        elif step.target_color:
            result = pixel_searcher.search(
                screenshot, step.target_color,
                tolerance=step.color_tolerance, region=region,
            )
        else:
            return NodeResult.fail("未指定目标颜色 (target_color) 或颜色预设 (color_preset)")

        output: dict[str, object] = {
            "found": result.found,
            "count": result.count,
        }
        if result.first is not None:
            output["position"] = result.first

        if result.found:
            logger.info(
                "像素搜索找到 %d 个匹配点，首个位置: %s",
                result.count, result.first,
            )
        else:
            logger.info("像素搜索未找到匹配像素")

        return NodeResult.ok(**output)
