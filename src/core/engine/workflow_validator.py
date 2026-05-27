"""WorkflowValidator — 三阶段 FlowGraph 验证。

阶段:
  1. 构建时验证 (validate_build): 图结构完整性
  2. 连接验证 (validate_connections): 边/引用/类型一致性
  3. 运行时验证 (validate_runtime): 执行前置条件

参考: 03_核心引擎设计.md §10, 12_开发计划与时间安排.md §9.2
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from src.core.engine.node_registry import NodeRegistry
from src.core.flow import NodeType

if TYPE_CHECKING:
    from src.core.engine.execution_context import ExecutionContext
    from src.core.flow import FlowGraph

__all__ = [
    "ValidationLevel",
    "ValidationIssue",
    "ValidationResult",
    "WorkflowValidator",
]


class ValidationLevel(Enum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class ValidationIssue:
    level: ValidationLevel
    message: str
    node_id: str | None = None
    edge_id: str | None = None


@dataclass
class ValidationResult:
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.level == ValidationLevel.ERROR]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.level == ValidationLevel.WARNING]

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def merge(self, other: ValidationResult) -> ValidationResult:
        return ValidationResult(issues=self.issues + other.issues)


class WorkflowValidator:
    """三阶段 FlowGraph 验证器。"""

    # ---- 阶段 1: 构建时验证 (D12) ----

    def validate_build(self, graph: FlowGraph) -> ValidationResult:
        """验证图结构完整性：START/END 存在、无孤立节点、节点类型合法。"""
        result = ValidationResult()

        # START 节点必须存在且唯一
        start_nodes = [
            n for n in graph.nodes.values() if n.node_type == NodeType.START
        ]
        if len(start_nodes) == 0:
            result.issues.append(ValidationIssue(
                level=ValidationLevel.ERROR,
                message="缺少 START 节点",
            ))
        elif len(start_nodes) > 1:
            result.issues.append(ValidationIssue(
                level=ValidationLevel.ERROR,
                message=f"存在多个 START 节点: {[n.node_id for n in start_nodes]}",
            ))

        # END 节点必须存在
        end_nodes = [
            n for n in graph.nodes.values() if n.node_type == NodeType.END
        ]
        if len(end_nodes) == 0:
            result.issues.append(ValidationIssue(
                level=ValidationLevel.ERROR,
                message="缺少 END 节点",
            ))
        elif len(end_nodes) > 1:
            result.issues.append(ValidationIssue(
                level=ValidationLevel.WARNING,
                message=f"存在多个 END 节点: {[n.node_id for n in end_nodes]}",
            ))

        # 从 START 可达性检查 — 检测孤立节点
        if start_nodes:
            reachable = graph.get_reachable_nodes(start_nodes[0].node_id)
            all_ids = graph.get_all_node_ids()
            unreachable = all_ids - reachable
            if unreachable:
                for uid in sorted(unreachable):
                    node = graph.get_node(uid)
                    if node and node.node_type == NodeType.END:
                        result.issues.append(ValidationIssue(
                            level=ValidationLevel.ERROR,
                            message=f"END 节点 '{uid}' 不可达",
                            node_id=uid,
                        ))
                    else:
                        result.issues.append(ValidationIssue(
                            level=ValidationLevel.WARNING,
                            message=f"节点 '{uid}' 不可达",
                            node_id=uid,
                        ))

        # 节点类型合法性 + ACTION 节点必须有 action 配置
        valid_types = {NodeType.START, NodeType.END, NodeType.ACTION, NodeType.CONDITION, NodeType.MERGE, NodeType.LOOP}
        for node in graph.nodes.values():
            if node.node_type not in valid_types:
                result.issues.append(ValidationIssue(
                    level=ValidationLevel.ERROR,
                    message=f"节点 '{node.node_id}' 类型 '{node.node_type.name}' 不合法",
                    node_id=node.node_id,
                ))
            if node.node_type == NodeType.ACTION and node.action is None:
                result.issues.append(ValidationIssue(
                    level=ValidationLevel.ERROR,
                    message=f"动作节点 '{node.node_id}' 缺少 action 配置",
                    node_id=node.node_id,
                ))

        return result

    # ---- 阶段 2: 连接验证 (D13) ----

    def validate_connections(self, graph: FlowGraph) -> ValidationResult:
        """验证边完整性：悬空引用、重复边、自环、描述符注册。"""
        result = ValidationResult()
        all_node_ids = graph.get_all_node_ids()

        for edge in graph.edges:
            # 悬空引用 — from_node 或 to_node 不存在
            if edge.from_node not in all_node_ids:
                result.issues.append(ValidationIssue(
                    level=ValidationLevel.ERROR,
                    message=f"边 '{edge.edge_id}' 的 from_node '{edge.from_node}' 不存在",
                    edge_id=edge.edge_id,
                ))
            if edge.to_node not in all_node_ids:
                result.issues.append(ValidationIssue(
                    level=ValidationLevel.ERROR,
                    message=f"边 '{edge.edge_id}' 的 to_node '{edge.to_node}' 不存在",
                    edge_id=edge.edge_id,
                ))

            # 自环
            if edge.from_node == edge.to_node:
                result.issues.append(ValidationIssue(
                    level=ValidationLevel.ERROR,
                    message=f"边 '{edge.edge_id}' 形成自环 ({edge.from_node} → {edge.to_node})",
                    edge_id=edge.edge_id,
                ))

        # 重复边检测
        seen: set[tuple[str, str, str]] = set()
        for edge in graph.edges:
            key = (edge.from_node, edge.to_node, edge.label or "")
            if key in seen:
                result.issues.append(ValidationIssue(
                    level=ValidationLevel.WARNING,
                    message=f"重复边: {edge.from_node} → {edge.to_node}",
                    edge_id=edge.edge_id,
                ))
            seen.add(key)

        # 节点连通性 — 非 END 节点应有出边，非 START 节点应有入边
        nodes_with_outgoing: set[str] = set()
        nodes_with_incoming: set[str] = set()
        for edge in graph.edges:
            nodes_with_outgoing.add(edge.from_node)
            nodes_with_incoming.add(edge.to_node)

        for node in graph.nodes.values():
            if node.node_type == NodeType.END:
                if node.node_id in nodes_with_outgoing:
                    result.issues.append(ValidationIssue(
                        level=ValidationLevel.WARNING,
                        message=f"END 节点 '{node.node_id}' 有出边",
                        node_id=node.node_id,
                    ))
            else:
                if node.node_id not in nodes_with_outgoing:
                    result.issues.append(ValidationIssue(
                        level=ValidationLevel.WARNING,
                        message=f"非终止节点 '{node.node_id}' 没有出边",
                        node_id=node.node_id,
                    ))
            if node.node_type == NodeType.START and node.node_id in nodes_with_incoming:
                result.issues.append(ValidationIssue(
                    level=ValidationLevel.WARNING,
                    message=f"START 节点 '{node.node_id}' 有入边",
                    node_id=node.node_id,
                ))

        # 描述符注册检查 — ACTION 节点的动作类型必须有对应描述符
        for node in graph.nodes.values():
            if node.node_type == NodeType.ACTION and node.action is not None:
                action_type = node.action.action_type.name
                if not NodeRegistry.has(action_type):
                    result.issues.append(ValidationIssue(
                        level=ValidationLevel.ERROR,
                        message=f"动作类型 '{action_type}' 未注册描述符",
                        node_id=node.node_id,
                    ))

        return result

    # ---- 阶段 3: 运行时验证 (D14) ----

    def validate_runtime(
        self, graph: FlowGraph, ctx: ExecutionContext,
    ) -> ValidationResult:
        """执行前验证：上下文完整性、必填参数、线程信号。"""
        result = ValidationResult()

        # 先执行构建时和连接时验证
        result = result.merge(self.validate_build(graph))
        result = result.merge(self.validate_connections(graph))

        # stop_event 和 pause_event 必须存在
        if ctx.stop_event is None:
            result.issues.append(ValidationIssue(
                level=ValidationLevel.ERROR,
                message="ExecutionContext 缺少 stop_event",
            ))
        elif not isinstance(ctx.stop_event, threading.Event):
            result.issues.append(ValidationIssue(
                level=ValidationLevel.ERROR,
                message="stop_event 类型不正确",
            ))

        if ctx.pause_event is None:
            result.issues.append(ValidationIssue(
                level=ValidationLevel.WARNING,
                message="ExecutionContext 缺少 pause_event",
            ))

        # capture 和 input_ctrl 必须存在
        if ctx.capture is None:
            result.issues.append(ValidationIssue(
                level=ValidationLevel.ERROR,
                message="ExecutionContext 缺少 capture",
            ))
        if ctx.input_ctrl is None:
            result.issues.append(ValidationIssue(
                level=ValidationLevel.ERROR,
                message="ExecutionContext 缺少 input_ctrl",
            ))

        # ACTION 节点参数验证 — 检查描述符 required 参数
        for node in graph.nodes.values():
            if node.node_type != NodeType.ACTION or node.action is None:
                continue
            action_type = node.action.action_type.name
            if not NodeRegistry.has(action_type):
                continue
            descriptor = NodeRegistry.get(action_type)

            for port_name, port_def in descriptor.input_types().items():
                if not port_def.required:
                    continue
                value = getattr(node.action, port_name, None)
                if value is None:
                    result.issues.append(ValidationIssue(
                        level=ValidationLevel.ERROR,
                        message=(
                            f"节点 '{node.node_id}' 缺少必填参数 '{port_name}'"
                        ),
                        node_id=node.node_id,
                    ))

        return result

    # ---- 便捷方法 ----

    def validate_all(self, graph: FlowGraph) -> ValidationResult:
        """执行所有静态验证阶段（构建时 + 连接时）。"""
        result = ValidationResult()
        result = result.merge(self.validate_build(graph))
        result = result.merge(self.validate_connections(graph))
        return result
