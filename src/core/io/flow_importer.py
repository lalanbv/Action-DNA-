"""流程导入器 — 从自包含 JSON 文件导入 FlowGraph（含 base64 解码图片）"""

import base64
import json
import os

from src.core.flow import FlowGraph
from src.core.logger import log
from src.utils.i18n import t
from src.core.serialization import (
    dict_to_flow_edge,
    dict_to_flow_node,
    dict_to_monitor,
)


class FlowImporter:
    """从自包含 JSON 文件导入 FlowGraph，自动还原 base64 编码的图片"""

    @staticmethod
    def import_from_file(filepath: str, target_dir: str) -> FlowGraph:
        """从导出文件导入 FlowGraph

        Args:
            filepath: 导出的 JSON 文件路径
            target_dir: 目标 profile 目录（图片将还原到此目录）

        Returns:
            还原后的 FlowGraph
        """
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        images_dir = os.path.join(target_dir, "images")
        os.makedirs(images_dir, exist_ok=True)

        # 还原 base64 编码的图片
        for rel_path, b64_data in data.get("images", {}).items():
            abs_path = os.path.realpath(os.path.join(target_dir, rel_path))
            if not abs_path.startswith(os.path.realpath(target_dir)):
                log.warning(t("importer.log.path_traversal", path=rel_path))
                continue
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            try:
                with open(abs_path, "wb") as f:
                    f.write(base64.b64decode(b64_data))
            except OSError as e:
                log.warning(t("importer.log.image_restore_failed", path=abs_path, error=e))

        # 解析流程图
        flow_data = data.get("flow")
        if flow_data is None:
            raise ValueError(t("importer.log.missing_flow_key", path=filepath))
        graph = FlowGraph(
            name=flow_data.get("name", t("common.untitled")),
            start_node_id=flow_data.get("start_node_id", ""),
            loop=flow_data.get("loop", True),
            loop_count=flow_data.get("loop_count", 0),
        )

        for nd in flow_data.get("nodes", []):
            node = dict_to_flow_node(nd, target_dir)
            graph.add_node(node)

        for ed in flow_data.get("edges", []):
            edge = dict_to_flow_edge(ed)
            graph.add_edge(edge)

        for md in flow_data.get("monitors", []):
            monitor = dict_to_monitor(md, target_dir)
            graph.monitors.append(monitor)

        log.info(t("importer.log.imported", name=graph.describe(), path=filepath))
        return graph
