"""流程导出器 — 将 FlowGraph 导出为自包含 JSON（含 base64 编码图片）"""

import base64
import json
import os
from datetime import datetime

from src.core.flow import FlowGraph
from src.core.logger import log
from src.core.step_types import ClickImageStep
from src.utils.i18n import t


class FlowExporter:
    """将 FlowGraph 导出为自包含 JSON 文件，图片以 base64 编码内嵌"""

    @staticmethod
    def export(graph: FlowGraph, profile_dir: str) -> dict:
        """导出为可序列化的字典

        图片路径统一映射为 images/<basename> 格式，确保导入时能正确还原。
        """
        from src.core.serialization import (
            flow_node_to_dict, flow_edge_to_dict, monitor_to_dict,
        )

        # 收集所有图片路径并建立映射：原始路径 → (export key, abs_path)
        image_paths = _collect_image_paths(graph)
        path_map: dict[str, tuple[str, str]] = {}  # original path → (export_key, abs_path)
        seen_basenames: dict[str, int] = {}  # basename → count (for dedup)
        # 反向查找：export_key → abs_path，O(1) 去重检查
        key_to_abs: dict[str, str] = {}

        for path in sorted(image_paths):
            abs_path = _resolve_path(path, profile_dir)
            if not abs_path or not os.path.exists(abs_path):
                continue
            basename = os.path.basename(abs_path)
            # 去重：同名文件加序号
            if basename in seen_basenames:
                # 检查是否为同一文件
                existing_key = f"images/{basename}"
                existing_abs = key_to_abs.get(existing_key)
                if existing_abs and existing_abs == abs_path:
                    path_map[path] = (existing_key, abs_path)
                    continue
                seen_basenames[basename] += 1
                name_base, ext = os.path.splitext(basename)
                basename = f"{name_base}_{seen_basenames[basename]}{ext}"
            else:
                seen_basenames[basename] = 0
            export_key = f"images/{basename}"
            path_map[path] = (export_key, abs_path)
            key_to_abs[export_key] = abs_path

        data: dict = {
            "export_version": 1,
            "exported_at": datetime.now().isoformat(),
            "flow": {
                "name": graph.name,
                "start_node_id": graph.start_node_id,
                "loop": graph.loop,
                "loop_count": graph.loop_count,
                "nodes": [],
                "edges": [flow_edge_to_dict(e) for e in graph.edges],
                "monitors": [monitor_to_dict(m) for m in graph.monitors],
            },
            "images": {},
        }

        # 序列化节点，替换图片路径
        for node in graph.nodes.values():
            node_dict = flow_node_to_dict(node)
            if isinstance(node.action, ClickImageStep) and node.action.image_path and node.action.image_path in path_map:
                node_dict["action"]["image_path"] = path_map[node.action.image_path][0]
            if node.condition and node.condition.image_path and node.condition.image_path in path_map:
                node_dict["condition"]["image_path"] = path_map[node.condition.image_path][0]
            data["flow"]["nodes"].append(node_dict)

        # 序列化监控器，替换图片路径
        for i, mon in enumerate(graph.monitors):
            mon_dict = data["flow"]["monitors"][i]
            if mon.image_path and mon.image_path in path_map:
                mon_dict["image_path"] = path_map[mon.image_path][0]
            if mon.handler_image_path and mon.handler_image_path in path_map:
                mon_dict["handler_image_path"] = path_map[mon.handler_image_path][0]

        # 编码图片为 base64（使用缓存的绝对路径，避免重复解析）
        for export_key, abs_path in path_map.values():
            try:
                with open(abs_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("ascii")
                data["images"][export_key] = b64
            except OSError as e:
                log.warning(t("exporter.log.image_export_failed", path=abs_path, error=e))

        return data

    @staticmethod
    def save_file(data: dict, filepath: str) -> None:
        """保存导出数据到文件"""
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        log.info(t("exporter.log.exported", path=filepath))


def _collect_image_paths(graph: FlowGraph) -> set[str]:
    """收集流程图中引用的所有图片路径"""
    paths: set[str] = set()
    for node in graph.nodes.values():
        if isinstance(node.action, ClickImageStep) and node.action.image_path:
            paths.add(node.action.image_path)
        if node.condition and node.condition.image_path:
            paths.add(node.condition.image_path)
    for mon in graph.monitors:
        if mon.image_path:
            paths.add(mon.image_path)
        if mon.handler_image_path:
            paths.add(mon.handler_image_path)
    return paths


def _resolve_path(path: str, profile_dir: str) -> str:
    """将路径解析为绝对路径"""
    if not path:
        return ""
    if os.path.isabs(path):
        return path
    return os.path.normpath(os.path.join(profile_dir, path))
