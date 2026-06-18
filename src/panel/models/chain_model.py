"""ChainModel — 可观察的流程图数据模型（基于 FlowGraph）"""

from enum import Enum

from src.core.action import ActionType
from src.core.flow import LOOP_EDGE_LABEL
from src.core.flow import FlowEdge, FlowGraph, FlowNode, NodeType
from src.core.monitor import MonitorConfig
from src.core.events import TypedEventBus
from src.core.events.event_names import EventName
from src.core.step_types import BaseStep, STEP_CLASSES
from src.panel.components.step_param_view import build_move_order
from src.panel.models.enums import EdgeLabel
from src.utils.i18n import t


class ExecutorState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"


class ChainModel:
    """持有流程图数据，通过 EventBus 通知变更

    内部使用 FlowGraph，对外保留线性步骤操作方法以兼容现有 UI。
    """

    def __init__(self, event_bus: TypedEventBus):
        self._bus = event_bus
        self.graph = FlowGraph(name=t("workflow.untitled"), start_node_id="start")
        self.current_profile_name: str | None = None
        self.region_mode: str = "fullscreen"
        self.executor_state: ExecutorState = ExecutorState.IDLE
        self._dirty: bool = False
        self._init_empty_graph()

    def _init_empty_graph(self) -> None:
        """初始化一个空流程图: START → END (+ 循环边)"""
        self.graph = FlowGraph(name=t("workflow.untitled"), start_node_id="start")
        start = FlowNode(node_id="start", node_type=NodeType.START)
        end = FlowNode(node_id="end", node_type=NodeType.END)
        self.graph.add_node(start)
        self.graph.add_node(end)
        edge = FlowEdge(
            edge_id=FlowGraph.new_id("e"),
            from_node="start",
            to_node="end",
            label=EdgeLabel.DEFAULT,
        )
        self.graph.add_edge(edge)
        # 默认循环边 END → START
        loop_edge = FlowEdge(
            edge_id=FlowGraph.new_id("e"),
            from_node="end",
            to_node="start",
            label=LOOP_EDGE_LABEL,
        )
        self.graph.add_edge(loop_edge)
        self._dirty = False

    @property
    def is_dirty(self) -> bool:
        """是否有未保存的修改。"""
        return self._dirty

    def mark_clean(self) -> None:
        """标记为已保存（干净状态）。"""
        self._dirty = False

    def _mark_dirty(self) -> None:
        """标记为已修改（脏状态）。"""
        self._dirty = True

    # ── 线性步骤操作（向后兼容 UI）───────────────────────────

    def _append_action_node(self, step: BaseStep) -> str:
        """内部：在 END 前追加一个 ACTION 节点，返回新 node_id（不发事件）。

        供 ``add_step`` / ``duplicate_step`` 复用，避免组合操作时多次 emit。
        """
        # 找到指向 END 的最后一条 default 边
        prev_id = self._find_node_before_end()
        new_node_id = FlowGraph.new_id("a")
        new_node = FlowNode(
            node_id=new_node_id,
            node_type=NodeType.ACTION,
            action=step,
            comment=step.comment,
            enabled=step.enabled,
        )
        self.graph.add_node(new_node)
        # 修改 prev -> END 为 prev -> new_node -> END
        self._reroute_to_end(prev_id, new_node_id)
        return new_node_id

    def add_step(self, step: BaseStep) -> None:
        """在线性序列末尾添加一个 ACTION 节点（插在 END 之前）"""
        self._append_action_node(step)
        self._mark_dirty()
        self._bus.emit(EventName.CHAIN_STEPS_CHANGED)

    def remove_step(self, index: int) -> None:
        """按线性索引移除一个 ACTION 节点，并重新连接其前后邻居"""
        action_nodes = self.graph.action_nodes()
        if not (0 <= index < len(action_nodes)):
            return
        node_id = action_nodes[index].node_id

        # 找到 default 入边和出边，确定前后邻居
        in_default = None
        for e in self.graph.get_incoming_edges(node_id):
            if e.label == EdgeLabel.DEFAULT:
                in_default = e
                break

        out_default = None
        for e in self.graph.get_outgoing_edges(node_id):
            if e.label == EdgeLabel.DEFAULT:
                out_default = e
                break

        prev_id = in_default.from_node if in_default else self.graph.start_node_id
        next_id = out_default.to_node if out_default else "end"

        # 删除节点（会自动移除其关联的边）
        self.graph.remove_node(node_id)

        # 重新连接 prev → next
        self.graph.add_edge(FlowEdge(
            edge_id=FlowGraph.new_id("e"),
            from_node=prev_id,
            to_node=next_id,
            label=EdgeLabel.DEFAULT,
        ))

        self._mark_dirty()
        self._bus.emit(EventName.CHAIN_STEPS_CHANGED)

    def update_step(self, index: int, step: BaseStep) -> None:
        """按线性索引更新一个 ACTION 节点"""
        action_nodes = self.graph.action_nodes()
        if 0 <= index < len(action_nodes):
            node = action_nodes[index]
            node.action = step
            node.comment = step.comment
            node.enabled = step.enabled
            self._mark_dirty()
            self._bus.emit(EventName.CHAIN_STEPS_CHANGED)

    def move_step(self, from_idx: int, to_idx: int) -> None:
        """交换两个 ACTION 节点的位置"""
        action_nodes = self.graph.action_nodes()
        if 0 <= from_idx < len(action_nodes) and 0 <= to_idx < len(action_nodes):
            n1 = action_nodes[from_idx]
            n2 = action_nodes[to_idx]
            # 交换内容
            n1.action, n2.action = n2.action, n1.action
            n1.comment, n2.comment = n2.comment, n1.comment
            n1.enabled, n2.enabled = n2.enabled, n1.enabled
            self._mark_dirty()
            self._bus.emit(EventName.CHAIN_STEPS_CHANGED)

    def _reorder_action_nodes(self, new_order: list[int]) -> None:
        """内部：按 new_order 重排 ACTION 节点的步骤相关状态（不发事件）。

        搬运 action/comment/enabled/breakpoint/error_config；非合法排列忽略。
        """
        action_nodes = self.graph.action_nodes()
        n = len(action_nodes)
        if len(new_order) != n or sorted(new_order) != list(range(n)):
            return  # 非合法排列，保持原序
        old = [
            (nd.action, nd.comment, nd.enabled, nd.breakpoint, nd.error_config)
            for nd in action_nodes
        ]
        for node, old_idx in zip(action_nodes, new_order):
            action, comment, enabled, bp, ec = old[old_idx]
            node.action = action
            node.comment = comment
            node.enabled = enabled
            node.breakpoint = bp
            node.error_config = ec

    def reorder_steps(self, new_order: list[int]) -> None:
        """按 new_order（原索引的新排列）insert 语义重排所有 ACTION 节点内容。

        new_order[i] = 新序列位置 i 应承载的原步骤索引。
        搬运每个 ACTION 节点的全部「步骤相关」状态——action/comment/enabled
        以及节点级 ``breakpoint``/``error_config``，使它们随步骤走到新槽位
        （否则断点/错误策略会留在原 node 槽位，落到搬来的另一步骤上）。
        不动 DAG 边；pos_x/pos_y/fsm_* 等节点固有属性不搬。
        非合法排列（长度不符或非 0..n-1）时静默忽略。
        """
        self._reorder_action_nodes(new_order)
        self._mark_dirty()
        self._bus.emit(EventName.CHAIN_STEPS_CHANGED)

    def duplicate_step(self, index: int) -> int:
        """深拷贝步骤，副本插入到 index 之后，返回副本新索引；越界返回 -1。

        用内部 ``_append_action_node`` + ``_reorder_action_nodes`` 组合，
        只发一次 CHAIN_STEPS_CHANGED，避免双 emit 导致的 UI 选中闪烁。
        """
        import copy
        steps = self.get_steps()
        if not (0 <= index < len(steps)):
            return -1
        self._append_action_node(copy.deepcopy(steps[index]))  # 副本暂在末尾
        n = len(self.get_steps())
        # 副本（末尾 n-1）insert 移动到 index+1
        self._reorder_action_nodes(build_move_order(n, n - 1, index + 1))
        self._mark_dirty()
        self._bus.emit(EventName.CHAIN_STEPS_CHANGED)  # 单次 emit
        return index + 1

    def clear_steps(self) -> None:
        """清空所有步骤，重置为空流程图"""
        self._init_empty_graph()
        self._bus.emit(EventName.CHAIN_STEPS_CHANGED)

    def reset(self) -> None:
        """清空步骤并重置配置文件名，恢复到全新状态"""
        self.clear_steps()
        self.current_profile_name = None

    def get_steps(self) -> list[BaseStep]:
        """获取线性步骤列表（向后兼容）"""
        return [
            node.action for node in self.graph.action_nodes()
            if node.action is not None
        ]

    @property
    def chain_name(self) -> str:
        return self.graph.name

    @chain_name.setter
    def chain_name(self, value: str) -> None:
        self.graph.name = value

    # ── 流程图操作（图级别，供工作流编辑器使用）──────────────────

    def add_node_at(
        self, node_type: NodeType, pos_x: int, pos_y: int,
        action_type: ActionType | None = None,
    ) -> FlowNode:
        """在指定位置创建新节点，可选指定动作类型"""
        prefix = "a" if node_type == NodeType.ACTION else "n"
        node_id = FlowGraph.new_id(prefix)
        action = None
        if node_type == NodeType.ACTION and action_type is not None:
            action = STEP_CLASSES[action_type]()
        node = FlowNode(
            node_id=node_id,
            node_type=node_type,
            action=action,
            pos_x=pos_x,
            pos_y=pos_y,
        )
        self.graph.add_node(node)
        self._mark_dirty()
        self._bus.emit(EventName.CHAIN_STEPS_CHANGED)
        return node

    def remove_node_by_id(self, node_id: str) -> None:
        """按 ID 移除节点及其关联的边"""
        node = self.graph.get_node(node_id)
        if not node:
            return
        # 保护原始 START/END 节点（ID 为 "start" 和 "end"）
        if node_id in ("start", "end"):
            return
        self.graph.remove_node(node_id)
        self._mark_dirty()
        self._bus.emit(EventName.CHAIN_STEPS_CHANGED)

    def add_edge_between(
        self, from_id: str, to_id: str, label: str = EdgeLabel.DEFAULT
    ) -> FlowEdge | None:
        """在两个节点之间创建边"""
        if from_id == to_id:
            return None
        from_node = self.graph.get_node(from_id)
        to_node = self.graph.get_node(to_id)
        if not from_node or not to_node:
            return None
        # 检查重复边
        for e in self.graph.edges:
            if e.from_node == from_id and e.to_node == to_id and e.label == label:
                return None
        edge = FlowEdge(
            edge_id=FlowGraph.new_id("e"),
            from_node=from_id,
            to_node=to_id,
            label=label,
        )
        self.graph.add_edge(edge)
        self._mark_dirty()
        self._bus.emit(EventName.CHAIN_STEPS_CHANGED)
        return edge

    def remove_edge_by_id(self, edge_id: str) -> None:
        """按 ID 移除一条边"""
        self.graph.remove_edge(edge_id)
        self._mark_dirty()
        self._bus.emit(EventName.CHAIN_STEPS_CHANGED)

    def update_node_position(self, node_id: str, x: int, y: int) -> None:
        """更新节点位置（纯视觉，不触发事件）"""
        node = self.graph.get_node(node_id)
        if node:
            node.pos_x = x
            node.pos_y = y

    # ── 流程图加载 ──────────────────────────────────────────

    def load_graph(self, graph: FlowGraph, profile_name: str) -> None:
        """加载完整流程图"""
        self.graph = graph
        self.current_profile_name = profile_name
        self.mark_clean()
        self._bus.emit(EventName.CHAIN_LOADED)

    def add_condition_node(self, node: FlowNode, branch_true_id: str, branch_false_id: str) -> None:
        """添加条件节点并设置分支边"""
        prev_id = self._find_node_before_end()
        self.graph.add_node(node)

        # prev -> node
        edge_in = FlowEdge(
            edge_id=FlowGraph.new_id("e"),
            from_node=prev_id,
            to_node=node.node_id,
            label=EdgeLabel.DEFAULT,
        )
        self.graph.add_edge(edge_in)

        # node -> true branch
        edge_true = FlowEdge(
            edge_id=FlowGraph.new_id("e"),
            from_node=node.node_id,
            to_node=branch_true_id,
            label=EdgeLabel.TRUE,
        )
        self.graph.add_edge(edge_true)

        # node -> false branch
        edge_false = FlowEdge(
            edge_id=FlowGraph.new_id("e"),
            from_node=node.node_id,
            to_node=branch_false_id,
            label=EdgeLabel.FALSE,
        )
        self.graph.add_edge(edge_false)

        self._mark_dirty()
        self._bus.emit(EventName.CHAIN_STEPS_CHANGED)

    def add_monitor(self, monitor: MonitorConfig) -> None:
        self.graph.monitors.append(monitor)
        self._bus.emit(EventName.CHAIN_MONITORS_CHANGED)

    def remove_monitor(self, index: int) -> None:
        if 0 <= index < len(self.graph.monitors):
            del self.graph.monitors[index]
            self._bus.emit(EventName.CHAIN_MONITORS_CHANGED)

    def update_monitor(self, index: int, monitor: MonitorConfig) -> None:
        if 0 <= index < len(self.graph.monitors):
            self.graph.monitors[index] = monitor
            self._bus.emit(EventName.CHAIN_MONITORS_CHANGED)

    def get_monitors(self) -> list[MonitorConfig]:
        return list(self.graph.monitors)

    # ── 执行状态 ──────────────────────────────────────────

    def set_executor_state(self, state: ExecutorState) -> None:
        self.executor_state = state
        self._bus.emit(EventName.EXECUTOR_STATE_CHANGED, state=state)

    # ── 区域 ──────────────────────────────────────────────

    def set_region(self, mode: str, rect: tuple | None = None) -> None:
        self.region_mode = mode
        self._bus.emit(EventName.REGION_CHANGED, mode=mode, rect=rect)

    # ── 内部辅助 ──────────────────────────────────────────

    def _find_node_before_end(self) -> str:
        """找到指向 END 的节点的 ID（最后一个非 END 节点）"""
        for edge in self.graph.get_incoming_edges("end"):
            if edge.label == EdgeLabel.DEFAULT:
                return edge.from_node
        return self.graph.start_node_id

    def _reroute_to_end(self, old_prev: str, new_node_id: str) -> None:
        """将 old_prev -> end 改为 old_prev -> new_node_id -> end"""
        for e in list(self.graph.get_outgoing_edges(old_prev)):
            if e.to_node == "end" and e.label == EdgeLabel.DEFAULT:
                self.graph.remove_edge(e.edge_id)
        # 添加新边
        self.graph.add_edge(FlowEdge(
            edge_id=FlowGraph.new_id("e"),
            from_node=old_prev,
            to_node=new_node_id,
            label=EdgeLabel.DEFAULT,
        ))
        self.graph.add_edge(FlowEdge(
            edge_id=FlowGraph.new_id("e"),
            from_node=new_node_id,
            to_node="end",
            label=EdgeLabel.DEFAULT,
        ))
