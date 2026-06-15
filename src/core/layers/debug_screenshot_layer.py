"""DebugScreenshotLayer — 节点执行失败时保存调试截图和模板。

从 ActionExecutor._save_debug_screenshot() 迁移而来，作为 GraphLayer
中间件插入 GraphEngine 管道。
"""

from __future__ import annotations

import logging
import os
import shutil
import time
from typing import TYPE_CHECKING

from src.core.engine.priority import SystemPriority
from src.core.layers.layer import ErrorContext, GraphLayer
from src.utils.i18n import t

if TYPE_CHECKING:
    from src.core.engine.execution_context import ExecutionContext

logger = logging.getLogger(__name__)

__all__ = ["DebugScreenshotLayer"]


class DebugScreenshotLayer(GraphLayer):
    """节点首次错误时保存调试截图和模板到 assets/logs/。

    仅保存一次（每轮执行），避免磁盘写入压力。
    """

    def __init__(self, capture, log_dir: str) -> None:
        self._capture = capture
        self._log_dir = log_dir
        self._saved_nodes: set[str] = set()

    @property
    def name(self) -> str:
        return "debug_screenshot"

    @property
    def priority(self) -> int:
        return SystemPriority.POST_PROCESS

    def on_graph_start(self, ctx: ExecutionContext) -> None:
        self._saved_nodes.clear()

    def on_node_error(
        self,
        ctx: ExecutionContext,
        err_ctx: ErrorContext,
    ) -> ErrorContext:
        node = ctx.current_node
        if node is None or node.action is None:
            return err_ctx

        if node.node_id in self._saved_nodes:
            return err_ctx

        image_path = getattr(node.action, "image_path", "")
        if not image_path:
            return err_ctx

        self._saved_nodes.add(node.node_id)
        self._save_debug_screenshot(image_path)
        err_ctx.actions.append(f"debug_screenshot:{node.node_id}")
        return err_ctx

    def _save_debug_screenshot(self, template_path: str) -> None:
        """保存调试截图和模板到日志目录"""
        try:
            import cv2
        except ImportError:
            return

        try:
            os.makedirs(self._log_dir, exist_ok=True)

            screen = self._capture.grab_reuse()
            if screen is None:
                screen = self._capture.grab()
            ts = time.strftime("%Y%m%d_%H%M%S")
            ss_path = os.path.join(self._log_dir, f"debug_screen_{ts}.png")
            cv2.imencode('.png', screen)[1].tofile(ss_path)
            logger.info(t("layers.log.debug_shot_saved", path=ss_path))

            if os.path.exists(template_path):
                tpl_name = os.path.basename(template_path)
                tpl_debug = os.path.join(self._log_dir, f"debug_template_{tpl_name}")
                shutil.copy2(template_path, tpl_debug)
                logger.info(t("layers.log.debug_template_saved", path=tpl_debug))
        except Exception as e:
            logger.warning(t("layers.log.debug_shot_save_failed", error=e))
