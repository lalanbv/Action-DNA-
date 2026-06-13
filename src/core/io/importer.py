"""ProfileImporter — 三版本迁移链 v1 → v2 → v3。
MacroImporter — JSON 宏脚本导入。

职责:
- 自动检测 profile.json 版本
- 按链式步骤迁移: v1 → v2 → v3
- v1 → v2: 线性步骤列表 → FlowGraph 格式
- v2 → v3: 添加 error_config / breakpoint / fsm_transitions 默认值
- JSON 宏脚本导入: 将可编辑 JSON 转为 BaseStep 列表

设计文档: DNA_Design_Scheme/13_风险与验证策略.md §3.2
"""

from __future__ import annotations

import contextlib
import copy
import json
import os
from dataclasses import dataclass

from src.core.action import ActionType
from src.core.step_types import BaseStep, ClickImageStep, STEP_CLASSES
from src.core.flow import FlowGraph, chain_to_flow
from src.core.logger import log
from src.utils.i18n import t
from src.core.serialization import (
    dict_to_flow_edge,
    dict_to_flow_node,
    dict_to_monitor,
    dict_to_step,
    flow_edge_to_dict,
    flow_node_to_dict,
    monitor_to_dict,
)


@dataclass(frozen=True)
class MigrationReport:
    """迁移报告 — 记录每一步迁移的变更。"""

    original_version: int
    final_version: int
    steps: list[str]
    migrated: bool

    def describe(self) -> str:
        lines = [t("importer.log.migration_header", from_ver=self.original_version, to_ver=self.final_version)]
        lines.extend(f"  - {step}" for step in self.steps)
        return "\n".join(lines)


class ProfileImporter:
    """Profile 版本迁移器。

    迁移链: v1 -> v2 -> v3

    v1 -> v2:
    - ActionStep 列表 → FlowGraph 格式
    - 图片路径标准化为相对路径

    v2 -> v3:
    - 添加 error_config 字段（默认 IGNORE 策略）
    - 添加 breakpoint 字段（默认 False）
    - 添加 fsm_transitions 字段（默认空列表）
    - 添加 fsm_global_transitions 字段（默认空列表）
    """

    SUPPORTED_VERSIONS = {1, 2, 3}
    CURRENT_VERSION = 3

    def import_profile(
        self, data: dict, profile_dir: str = ""
    ) -> tuple[FlowGraph, MigrationReport]:
        """导入配置文件，自动检测版本并迁移。

        Args:
            data: profile.json 解析后的字典
            profile_dir: 配置目录路径（用于解析相对图片路径）

        Returns:
            (FlowGraph, MigrationReport) 元组
        """
        version = data.get("version", 1)
        if version not in self.SUPPORTED_VERSIONS:
            raise ValueError(t("profile.error.unsupported_version", version=version))

        steps: list[str] = []
        original_version = version
        migrated = False

        if version == 1:
            data = self._migrate_v1_to_v2(data, profile_dir)
            steps.append(t("importer.log.migration_step.v1_v2"))
            version = 2
            migrated = True

        if version == 2:
            data = self._migrate_v2_to_v3(data)
            steps.append(t("importer.log.migration_step.v2_v3"))
            version = 3
            migrated = True

        graph = self._parse_v3(data, profile_dir)

        report = MigrationReport(
            original_version=original_version,
            final_version=version,
            steps=steps,
            migrated=migrated,
        )
        log.info(report.describe())
        return graph, report

    def import_from_file(self, config_path: str) -> tuple[FlowGraph, MigrationReport]:
        """从 profile.json 文件导入。

        Args:
            config_path: profile.json 的完整路径

        Returns:
            (FlowGraph, MigrationReport) 元组
        """
        profile_dir = os.path.dirname(config_path)
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return self.import_profile(data, profile_dir)

    # ── v1 → v2 ─────────────────────────────────────────────

    def _migrate_v1_to_v2(self, data: dict, profile_dir: str) -> dict:
        """v1 (线性步骤列表) → v2 (FlowGraph dict)"""
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
        graph = chain_to_flow(chain_name, steps, loop, loop_count)

        return {
            "version": 2,
            "name": data.get("name", chain_name),
            "created_at": data.get("created_at", ""),
            "flow": _graph_to_v2_dict(graph, profile_dir),
        }

    # ── v2 → v3 ─────────────────────────────────────────────

    def _migrate_v2_to_v3(self, data: dict) -> dict:
        """v2 → v3: 为每个节点补全新字段默认值。"""
        data = copy.deepcopy(data)
        data["version"] = 3

        for node in data.get("flow", {}).get("nodes", []):
            if "error_config" not in node or node["error_config"] is None:
                node["error_config"] = {
                    "strategy": "ignore",
                    "max_retries": 3,
                    "retry_delay": 1.0,
                }
            if "breakpoint" not in node:
                node["breakpoint"] = False
            if "fsm_transitions" not in node:
                node["fsm_transitions"] = []
            if "fsm_global_transitions" not in node:
                node["fsm_global_transitions"] = []

        return data

    # ── v3 解析 ──────────────────────────────────────────────

    def _parse_v3(self, data: dict, profile_dir: str) -> FlowGraph:
        """解析 v3 格式数据为 FlowGraph。"""
        flow_data = data["flow"]
        graph = FlowGraph(
            name=flow_data.get("name", t("common.untitled")),
            start_node_id=flow_data.get("start_node_id", ""),
            loop=flow_data.get("loop", True),
            loop_count=flow_data.get("loop_count", 0),
        )

        for nd in flow_data.get("nodes", []):
            node = dict_to_flow_node(nd, profile_dir)
            graph.add_node(node)

        for ed in flow_data.get("edges", []):
            edge = dict_to_flow_edge(ed)
            graph.add_edge(edge)

        for md in flow_data.get("monitors", []):
            monitor = dict_to_monitor(md, profile_dir)
            graph.monitors.append(monitor)

        return graph


# ── 内部辅助 ──────────────────────────────────────────────


def _graph_to_v2_dict(graph: FlowGraph, profile_dir: str) -> dict:
    """将 FlowGraph 序列化为 v2 字典格式（不含 error_config 等新字段）。"""
    nodes_data = []
    for node in graph.nodes.values():
        nd = flow_node_to_dict(node)
        if isinstance(node.action, ClickImageStep) and node.action.image_path:
            with contextlib.suppress(ValueError):
                nd["action"]["image_path"] = os.path.relpath(
                    node.action.image_path, profile_dir
                )
        # 多模板备用图:绝对路径 → 相对 profile_dir
        if isinstance(node.action, ClickImageStep) and node.action.alt_image_paths:
            nd["action"]["alt_image_paths"] = [
                os.path.relpath(p, profile_dir) if os.path.isabs(p) else p
                for p in node.action.alt_image_paths
            ]
        nodes_data.append(nd)

    edges_data = [flow_edge_to_dict(e) for e in graph.edges]
    monitors_data = [monitor_to_dict(m) for m in graph.monitors]

    return {
        "name": graph.name,
        "start_node_id": graph.start_node_id,
        "nodes": nodes_data,
        "edges": edges_data,
        "monitors": monitors_data,
        "loop": graph.loop,
        "loop_count": graph.loop_count,
    }


class MacroImporter:
    """导入 JSON 宏脚本为 BaseStep 列表。

    JSON 格式由 ScriptExporter.export_json() 生成，也可手动编辑。
    """

    SUPPORTED_VERSION = "2.0"

    def import_json(self, json_str: str) -> list[BaseStep]:
        """从 JSON 字符串导入宏步骤。"""
        data = json.loads(json_str)
        version = data.get("version", "")
        if version != self.SUPPORTED_VERSION:
            raise ValueError(f"不支持的宏脚本版本: {version} (需要 {self.SUPPORTED_VERSION})")

        steps: list[BaseStep] = []
        for item in data.get("steps", []):
            step = self._dict_to_step(item)
            if step is not None:
                steps.append(step)
        return steps

    def import_json_file(self, path: str) -> list[BaseStep]:
        """从 JSON 文件导入宏步骤。"""
        with open(path, "r", encoding="utf-8") as f:
            return self.import_json(f.read())

    _LEGACY_TYPE_MAP: dict[str, str] = {
        "MOUSE_TURN": "MOUSE_MOVE",
    }

    def _dict_to_step(self, d: dict) -> BaseStep | None:
        """单条 JSON 字典 → BaseStep。"""
        atype_str = d.get("type", "")
        atype_str = self._LEGACY_TYPE_MAP.get(atype_str, atype_str)
        try:
            atype = ActionType[atype_str]
        except KeyError:
            return None

        cls = STEP_CLASSES.get(atype)
        if cls is None:
            return None

        match atype:
            case ActionType.CLICK_POS:
                pos = d.get("pos", [0, 0])
                return cls(
                    pos_x=pos[0], pos_y=pos[1],
                    clicks=d.get("clicks", 1),
                    button=d.get("button", "left"),
                    hold_duration=d.get("hold", 0.0),
                    recorded_duration=d.get("duration", 0.0),
                    enabled=d.get("enabled", True),
                )
            case ActionType.PRESS_KEY:
                text = d.get("text", "")
                key = d.get("key", "")
                return cls(
                    text=text, key=key,
                    recorded_duration=d.get("duration", 0.0),
                    enabled=d.get("enabled", True),
                )
            case ActionType.HOLD_KEY:
                return cls(
                    keys_hold=d.get("key", ""),
                    hold_duration=d.get("duration", 0.5),
                    recorded_duration=d.get("duration", 0.0),
                    enabled=d.get("enabled", True),
                )
            case ActionType.MOUSE_SCROLL:
                pos = d.get("pos", [0, 0])
                return cls(
                    scroll_clicks=d.get("clicks", 3),
                    scroll_delta_x=d.get("horizontal", 0),
                    pos_x=pos[0], pos_y=pos[1],
                    recorded_duration=d.get("duration", 0.0),
                    enabled=d.get("enabled", True),
                )
            case ActionType.MOUSE_MOVE:
                offset = d.get("offset", [0, 0])
                return cls(
                    offset_x=offset[0], offset_y=offset[1],
                    move_speed=d.get("speed", 0.5),
                    curve_amount=d.get("curve", 0.0),
                    recorded_duration=d.get("duration", 0.0),
                    enabled=d.get("enabled", True),
                    button=d.get("button", ""),
                )
            case ActionType.MOUSE_DRAG:
                start = d.get("start", [0, 0])
                end = d.get("end", [0, 0])
                return cls(
                    start_x=start[0], start_y=start[1],
                    end_x=end[0], end_y=end[1],
                    button=d.get("button", "left"),
                    duration=d.get("duration", 0.5),
                    enabled=d.get("enabled", True),
                )
            case ActionType.WAIT:
                return cls(
                    wait_seconds=d.get("seconds", 1.0),
                    recorded_duration=d.get("duration", 0.0),
                    enabled=d.get("enabled", True),
                )
            case ActionType.WAIT_RANDOM:
                return cls(
                    wait_min=d.get("min", 1.0),
                    wait_max=d.get("max", 3.0),
                    recorded_duration=d.get("duration", 0.0),
                    enabled=d.get("enabled", True),
                )
            case ActionType.KEY_COMBO:
                return cls(
                    combo_keys=d.get("keys", ""),
                    combo_mode=d.get("mode", "hold_tap"),
                    recorded_duration=d.get("duration", 0.0),
                    enabled=d.get("enabled", True),
                )
            case _:
                return cls(
                    recorded_duration=d.get("duration", 0.0),
                    enabled=d.get("enabled", True),
                )
