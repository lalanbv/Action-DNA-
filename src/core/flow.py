"""流程图数据模型 — 有向图替代线性步骤列表"""

from __future__ import annotations

import bisect
import logging
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, ClassVar

from src.core.step_types import BaseStep
from src.utils.i18n import t

if TYPE_CHECKING:
    from src.core.condition import Condition
    from src.core.engine.fsm_engine import GlobalTransition, Transition
    from src.core.error.error_config import ErrorConfig
    from src.core.monitor import MonitorConfig


class NodeType(Enum):
    """流程节点类型"""
    START = auto()
    ACTION = auto()
    CONDITION = auto()
    MERGE = auto()
    LOOP = auto()
    END = auto()


@dataclass
class FlowNode:
    """流程图中的单个节点"""
    node_id: str
    node_type: NodeType
    # ACTION 节点持有动作步骤（BaseStep 类型化）
    action: BaseStep | None = None
    # CONDITION 节点持有 Condition
    condition: Condition | None = None
    comment: str = ""
    enabled: bool = True
    # LOOP 节点的循环次数（0=无限）
    loop_count: int = 0
    # 可视化位置（仅 UI 使用）
    pos_x: int = 0
    pos_y: int = 0
    # D11: 错误配置（节点级，继承链: node → graph → global default IGNORE）
    error_config: ErrorConfig | None = None
    # D11: 断点标记（Layer 中间件读取）
    breakpoint: bool = False
    # D12: FSM 状态转换（为空则不启用 FSM）
    fsm_transitions: list[Transition] = field(default_factory=list)
    fsm_global_transitions: list[GlobalTransition] = field(default_factory=list)

    def describe(self) -> str:
        """返回节点的人类可读描述"""
        match self.node_type:
            case NodeType.START:
                return t("flow.node.start")
            case NodeType.END:
                return t("flow.node.end")
            case NodeType.MERGE:
                name = self.comment or self.node_id
                return t("flow.node.merge", name=name)
            case NodeType.LOOP:
                count_str = t("flow.node.infinite") if self.loop_count == 0 else str(self.loop_count)
                return t("flow.node.loop", count=count_str)
            case NodeType.ACTION:
                if self.action:
                    return self.action.describe()
                return t("flow.node.empty_action")
            case NodeType.CONDITION:
                if self.condition:
                    return t("flow.node.condition_with", desc=self.condition.describe())
                return t("flow.node.no_condition")


@dataclass
class FlowEdge:
    """流程图中两个节点之间的有向边"""
    edge_id: str
    from_node: str  # 源节点 ID
    to_node: str    # 目标节点 ID
    label: str = "default"  # "default" | "true" | "false" | "timeout"
    priority: int = 0       # 多出边时按优先级排序


@dataclass
class FlowGraph:
    """完整的流程图，替代 ActionChain"""
    name: str = ""
    nodes: dict[str, FlowNode] = field(default_factory=dict)
    edges: list[FlowEdge] = field(default_factory=list)
    start_node_id: str = ""
    # 后台监控器
    monitors: list[MonitorConfig] = field(default_factory=list)
    # D11: 图级别默认错误配置（节点未设置时继承）
    default_error_config: ErrorConfig | None = None
    # 向后兼容 v1 的 loop 控制
    loop: bool = True
    loop_count: int = 0  # 0 = 无限循环

    def __post_init__(self) -> None:
        self._rebuild_index()

    # ── 邻接索引 ──────────────────────────────────────────────

    def _rebuild_index(self) -> None:
        """从 edges 列表重建邻接索引"""
        self._outgoing: dict[str, list[FlowEdge]] = {}
        self._incoming: dict[str, list[FlowEdge]] = {}
        self._edge_by_id: dict[str, FlowEdge] = {}
        self._type_index: dict[NodeType, FlowNode] = {}
        for node in self.nodes.values():
            if node.node_type in (NodeType.START, NodeType.END):
                self._type_index[node.node_type] = node
        for e in self.edges:
            self._edge_by_id[e.edge_id] = e
            bisect.insort(
                self._outgoing.setdefault(e.from_node, []),
                e, key=lambda edge: edge.priority,
            )
            bisect.insort(
                self._incoming.setdefault(e.to_node, []),
                e, key=lambda edge: edge.priority,
            )

    def _remove_edge_by_id(self, edge_id: str) -> None:
        """按 ID 移除边，同步更新索引"""
        edge = self._edge_by_id.pop(edge_id, None)
        if edge is None:
            return
        self.edges = [e for e in self.edges if e.edge_id != edge_id]
        out = self._outgoing.get(edge.from_node)
        if out:
            out[:] = [e for e in out if e.edge_id != edge_id]
            if not out:
                del self._outgoing[edge.from_node]
        inc = self._incoming.get(edge.to_node)
        if inc:
            inc[:] = [e for e in inc if e.edge_id != edge_id]
            if not inc:
                del self._incoming[edge.to_node]

    def describe(self) -> str:
        return t("flow.describe.graph", name=self.name, nodes=len(self.nodes), edges=len(self.edges))

    # ── 节点操作 ──────────────────────────────────────────────

    def add_node(self, node: FlowNode) -> None:
        existing = self._type_index.get(node.node_type)
        if existing and existing.node_id != node.node_id and node.node_type in (NodeType.START, NodeType.END):
            logging.getLogger(__name__).warning(
                "覆盖已有 %s 节点: %s → %s",
                node.node_type.name, existing.node_id, node.node_id,
            )
        if node.node_type in (NodeType.START, NodeType.END):
            self._type_index[node.node_type] = node
        self.nodes[node.node_id] = node

    def remove_node(self, node_id: str) -> None:
        node = self.nodes.pop(node_id, None)
        if node:
            indexed = self._type_index.get(node.node_type)
            if indexed and indexed.node_id == node_id:
                del self._type_index[node.node_type]
        # 批量收集要移除的边 ID，一次性过滤
        out = self._outgoing.pop(node_id, [])
        inc = self._incoming.pop(node_id, [])
        remove_ids = {e.edge_id for e in out + inc}
        if not remove_ids:
            return
        self.edges = [e for e in self.edges if e.edge_id not in remove_ids]
        for eid in remove_ids:
            self._edge_by_id.pop(eid, None)
        # 清理对端节点的边索引
        for edge in out:
            inc_other = self._incoming.get(edge.to_node)
            if inc_other:
                inc_other[:] = [e for e in inc_other if e.edge_id not in remove_ids]
                if not inc_other:
                    del self._incoming[edge.to_node]
        for edge in inc:
            out_other = self._outgoing.get(edge.from_node)
            if out_other:
                out_other[:] = [e for e in out_other if e.edge_id not in remove_ids]
                if not out_other:
                    del self._outgoing[edge.from_node]

    def get_node(self, node_id: str) -> FlowNode | None:
        return self.nodes.get(node_id)

    # ── 边操作 ──────────────────────────────────────────────

    def add_edge(self, edge: FlowEdge) -> None:
        self.edges.append(edge)
        self._edge_by_id[edge.edge_id] = edge
        out = self._outgoing.setdefault(edge.from_node, [])
        bisect.insort(out, edge, key=lambda e: e.priority)
        inc = self._incoming.setdefault(edge.to_node, [])
        bisect.insort(inc, edge, key=lambda e: e.priority)

    def remove_edge(self, edge_id: str) -> None:
        self._remove_edge_by_id(edge_id)

    # ── 端口标签 ↔ 边标签 映射 ──────────────────────────────

    _PORT_LABEL_TO_EDGE: ClassVar[dict[str, str]] = {
        "out_default": "default",
        "out": "default",
        "out_true": "true",
        "out_false": "false",
        "out_loop": "loop",
        "out_exit": "exit",
    }

    @staticmethod
    def port_label_to_edge_label(port_label: str) -> str:
        """将端口标签 (out_default, out_true, out_false …) 映射为边标签。"""
        return FlowGraph._PORT_LABEL_TO_EDGE.get(
            port_label, port_label.replace("out_", "")
        )

    # ── 边重连 ──────────────────────────────────────────────

    def reconnect_edge(
        self, edge_id: str, side: str, new_node_id: str, new_port: str
    ) -> None:
        """重连边的一端。

        Args:
            edge_id: 要重连的边 ID
            side: "source" 重连源端 | "target" 重连目标端
            new_node_id: 新的连接节点 ID
            new_port: 新的端口标签（用于确定 edge label）
        """
        edge = self._edge_by_id.get(edge_id)
        if edge is None:
            raise ValueError(f"Edge {edge_id} not found")
        if new_node_id not in self.nodes:
            raise ValueError(f"Node {new_node_id} not found")

        if side == "source":
            out = self._outgoing.get(edge.from_node)
            if out:
                out[:] = [e for e in out if e.edge_id != edge_id]
                if not out:
                    self._outgoing.pop(edge.from_node, None)
            edge.from_node = new_node_id
            edge.label = self.port_label_to_edge_label(new_port)
            bucket = self._outgoing.setdefault(new_node_id, [])
            bucket.append(edge)
            bucket.sort(key=lambda e: e.priority)
        elif side == "target":
            inc = self._incoming.get(edge.to_node)
            if inc:
                inc[:] = [e for e in inc if e.edge_id != edge_id]
                if not inc:
                    self._incoming.pop(edge.to_node, None)
            edge.to_node = new_node_id
            self._incoming.setdefault(new_node_id, []).append(edge)
        else:
            raise ValueError(f"Invalid side: {side!r}")

    # 端口方向常量
    _INPUT_PORT_LABELS: ClassVar[frozenset[str]] = frozenset({"in"})
    _OUTPUT_PORT_LABELS: ClassVar[frozenset[str]] = frozenset({
        "out", "out_default", "out_true", "out_false", "out_loop", "out_exit",
    })

    def can_connect(
        self, from_id: str, to_id: str, label: str = "default",
        from_port: str = "", to_port: str = "",
    ) -> tuple[bool, str]:
        """验证连接是否有效。

        Args:
            from_id: 源节点 ID
            to_id: 目标节点 ID
            label: 边标签
            from_port: 源端口标签（如 "out_default"），用于方向校验
            to_port: 目标端口标签（如 "in"），用于方向校验

        Returns:
            (is_valid, reason) — reason 为空串表示有效。
        """
        if from_id == to_id:
            return False, "self_connect"
        if from_id not in self.nodes or to_id not in self.nodes:
            return False, "node_not_found"
        if from_port and to_port:
            from_is_output = from_port in self._OUTPUT_PORT_LABELS
            to_is_input = to_port in self._INPUT_PORT_LABELS
            if not from_is_output or not to_is_input:
                return False, "port_direction_mismatch"
        for e in self._outgoing.get(from_id, []):
            if e.to_node == to_id and e.label == label:
                return False, "duplicate"
        return True, ""

    def get_outgoing_edges(self, node_id: str) -> list[FlowEdge]:
        """获取指定节点的所有出边，按优先级排序（已预排序）。"""
        edges = self._outgoing.get(node_id)
        return edges[:] if edges else []

    def get_successors(self, node_id: str) -> list[str]:
        """获取直接后继节点 ID 列表（去重）。"""
        return list(dict.fromkeys(
            e.to_node for e in self._outgoing.get(node_id, [])
        ))

    def get_incoming_edges(self, node_id: str) -> list[FlowEdge]:
        """获取指定节点的所有入边"""
        return list(self._incoming.get(node_id, []))

    def get_edge(self, edge_id: str) -> FlowEdge | None:
        """按 ID 查找边"""
        return self._edge_by_id.get(edge_id)

    def get_edges_for_node(self, node_id: str) -> list[FlowEdge]:
        """获取与指定节点关联的所有边（入边 + 出边）"""
        out = self._outgoing.get(node_id, [])
        inc = self._incoming.get(node_id, [])
        return out + inc

    def next_node_id(self, from_id: str, label: str) -> str:
        """沿指定 label 的边查找下一个节点 ID"""
        # 先精确匹配 label
        for edge in self.get_outgoing_edges(from_id):
            if edge.label == label:
                return edge.to_node
        # 回退到 default
        if label != "default":
            for edge in self.get_outgoing_edges(from_id):
                if edge.label == "default":
                    return edge.to_node
        return ""  # 无出边 = 终止

    # ── ACTION 节点快捷方法（向后兼容线性编辑） ─────────────

    def action_nodes(self) -> list[FlowNode]:
        """沿 default 边遍历，按链路顺序返回 ACTION 节点"""
        result: list[FlowNode] = []
        visited: set[str] = set()
        nid = self.start_node_id
        while nid:
            if nid in visited:
                break
            visited.add(nid)
            node = self.nodes.get(nid)
            if node and node.node_type == NodeType.ACTION:
                result.append(node)
            # 沿 default 边前进
            next_id = ""
            for edge in self.get_outgoing_edges(nid):
                if edge.label == "default":
                    next_id = edge.to_node
                    break
            nid = next_id
        return result

    def ordered_nodes(self) -> list[FlowNode]:
        """DFS 遍历图，返回所有可达的有序节点列表（含分支）"""
        result: list[FlowNode] = []
        visited: set[str] = set()
        stack = [self.start_node_id]

        while stack:
            node_id = stack.pop()
            if not node_id or node_id in visited:
                continue
            visited.add(node_id)
            node = self.nodes.get(node_id)
            if node is None:
                continue
            result.append(node)
            # 出边已按 priority 升序排列；反向压栈使高优先级先出栈
            for edge in reversed(self.get_outgoing_edges(node_id)):
                stack.append(edge.to_node)

        return result

    # ── GraphEngine 依赖 ──────────────────────────────────────

    def find_by_type(self, node_type_name: str) -> FlowNode | None:
        """按 NodeType 名称查找第一个匹配的节点。"""
        try:
            nt = NodeType[node_type_name]
        except KeyError:
            return None
        cached = self._type_index.get(nt)
        if cached is not None and cached.node_id in self.nodes:
            return cached
        # 缓存失效（节点被直接 del），清理并回退到线性扫描
        if cached is not None:
            del self._type_index[nt]
        for node in self.nodes.values():
            if node.node_type == nt:
                if nt in (NodeType.START, NodeType.END):
                    self._type_index[nt] = node
                return node
        return None

    def get_reachable_nodes(self, start_id: str) -> set[str]:
        """从 start_id 出发 BFS，返回所有可达节点 ID。"""
        visited: set[str] = set()
        queue: deque[str] = deque([start_id])
        while queue:
            nid = queue.popleft()
            if nid in visited:
                continue
            visited.add(nid)
            for edge in self.get_outgoing_edges(nid):
                if edge.to_node not in visited:
                    queue.append(edge.to_node)
        return visited

    def get_all_node_ids(self) -> set[str]:
        """返回所有节点 ID。"""
        return set(self.nodes.keys())

    # ── 工具 ──────────────────────────────────────────────

    @staticmethod
    def new_id(prefix: str = "n") -> str:
        """生成稳定的短 ID"""
        uid = uuid.uuid4().hex[:8]
        return f"{prefix}_{uid}"


def chain_to_flow(chain_name: str, steps: list[BaseStep],
                  loop: bool = True, loop_count: int = 0) -> FlowGraph:
    """将线性步骤列表转换为 FlowGraph

    生成的图: START -> action_0 -> action_1 -> ... -> action_n -> END
    loop=True 时添加 END → START 边（结构元数据，供画布可视化循环回环箭头；
    GraphEngine 将 END 视为硬终止，实际循环由 ActionExecutor 管理）。
    """
    graph = FlowGraph(name=chain_name, loop=loop, loop_count=loop_count)

    # START 节点
    start = FlowNode(node_id="start", node_type=NodeType.START)
    graph.add_node(start)
    graph.start_node_id = "start"

    # 为每个步骤创建 ACTION 节点
    prev_id = "start"
    for step in steps:
        node_id = FlowGraph.new_id("a")
        node = FlowNode(
            node_id=node_id,
            node_type=NodeType.ACTION,
            action=step,
            comment=step.comment,
            enabled=step.enabled,
        )
        graph.add_node(node)
        edge = FlowEdge(
            edge_id=FlowGraph.new_id("e"),
            from_node=prev_id,
            to_node=node_id,
            label="default",
        )
        graph.add_edge(edge)
        prev_id = node_id

    # END 节点
    end = FlowNode(node_id="end", node_type=NodeType.END)
    graph.add_node(end)
    edge = FlowEdge(
        edge_id=FlowGraph.new_id("e"),
        from_node=prev_id,
        to_node="end",
        label="default",
    )
    graph.add_edge(edge)

    # loop 时 END → START
    if loop:
        loop_edge = FlowEdge(
            edge_id=FlowGraph.new_id("e"),
            from_node="end",
            to_node="start",
            label=LOOP_EDGE_LABEL,
        )
        graph.add_edge(loop_edge)

    return graph


# ── 循环边工具函数 ──────────────────────────────────────────

LOOP_EDGE_LABEL = "loop"


def find_loop_edge(graph: FlowGraph) -> FlowEdge | None:
    """查找 END → START 的 loop 边"""
    for e in graph.get_outgoing_edges("end"):
        if e.to_node == "start" and e.label == LOOP_EDGE_LABEL:
            return e
    return None


def ensure_loop_edge(graph: FlowGraph) -> None:
    """确保存在 loop 边，不存在则创建"""
    if find_loop_edge(graph):
        return
    loop_edge = FlowEdge(
        edge_id=FlowGraph.new_id("e"),
        from_node="end",
        to_node="start",
        label=LOOP_EDGE_LABEL,
    )
    graph.add_edge(loop_edge)


def remove_loop_edge(graph: FlowGraph) -> None:
    """移除 loop 边"""
    edge = find_loop_edge(graph)
    if edge:
        graph.remove_edge(edge.edge_id)
