"""SubGraphDescriptor — 子图嵌套，引用并执行另一个 FlowGraph。

支持工作流复用：将常用流程封装为子图，在主图中通过引用调用。
子图共享父图的 VariablePool、stop_event、pause_event，
实现隔离执行 + 统一控制。

循环检测：通过 ancestor_chain 追踪嵌套路径，防止 A→B→A 循环引用。
"""

from __future__ import annotations

import json
import logging
import os
import types
from dataclasses import replace
from typing import TYPE_CHECKING

from src.core.engine.node_descriptor import NodeDescriptor, PortDef
from src.core.engine.node_registry import auto_register
from src.core.engine.node_result import NodeResult

if TYPE_CHECKING:
    from src.core.engine.execution_context import ExecutionContext
    from src.core.flow import FlowGraph

logger = logging.getLogger(__name__)

__all__ = ["SubGraphDescriptor"]

_ANCESTOR_KEY = "_subgraph_ancestors"


@auto_register
class SubGraphDescriptor(NodeDescriptor):
    """SUB_GRAPH: 引用并执行另一个 FlowGraph（子图嵌套）。

    graph_ref 指向 profiles 目录下的配置名（如 "combat_rotation"），
    执行时加载对应 FlowGraph，创建子上下文委托给 GraphEngine。
    """

    @classmethod
    def action_type(cls) -> str:
        return "SUB_GRAPH"

    @classmethod
    def display_name(cls) -> str:
        return "子图"

    @classmethod
    def category(cls) -> str:
        return "流程控制"

    @classmethod
    def input_types(cls) -> dict[str, PortDef]:
        return {
            "graph_ref": PortDef("string", "子图引用（配置名）", required=True),
        }

    @classmethod
    def output_types(cls) -> dict[str, PortDef]:
        return {
            "sub_result": PortDef("string", "子图执行结果"),
        }

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        action = ctx.current_node.action
        if action is None:
            return NodeResult(success=False, error="SUB_GRAPH: 无动作配置")

        graph_ref = getattr(action, "graph_ref", None)
        if not graph_ref:
            return NodeResult(success=False, error="SUB_GRAPH: graph_ref 未设置")

        # 循环检测
        ancestor_chain = list(ctx.extra.get(_ANCESTOR_KEY, []))
        if graph_ref in ancestor_chain:
            return NodeResult(
                success=False,
                error=f"SUB_GRAPH: 检测到循环引用 {' → '.join(ancestor_chain)} → {graph_ref}",
            )

        # 加载子图
        try:
            sub_graph = _load_sub_graph(graph_ref, ctx)
        except (FileNotFoundError, json.JSONDecodeError, KeyError) as exc:
            return NodeResult(
                success=False, error=f"SUB_GRAPH: 加载子图 '{graph_ref}' 失败: {exc}"
            )

        # 获取 GraphEngine（通过 extra 注入）
        engine = ctx.extra.get("_graph_engine")
        if engine is None:
            return NodeResult(success=False, error="SUB_GRAPH: GraphEngine 未注入")

        # 构建子上下文 — 共享 variables、stop/pause 事件，追加 ancestor
        child_ctx = replace(
            ctx,
            graph=sub_graph,
            step_index=0,
            extra=_with_ancestor(ctx.extra, ancestor_chain, graph_ref),
        )

        logger.info("▶ 进入子图 '%s' (ancestor: %s)", graph_ref, ancestor_chain)

        try:
            engine.run(sub_graph, child_ctx)
        except Exception as exc:  # noqa: BLE001 — 描述符不能向上传播异常
            logger.error("子图 '%s' 执行失败: %s", graph_ref, exc)
            return NodeResult(
                success=False,
                error=f"子图 '{graph_ref}' 执行失败: {exc}",
                output_vars={"sub_result": "error"},
            )

        logger.info("◀ 子图 '%s' 执行完成", graph_ref)
        return NodeResult(success=True, output_vars={"sub_result": "ok"})


def _load_sub_graph(graph_ref: str, ctx: ExecutionContext) -> FlowGraph:
    """从 profiles 目录加载子图配置。"""
    from src.core.flow import FlowGraph
    from src.core.serialization import dict_to_flow_edge, dict_to_flow_node

    profile_root = ctx.extra.get("profile_root", "profiles")
    profile_dir = os.path.join(profile_root, graph_ref)
    config_path = os.path.join(profile_dir, "profile.json")

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"子图配置不存在: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    graph_data = data.get("flow", data.get("graph", data))

    nodes = {}
    for nid, nd in graph_data.get("nodes", {}).items():
        nodes[nid] = dict_to_flow_node(nd, profile_dir)

    edges = [dict_to_flow_edge(ed) for ed in graph_data.get("edges", [])]

    return FlowGraph(
        name=graph_data.get("name", graph_ref),
        nodes=nodes,
        edges=edges,
        start_node_id=graph_data.get("start_node_id", ""),
        loop=graph_data.get("loop", True),
        loop_count=graph_data.get("loop_count", 0),
    )


def _with_ancestor(
    extra: types.MappingProxyType | dict, chain: list[str], ref: str,
) -> dict:
    """创建包含更新 ancestor 链的 extra。"""
    new_data = dict(extra)
    new_data[_ANCESTOR_KEY] = chain + [ref]
    return new_data
