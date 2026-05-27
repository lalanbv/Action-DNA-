"""配置文件管理 — 保存/加载流程图配置（v3），兼容 v1/v2"""

import json
import os
import re
import shutil
from datetime import datetime

from src.core.action import ActionType
from src.core.step_types import BaseStep, ClickImageStep
from src.utils.i18n import t
from src.core.flow import FlowGraph, chain_to_flow
from src.core.logger import log
from src.core.serialization import (
    dict_to_flow_edge,
    dict_to_flow_node,
    dict_to_monitor,
    dict_to_step,
    flow_edge_to_dict,
    flow_node_to_dict,
    monitor_to_dict,
)
from src.utils.paths import get_profiles_dir


def get_profiles_root() -> str:
    """获取 profiles 根目录"""
    return get_profiles_dir()


def sanitize_profile_name(name: str) -> str:
    """清理配置名称，移除文件系统不安全字符"""
    return re.sub(r'[\\/:*?"<>|]', '_', name.strip())


def _validate_profile_name(name: str) -> None:
    """验证配置名称安全性，防止路径遍历攻击"""
    if not name or not name.strip():
        raise ValueError(t("profile.error.name_empty"))
    if os.path.sep in name or (os.path.altsep and os.path.altsep in name):
        raise ValueError(t("profile.error.name_path_sep", name=name))
    if ".." in name:
        raise ValueError(t("profile.error.name_dotdot", name=name))


class ProfileManager:
    """配置文件管理器 — 支持 v1/v2/v3 (FlowGraph)"""

    def __init__(self):
        self.root = get_profiles_root()

    def list_profiles(self) -> list[str]:
        """列出所有已保存的配置名称"""
        if not os.path.exists(self.root):
            return []
        return sorted(
            d for d in os.listdir(self.root)
            if os.path.isdir(os.path.join(self.root, d))
            and os.path.exists(os.path.join(self.root, d, "profile.json"))
        )

    def load(self, name: str) -> FlowGraph:
        """加载配置，返回 FlowGraph（v1 自动转换，图片路径为绝对路径）"""
        _validate_profile_name(name)
        profile_dir = os.path.join(self.root, name)
        config_path = os.path.join(profile_dir, "profile.json")

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError as exc:
            raise FileNotFoundError(t("profile.error.file_not_found", path=config_path)) from exc
        except json.JSONDecodeError as e:
            raise ValueError(t("profile.error.format_invalid", path=config_path) + f"\n{e}") from e

        version = data.get("version", 1)

        if version == 1 and "chain" in data:
            # v1: 转换为 FlowGraph
            return self._load_v1(data, profile_dir)
        elif version >= 2 and "flow" in data:
            # v2/v3: 直接解析（v3 新字段缺失时使用默认值）
            return self._load_v2(data, profile_dir)
        else:
            raise ValueError(t("profile.error.unsupported_version", version=version))

    def _load_v1(self, data: dict, profile_dir: str) -> FlowGraph:
        """加载 v1 格式并转换为 FlowGraph"""
        chain_data = data.get("chain")
        if chain_data is None:
            raise ValueError(t("profile.error.v1_missing_chain"))

        steps: list[BaseStep] = []
        for s in chain_data.get("steps", []):
            step = dict_to_step(s)
            if isinstance(step, ClickImageStep) and step.image_path:
                abs_path = os.path.normpath(os.path.join(profile_dir, step.image_path))
                step.image_path = abs_path
            steps.append(step)

        chain_name = chain_data.get("name", "")
        loop = chain_data.get("loop", True)
        loop_count = chain_data.get("loop_count", 0)
        return chain_to_flow(chain_name, steps, loop, loop_count)

    def _load_v2(self, data: dict, profile_dir: str) -> FlowGraph:
        """加载 v2/v3 格式的 FlowGraph（v3 新字段缺失时使用默认值）"""
        flow_data = data["flow"]
        graph = FlowGraph(
            name=flow_data.get("name", t("workflow.untitled")),
            start_node_id=flow_data.get("start_node_id", ""),
            loop=flow_data.get("loop", True),
            loop_count=flow_data.get("loop_count", 0),
        )

        # 解析节点
        for nd in flow_data.get("nodes", []):
            node = dict_to_flow_node(nd, profile_dir)
            graph.add_node(node)

        # 解析边
        for ed in flow_data.get("edges", []):
            edge = dict_to_flow_edge(ed)
            graph.add_edge(edge)

        # 解析监控器
        for md in flow_data.get("monitors", []):
            monitor = dict_to_monitor(md, profile_dir)
            graph.monitors.append(monitor)

        return graph

    def save(self, name: str, graph: FlowGraph) -> str:
        """
        保存配置为 v3 格式。
        外部图片会被复制到 profile 的 images/ 目录。
        返回 profile 目录路径。
        """
        safe_name = sanitize_profile_name(name)
        _validate_profile_name(safe_name)
        profile_dir = os.path.join(self.root, safe_name)
        images_dir = os.path.join(profile_dir, "images")
        os.makedirs(images_dir, exist_ok=True)

        # 序列化节点（处理图片复制）
        nodes_data = []
        for node in graph.nodes.values():
            node_dict = flow_node_to_dict(node)
            # 处理 ACTION 节点的图片
            if isinstance(node.action, ClickImageStep) and node.action.image_path:
                rel = self._copy_image(node.action.image_path, profile_dir, images_dir)
                node_dict["action"]["image_path"] = rel
            # 处理 CONDITION 节点的图片
            if node.condition and node.condition.image_path:
                node_dict["condition"]["image_path"] = self._copy_image(
                    node.condition.image_path, profile_dir, images_dir
                )
            nodes_data.append(node_dict)

        # 序列化边
        edges_data = [flow_edge_to_dict(e) for e in graph.edges]

        # 序列化监控器（处理图片）
        monitors_data = []
        for mon in graph.monitors:
            mon_dict = monitor_to_dict(mon)
            if mon.image_path:
                mon_dict["image_path"] = self._copy_image(mon.image_path, profile_dir, images_dir)
            if mon.handler_image_path:
                mon_dict["handler_image_path"] = self._copy_image(mon.handler_image_path, profile_dir, images_dir)
            monitors_data.append(mon_dict)

        profile_data = {
            "version": 3,
            "name": safe_name,
            "created_at": datetime.now().isoformat(),
            "flow": {
                "name": graph.name,
                "start_node_id": graph.start_node_id,
                "nodes": nodes_data,
                "edges": edges_data,
                "monitors": monitors_data,
                "loop": graph.loop,
                "loop_count": graph.loop_count,
            },
        }

        config_path = os.path.join(profile_dir, "profile.json")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(profile_data, f, indent=2, ensure_ascii=False)

        log.info(t("profile.log.saved", path=config_path))
        return profile_dir

    def _copy_image(self, src: str, profile_dir: str, images_dir: str) -> str:
        """复制外部图片到 profile 目录，返回相对路径"""
        if not os.path.exists(src):
            log.warning(t("profile.log.image_not_found", path=src))
            return src
        if src.startswith(profile_dir + os.sep) or os.path.abspath(src) == os.path.abspath(profile_dir):
            return os.path.relpath(src, profile_dir)
        basename = os.path.basename(src)
        dst = os.path.join(images_dir, basename)
        # 处理文件名冲突
        if os.path.abspath(src) != os.path.abspath(dst):
            name_base, ext = os.path.splitext(basename)
            counter = 1
            while os.path.exists(dst):
                dst = os.path.join(images_dir, f"{name_base}_{counter}{ext}")
                counter += 1
            basename = os.path.basename(dst)
        try:
            shutil.copy2(src, dst)
        except OSError as e:
            log.warning(t("profile.log.image_copy_failed", src=src, dst=dst, error=e))
        return os.path.join("images", basename)

    def delete(self, name: str) -> None:
        """删除配置"""
        _validate_profile_name(name)
        profile_dir = os.path.join(self.root, name)
        if os.path.exists(profile_dir):
            shutil.rmtree(profile_dir)
            log.info(t("profile.log.deleted", name=name))

    def exists(self, name: str) -> bool:
        return os.path.exists(os.path.join(self.root, name, "profile.json"))
