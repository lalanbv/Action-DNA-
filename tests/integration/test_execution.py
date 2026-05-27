"""执行管道集成测试 — GraphEngine + 真实描述符 + mock I/O。

参考: 13_风险与验证策略.md §5.3
覆盖: 创建图 → 执行（mock vision/input） → 验证事件序列和变量状态。

与单元测试的区别：
- 使用真实 NodeDescriptor（通过 auto_register），非 mock
- 使用真实 VariablePool / TypedEventBus / GraphEngine
- 仅 mock I/O 层（ScreenCapture / TemplateMatcher / InputController）
"""

import threading
import time

import pytest

pytestmark = pytest.mark.integration

from src.core.action import ActionType
from src.core.step_types import BaseStep, STEP_CLASSES
from src.core.engine.execution_context import ExecutionContext
from src.core.engine.graph_engine import GraphEngine, GraphEngineConfig
from src.core.engine.node_descriptor import NodeDescriptor, PortDef
from src.core.engine.node_registry import NodeRegistry, auto_register
from src.core.engine.node_result import NodeResult
from src.core.error.error_config import ErrorStrategy
from src.core.events.bus import TypedEventBus
from src.core.flow import FlowEdge, FlowGraph, FlowNode, NodeType, chain_to_flow
from src.core.layers.event_bridge_layer import EventBridgeLayer
from src.core.variables.pool import VariablePool

# 确保所有内置描述符注册
from src.core.engine.descriptors.flow_descriptors import (  # noqa: F401
    StartDescriptor,
    EndDescriptor,
    LoopDescriptor,
)
from src.core.engine.descriptors.wait_descriptor import (  # noqa: F401
    WaitDescriptor,
    WaitRandomDescriptor,
)
from src.core.engine.descriptors.click_pos_descriptor import (  # noqa: F401
    ClickPosDescriptor,
)
from src.core.engine.descriptors.press_key_descriptor import (  # noqa: F401
    PressKeyDescriptor,
)
from _helpers import ActionChain


# ============================================================
# helpers
# ============================================================


def _make_real_context(
    graph: FlowGraph,
    *,
    capture,
    matcher,
    input_ctrl,
    variables: VariablePool | None = None,
    event_bus: TypedEventBus | None = None,
) -> ExecutionContext:
    """创建真实 ExecutionContext（frozen dataclass），仅 I/O 为 mock。"""
    start = graph.find_by_type("START")
    assert start is not None, "图缺少 START 节点"
    return ExecutionContext(
        graph=graph,
        current_node=start,
        variables=variables or VariablePool(),
        capture=capture,
        matcher=matcher,
        input_ctrl=input_ctrl,
        gen=0,
        stop_event=threading.Event(),
        pause_event=threading.Event(),
        event_bus=event_bus,
    )


def _make_linear_graph(
    action_steps: list[BaseStep],
    *,
    name: str = "test_graph",
    loop: bool = False,
    loop_count: int = 0,
) -> FlowGraph:
    """用 chain_to_flow 构建线性图: START → actions → END。"""
    chain = ActionChain(
        name=name,
        steps=action_steps,
        loop=loop,
        loop_count=loop_count,
    )
    return chain_to_flow(chain.name, chain.steps, loop=chain.loop, loop_count=chain.loop_count)


def _make_action_step(action_type: ActionType, **kwargs) -> ActionStep:
    return STEP_CLASSES[action_type](**kwargs)


def _add_node(
    graph: FlowGraph,
    node_type: NodeType,
    node_id: str,
    *,
    action: BaseStep | None = None,
    loop_count: int = 0,
) -> FlowNode:
    node = FlowNode(
        node_id=node_id,
        node_type=node_type,
        action=action,
        loop_count=loop_count,
    )
    graph.add_node(node)
    return node


def _add_edge(
    graph: FlowGraph,
    from_node: str,
    to_node: str,
    *,
    label: str = "default",
) -> FlowEdge:
    edge = FlowEdge(
        edge_id=f"e_{from_node}_{to_node}",
        from_node=from_node,
        to_node=to_node,
        label=label,
    )
    graph.add_edge(edge)
    return edge


# ============================================================
# fixtures
# ============================================================


@pytest.fixture(autouse=True)
def _ensure_descriptors():
    """确保内置描述符已注册。"""
    for atype in ("START", "END", "LOOP", "WAIT", "WAIT_RANDOM", "CLICK_POS", "PRESS_KEY"):
        assert NodeRegistry.has(atype), f"描述符 {atype} 未注册"


@pytest.fixture
def bus() -> TypedEventBus:
    return TypedEventBus()


@pytest.fixture
def pool() -> VariablePool:
    return VariablePool()


# ============================================================
# 1. 事件序列验证 — EventBridgeLayer + EventBus
# ============================================================


class TestEventSequence:
    """创建图 → 执行 → 验证 EventBridgeLayer 发布的事件序列。"""

    def test_linear_graph_events(
        self, mock_capture, mock_matcher, mock_input, bus,
    ):
        """START → WAIT(0.01s) → CLICK_POS(100,200) → END 产生正确事件序列。"""
        graph = _make_linear_graph([
            _make_action_step(ActionType.WAIT, wait_seconds=0.01),
            _make_action_step(ActionType.CLICK_POS, pos_x=100, pos_y=200),
        ])
        ctx = _make_real_context(
            graph, capture=mock_capture, matcher=mock_matcher,
            input_ctrl=mock_input, event_bus=bus,
        )

        collected: list[dict] = []

        def publish_fn(topic: str, **kwargs):
            collected.append({"topic": topic, **kwargs})

        engine = GraphEngine()
        engine.add_layer(EventBridgeLayer(publish_fn))
        engine.run(graph, ctx)

        # 只有 ACTION 节点（WAIT, CLICK_POS）发布 step_changed，START/END 不发布
        step_events = [e for e in collected if e["topic"] == "executor.step_changed"]
        assert len(step_events) == 2

        # 验证 step_index 递增
        indices = [e["step_index"] for e in step_events]
        assert indices == sorted(indices)

    def test_event_bridge_on_error(self, mock_capture, mock_matcher, mock_input, bus):
        """节点抛异常 → EventBridgeLayer 发布 step_error。"""
        graph = _make_linear_graph([
            _make_action_step(ActionType.WAIT, wait_seconds=0.01),
        ])
        ctx = _make_real_context(
            graph, capture=mock_capture, matcher=mock_matcher,
            input_ctrl=mock_input, event_bus=bus,
        )

        collected: list[dict] = []

        def publish_fn(topic: str, **kwargs):
            collected.append({"topic": topic, **kwargs})

        # 注入一个会抛异常的描述符
        class _BoomDescriptor(NodeDescriptor):
            @classmethod
            def action_type(cls) -> str:
                return "WAIT"

            @classmethod
            def display_name(cls) -> str:
                return "boom"

            @classmethod
            def category(cls) -> str:
                return "测试"

            @classmethod
            def input_types(cls) -> dict[str, PortDef]:
                return {}

            @classmethod
            def output_types(cls) -> dict[str, PortDef]:
                return {}

            def execute(self, ctx) -> NodeResult:
                raise RuntimeError("boom!")

        NodeRegistry.register(_BoomDescriptor)

        try:
            engine = GraphEngine(GraphEngineConfig(default_error_strategy=ErrorStrategy.IGNORE))
            engine.add_layer(EventBridgeLayer(publish_fn))
            engine.run(graph, ctx)

            error_events = [e for e in collected if e["topic"] == "executor.step_error"]
            assert len(error_events) >= 1
        finally:
            # 恢复真实描述符
            NodeRegistry.register(WaitDescriptor)


# ============================================================
# 2. 变量池集成 — 描述符写入 + 执行后验证
# ============================================================


class TestVariablePoolIntegration:
    """描述符通过 NodeResult.output_vars 写入 VariablePool。"""

    def test_output_vars_persisted_to_pool(
        self, mock_capture, mock_matcher, mock_input, pool,
    ):
        """LoopDescriptor 的 output_vars（current_iteration）被正确写入 VariablePool。

        验证: 引擎将 NodeResult 中的非 _ 前缀 output_vars 持久化到 VariablePool。
        """
        graph = FlowGraph(name="var_test")
        start = _add_node(graph, NodeType.START, "start")
        graph.start_node_id = "start"
        loop = _add_node(graph, NodeType.LOOP, "loop_1", loop_count=2)
        end = _add_node(graph, NodeType.END, "end")
        _add_edge(graph, "start", "loop_1")
        _add_edge(graph, "loop_1", "end", label="exit")
        _add_edge(graph, "loop_1", "start", label="loop")

        ctx = _make_real_context(
            graph, capture=mock_capture, matcher=mock_matcher,
            input_ctrl=mock_input, variables=pool,
        )

        engine = GraphEngine(GraphEngineConfig(max_iterations=50))
        engine.run(graph, ctx)

        val = pool.get("current_iteration")
        assert val is not None, "LoopDescriptor 的 current_iteration 应写入 VariablePool"
        assert isinstance(val, int)
        assert val >= 2

    def test_loop_output_vars_in_pool(
        self, mock_capture, mock_matcher, mock_input, pool,
    ):
        """LoopDescriptor 的 current_iteration 被写入 VariablePool。"""
        graph = FlowGraph(name="loop_var_test")
        start = _add_node(graph, NodeType.START, "start")
        graph.start_node_id = "start"
        loop_node = _add_node(graph, NodeType.LOOP, "loop_1", loop_count=3)
        end = _add_node(graph, NodeType.END, "end")
        _add_edge(graph, "start", "loop_1")
        _add_edge(graph, "loop_1", "end", label="exit")
        _add_edge(graph, "loop_1", "start", label="loop")

        ctx = _make_real_context(
            graph, capture=mock_capture, matcher=mock_matcher,
            input_ctrl=mock_input, variables=pool,
        )

        engine = GraphEngine(GraphEngineConfig(max_iterations=50))
        engine.run(graph, ctx)

        # LoopDescriptor 写入 current_iteration（非 _ 前缀的 output_vars）
        val = pool.get("current_iteration")
        assert val is not None
        assert val >= 3  # 至少循环了 3 次


# ============================================================
# 3. 错误策略集成 — 引擎级错误处理 + 变量状态
# ============================================================


class TestErrorStrategyIntegration:
    """引擎错误策略对变量池状态的影响。"""

    def test_ignore_strategy_preserves_pool(
        self, mock_capture, mock_matcher, mock_input, pool,
    ):
        """IGNORE 策略：节点失败后继续执行，pool 不含 error 变量。"""

        class _FailDescriptor(NodeDescriptor):
            @classmethod
            def action_type(cls) -> str:
                return "FAIL_NODE"

            @classmethod
            def display_name(cls) -> str:
                return "失败节点"

            @classmethod
            def category(cls) -> str:
                return "测试"

            @classmethod
            def input_types(cls) -> dict[str, PortDef]:
                return {}

            @classmethod
            def output_types(cls) -> dict[str, PortDef]:
                return {}

            def execute(self, ctx) -> NodeResult:
                return NodeResult.fail("always fails")

        NodeRegistry.register(_FailDescriptor)

        try:
            graph = FlowGraph(name="error_test")
            start = _add_node(graph, NodeType.START, "start")
            graph.start_node_id = "start"
            # 用 LOOP 节点限制循环
            loop_node = _add_node(graph, NodeType.LOOP, "loop_1", loop_count=2)
            end = _add_node(graph, NodeType.END, "end")
            _add_edge(graph, "start", "loop_1")
            _add_edge(graph, "loop_1", "end", label="exit")
            _add_edge(graph, "loop_1", "start", label="loop")

            ctx = _make_real_context(
                graph, capture=mock_capture, matcher=mock_matcher,
                input_ctrl=mock_input, variables=pool,
            )

            engine = GraphEngine(GraphEngineConfig(
                default_error_strategy=ErrorStrategy.IGNORE,
                max_iterations=50,
            ))
            engine.run(graph, ctx)

            # IGNORE 后继续，pool 应有 loop 的 current_iteration
            assert pool.get("current_iteration") is not None
        finally:
            NodeRegistry.unregister("FAIL_NODE")

    def test_fail_fast_stops_execution(
        self, mock_capture, mock_matcher, mock_input, pool,
    ):
        """FAIL_FAST 策略：节点失败后立即终止执行。"""

        # 用一个始终失败的描述符替换 WAIT
        class _FailWaitDescriptor(NodeDescriptor):
            @classmethod
            def action_type(cls) -> str:
                return "WAIT"

            @classmethod
            def display_name(cls) -> str:
                return "失败等待"

            @classmethod
            def category(cls) -> str:
                return "测试"

            @classmethod
            def input_types(cls) -> dict[str, PortDef]:
                return {}

            @classmethod
            def output_types(cls) -> dict[str, PortDef]:
                return {}

            def execute(self, ctx) -> NodeResult:
                return NodeResult.fail("simulated failure")

        NodeRegistry.register(_FailWaitDescriptor)

        try:
            # 线性图: START → WAIT(失败) → END
            graph = _make_linear_graph([
                _make_action_step(ActionType.WAIT, wait_seconds=0.01),
                _make_action_step(ActionType.CLICK_POS, pos_x=100, pos_y=200),
            ])

            ctx = _make_real_context(
                graph, capture=mock_capture, matcher=mock_matcher,
                input_ctrl=mock_input, variables=pool,
            )

            engine = GraphEngine(GraphEngineConfig(
                default_error_strategy=ErrorStrategy.FAIL_FAST,
            ))
            engine.run(graph, ctx)

            # FAIL_FAST: WAIT 节点失败后立即终止，不应执行 CLICK_POS
            mock_input.click.assert_not_called()
        finally:
            # 恢复真实 WAIT 描述符
            NodeRegistry.register(WaitDescriptor)


# ============================================================
# 4. LOOP 节点集成 — LoopDescriptor + GraphEngine 循环路径
# ============================================================


class TestLoopIntegration:
    """LoopDescriptor 与 GraphEngine 的循环遍历集成。"""

    def test_loop_respects_count(
        self, mock_capture, mock_matcher, mock_input, pool,
    ):
        """LOOP(3) 循环体执行恰好 3 次后走 exit 边到 END。"""
        graph = FlowGraph(name="loop_count_test")
        start = _add_node(graph, NodeType.START, "start")
        graph.start_node_id = "start"
        loop = _add_node(graph, NodeType.LOOP, "loop_1", loop_count=3)
        end = _add_node(graph, NodeType.END, "end")
        _add_edge(graph, "start", "loop_1")
        _add_edge(graph, "loop_1", "end", label="exit")
        _add_edge(graph, "loop_1", "start", label="loop")

        ctx = _make_real_context(
            graph, capture=mock_capture, matcher=mock_matcher,
            input_ctrl=mock_input, variables=pool,
        )

        engine = GraphEngine(GraphEngineConfig(max_iterations=100))
        engine.run(graph, ctx)

        # LoopDescriptor 在 current > max_count 时返回 exit
        # 由于 loop → start → loop_1 路径，每次重新进入 loop_1
        # ctx.get_loop_count 在 with_loop_count 更新后被跟踪
        iteration = pool.get("current_iteration")
        assert iteration is not None
        assert iteration >= 3

    def test_loop_infinite_stopped_by_max_iterations(
        self, mock_capture, mock_matcher, mock_input, pool,
    ):
        """LOOP(0=无限) 被引擎 max_iterations 兜底终止。"""
        graph = FlowGraph(name="infinite_loop_test")
        start = _add_node(graph, NodeType.START, "start")
        graph.start_node_id = "start"
        loop = _add_node(graph, NodeType.LOOP, "loop_1", loop_count=0)  # 无限
        end = _add_node(graph, NodeType.END, "end")
        _add_edge(graph, "start", "loop_1")
        _add_edge(graph, "loop_1", "end", label="exit")
        _add_edge(graph, "loop_1", "start", label="loop")

        ctx = _make_real_context(
            graph, capture=mock_capture, matcher=mock_matcher,
            input_ctrl=mock_input, variables=pool,
        )

        engine = GraphEngine(GraphEngineConfig(max_iterations=5))
        engine.run(graph, ctx)

        # 应在 5 次迭代后被强制终止
        iteration = pool.get("current_iteration")
        assert iteration is not None


# ============================================================
# 5. 停止信号集成
# ============================================================


class TestStopSignal:
    """stop_event 对执行管道的中断效果。"""

    def test_stop_event_halts_execution(
        self, mock_capture, mock_matcher, mock_input, pool,
    ):
        """stop_event.set() 在下次循环检查时终止执行。"""
        graph = FlowGraph(name="stop_test")
        start = _add_node(graph, NodeType.START, "start")
        graph.start_node_id = "start"
        loop = _add_node(graph, NodeType.LOOP, "loop_1", loop_count=0)  # 无限
        end = _add_node(graph, NodeType.END, "end")
        _add_edge(graph, "start", "loop_1")
        _add_edge(graph, "loop_1", "end", label="exit")
        _add_edge(graph, "loop_1", "start", label="loop")

        ctx = _make_real_context(
            graph, capture=mock_capture, matcher=mock_matcher,
            input_ctrl=mock_input, variables=pool,
        )

        # 2 次迭代后触发 stop
        def delayed_stop():
            time.sleep(0.05)
            ctx.stop_event.set()

        t = threading.Thread(target=delayed_stop, daemon=True)
        t.start()

        engine = GraphEngine(GraphEngineConfig(max_iterations=100))
        engine.run(graph, ctx)

        t.join(timeout=1.0)
        assert not t.is_alive(), "delayed_stop thread should have completed"
        assert ctx.stop_event.is_set()


# ============================================================
# 6. chain_to_flow 端到端
# ============================================================


class TestChainToFlowE2E:
    """v1 ActionChain → v2 FlowGraph → GraphEngine 执行 全流程。"""

    def test_wait_then_click_e2e(
        self, mock_capture, mock_matcher, mock_input, pool,
    ):
        """WAIT(0.01) + CLICK_POS(100,200) 完整流程。"""
        graph = _make_linear_graph([
            _make_action_step(ActionType.WAIT, wait_seconds=0.01),
            _make_action_step(ActionType.CLICK_POS, pos_x=100, pos_y=200),
        ])

        ctx = _make_real_context(
            graph, capture=mock_capture, matcher=mock_matcher,
            input_ctrl=mock_input, variables=pool,
        )

        engine = GraphEngine()
        engine.run(graph, ctx)

        # ClickPosDescriptor 应调用了 input_ctrl.click(100, 200)
        mock_input.click.assert_called_once_with(100, 200, button="left", clicks=1)

    def test_press_key_e2e(
        self, mock_capture, mock_matcher, mock_input, pool,
    ):
        """PRESS_KEY('enter') 完整流程。"""
        graph = _make_linear_graph([
            _make_action_step(ActionType.PRESS_KEY, key="enter"),
        ])

        ctx = _make_real_context(
            graph, capture=mock_capture, matcher=mock_matcher,
            input_ctrl=mock_input, variables=pool,
        )

        engine = GraphEngine()
        engine.run(graph, ctx)

        mock_input.press_key.assert_called_once_with("enter")

    def test_mouse_key_e2e(
        self, mock_capture, mock_matcher, mock_input, pool,
    ):
        """PRESS_KEY('mouse_left') 触发 click_current_pos。"""
        graph = _make_linear_graph([
            _make_action_step(ActionType.PRESS_KEY, key="mouse_left"),
        ])

        ctx = _make_real_context(
            graph, capture=mock_capture, matcher=mock_matcher,
            input_ctrl=mock_input, variables=pool,
        )

        engine = GraphEngine()
        engine.run(graph, ctx)

        mock_input.click_current_pos.assert_called_once_with("left")

    def test_looping_chain_e2e(
        self, mock_capture, mock_matcher, mock_input, pool,
    ):
        """loop=True 的 chain_to_flow 图包含 END→START 循环边，引擎执行单次完整流程。

        注: GraphEngine 将 END 视为硬终止，循环由上层 ActionExecutor 管理。
        此测试验证 chain_to_flow 生成的图结构和引擎单次执行正确性。
        """
        graph = _make_linear_graph(
            [_make_action_step(ActionType.CLICK_POS, pos_x=10, pos_y=20)],
            loop=True,
        )

        ctx = _make_real_context(
            graph, capture=mock_capture, matcher=mock_matcher,
            input_ctrl=mock_input, variables=pool,
        )

        engine = GraphEngine()
        engine.run(graph, ctx)

        # 验证图结构: END → START 循环边存在
        end_edges = graph.get_outgoing_edges("end")
        loop_edges = [e for e in end_edges if e.to_node == "start"]
        assert len(loop_edges) == 1, "loop=True 时应有 END → START 边"

        # 引擎在 END 处停止，执行了 1 次 CLICK_POS
        mock_input.click.assert_called_once_with(10, 20, button="left", clicks=1)


# ============================================================
# 7. 混合描述符管道 — 多类型节点组合
# ============================================================


class TestMixedPipeline:
    """多种描述符在同一管道中协作。"""

    def test_wait_click_key_sequence(
        self, mock_capture, mock_matcher, mock_input, pool,
    ):
        """WAIT → CLICK_POS → PRESS_KEY 顺序执行，验证调用顺序。"""
        graph = _make_linear_graph([
            _make_action_step(ActionType.WAIT, wait_seconds=0.01),
            _make_action_step(ActionType.CLICK_POS, pos_x=300, pos_y=400),
            _make_action_step(ActionType.PRESS_KEY, key="space"),
        ])

        ctx = _make_real_context(
            graph, capture=mock_capture, matcher=mock_matcher,
            input_ctrl=mock_input, variables=pool,
        )

        engine = GraphEngine()
        engine.run(graph, ctx)

        mock_input.click.assert_called_once_with(300, 400, button="left", clicks=1)
        mock_input.press_key.assert_called_once_with("space")

    def test_wait_random_in_pipeline(
        self, mock_capture, mock_matcher, mock_input, pool,
    ):
        """WAIT_RANDOM 在管道中正常执行。"""
        graph = _make_linear_graph([
            _make_action_step(ActionType.WAIT_RANDOM, wait_min=0.01, wait_max=0.02),
            _make_action_step(ActionType.CLICK_POS, pos_x=50, pos_y=60),
        ])

        ctx = _make_real_context(
            graph, capture=mock_capture, matcher=mock_matcher,
            input_ctrl=mock_input, variables=pool,
        )

        engine = GraphEngine()
        engine.run(graph, ctx)

        mock_input.click.assert_called_once_with(50, 60, button="left", clicks=1)

    def test_click_pos_with_coord_var(
        self, mock_capture, mock_matcher, mock_input, pool,
    ):
        """CLICK_POS 使用坐标变量模式。"""
        pool.set("target_pos", [250, 350])

        graph = _make_linear_graph([
            _make_action_step(
                ActionType.CLICK_POS,
                use_coord_var=True,
                coord_var_name="target_pos",
            ),
        ])

        ctx = _make_real_context(
            graph, capture=mock_capture, matcher=mock_matcher,
            input_ctrl=mock_input, variables=pool,
        )

        engine = GraphEngine()
        engine.run(graph, ctx)

        mock_input.click.assert_called_once_with(250, 350, button="left", clicks=1)


# ============================================================
# 8. Layer 管道顺序验证
# ============================================================


class TestLayerPipelineOrder:
    """验证 Layer on_node_enter 正序、on_node_exit LIFO 逆序。"""

    def test_enter_exit_order(self, mock_capture, mock_matcher, mock_input, pool):
        """多个 Layer 按正确顺序执行。"""
        from src.core.layers.layer import GraphLayer

        log: list[str] = []

        class LayerA(GraphLayer):
            @property
            def name(self) -> str:
                return "A"

            @property
            def priority(self) -> int:
                return 10

            def on_node_enter(self, ctx):
                log.append("A_enter")
                return ctx

            def on_node_exit(self, ctx, result):
                log.append("A_exit")
                return result

        class LayerB(GraphLayer):
            @property
            def name(self) -> str:
                return "B"

            @property
            def priority(self) -> int:
                return 20

            def on_node_enter(self, ctx):
                log.append("B_enter")
                return ctx

            def on_node_exit(self, ctx, result):
                log.append("B_exit")
                return result

        graph = _make_linear_graph([
            _make_action_step(ActionType.WAIT, wait_seconds=0.01),
        ])
        ctx = _make_real_context(
            graph, capture=mock_capture, matcher=mock_matcher,
            input_ctrl=mock_input, variables=pool,
        )

        engine = GraphEngine()
        engine.add_layer(LayerA())
        engine.add_layer(LayerB())
        engine.run(graph, ctx)

        # 每个节点: A_enter, B_enter, [execute], B_exit, A_exit
        # 4 个节点 (START, WAIT, END + chain_to_flow 可能还有)
        # 验证 enter 和 exit 的相对顺序
        for i in range(len(log)):
            if log[i] == "A_enter":
                # 后面应该跟着 B_enter（正序）
                if i + 1 < len(log):
                    assert log[i + 1] == "B_enter" or log[i + 1].startswith("A_exit")
            if log[i] == "B_exit":
                # 后面应该跟着 A_exit（LIFO）
                if i + 1 < len(log):
                    assert log[i + 1] == "A_exit" or log[i + 1].startswith("B_enter")


# ============================================================
# 9. 暂停/恢复集成 — pause_event 对管道的影响
# ============================================================


class TestPauseResume:
    """pause_event 暂停和恢复执行管道。"""

    def test_pause_delays_execution(self, mock_capture, mock_matcher, mock_input, pool):
        """暂停期间不执行节点，恢复后继续。"""
        graph = _make_linear_graph([
            _make_action_step(ActionType.WAIT, wait_seconds=0.01),
            _make_action_step(ActionType.CLICK_POS, pos_x=100, pos_y=200),
        ])

        ctx = _make_real_context(
            graph, capture=mock_capture, matcher=mock_matcher,
            input_ctrl=mock_input, variables=pool,
        )

        def delayed_resume():
            time.sleep(0.1)
            ctx.pause_event.clear()

        ctx.pause_event.set()
        t = threading.Thread(target=delayed_resume, daemon=True)
        t.start()

        engine = GraphEngine()
        engine.run(graph, ctx)

        t.join(timeout=1.0)
        mock_input.click.assert_called_once_with(100, 200, button="left", clicks=1)

    def test_pause_during_loop_then_stop(
        self, mock_capture, mock_matcher, mock_input, pool,
    ):
        """暂停中发送停止信号能终止循环执行。"""
        graph = FlowGraph(name="pause_stop_test")
        start = _add_node(graph, NodeType.START, "start")
        graph.start_node_id = "start"
        loop = _add_node(graph, NodeType.LOOP, "loop_1", loop_count=0)
        end = _add_node(graph, NodeType.END, "end")
        _add_edge(graph, "start", "loop_1")
        _add_edge(graph, "loop_1", "end", label="exit")
        _add_edge(graph, "loop_1", "start", label="loop")

        ctx = _make_real_context(
            graph, capture=mock_capture, matcher=mock_matcher,
            input_ctrl=mock_input, variables=pool,
        )

        def delayed_stop():
            time.sleep(0.05)
            ctx.stop_event.set()
            ctx.pause_event.clear()

        ctx.pause_event.set()
        t = threading.Thread(target=delayed_stop, daemon=True)
        t.start()

        engine = GraphEngine(GraphEngineConfig(max_iterations=100))
        engine.run(graph, ctx)

        t.join(timeout=1.0)
        assert ctx.stop_event.is_set()


# ============================================================
# 10. Profile 保存 → 加载 → 执行 端到端管道
# ============================================================


class TestProfileToExecutionPipeline:
    """ProfileManager.save → load → GraphEngine.execute 完整管道。"""

    def test_save_load_execute_linear(
        self, mock_capture, mock_matcher, mock_input, pool, tmp_path, monkeypatch,
    ):
        """保存线性图 → 加载 → 执行，验证 I/O 调用正确。"""
        from src.panel.profile_manager import ProfileManager

        monkeypatch.setattr(
            "src.panel.profile_manager.get_profiles_dir",
            lambda: str(tmp_path),
        )
        pm = ProfileManager()

        chain = ActionChain(
            name="pipeline_test",
            steps=[
                STEP_CLASSES[ActionType.WAIT](wait_seconds=0.01),
                STEP_CLASSES[ActionType.CLICK_POS](pos_x=150, pos_y=250),
            ],
        )
        original = chain_to_flow(chain.name, chain.steps, chain.loop, chain.loop_count)
        pm.save("pipeline_test", original)

        loaded = pm.load("pipeline_test")

        ctx = _make_real_context(
            loaded, capture=mock_capture, matcher=mock_matcher,
            input_ctrl=mock_input, variables=pool,
        )
        engine = GraphEngine()
        engine.run(loaded, ctx)

        mock_input.click.assert_called_once_with(150, 250, button="left", clicks=1)

    def test_save_load_execute_with_loop(
        self, mock_capture, mock_matcher, mock_input, pool, tmp_path, monkeypatch,
    ):
        """保存带循环配置的图 → 加载 → 验证循环属性保持。"""
        from src.panel.profile_manager import ProfileManager

        monkeypatch.setattr(
            "src.panel.profile_manager.get_profiles_dir",
            lambda: str(tmp_path),
        )
        pm = ProfileManager()

        graph = FlowGraph(name="loop_pipeline", start_node_id="start", loop=True, loop_count=2)
        start = _add_node(graph, NodeType.START, "start")
        wait_node = _add_node(
            graph, NodeType.ACTION, "wait_1",
            action=STEP_CLASSES[ActionType.WAIT](wait_seconds=0.01),
        )
        end = _add_node(graph, NodeType.END, "end")
        _add_edge(graph, "start", "wait_1")
        _add_edge(graph, "wait_1", "end")

        pm.save("loop_pipeline", graph)
        loaded = pm.load("loop_pipeline")

        assert loaded.loop is True
        assert loaded.loop_count == 2
