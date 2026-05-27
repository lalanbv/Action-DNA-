"""插件系统向后兼容回归测试。

验证插件系统不破坏 v1/v2 现有执行路径:
- 插件加载/卸载不影响 v1 ActionChain 执行
- 插件描述符与内置描述符共存无冲突
- 插件 load/unload 循环不污染 NodeRegistry
- 插件热重载后执行结果保持正确
- ActionExecutor Facade 与 PluginLoader 协同工作
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

import numpy as np
import pytest

from src.core.action import ActionType
from src.core.step_types import BaseStep, STEP_CLASSES
from src.core.engine.execution_context import ExecutionContext
from src.core.engine.graph_engine import GraphEngine
from src.core.engine.node_registry import NodeRegistry
from src.core.events.bus import TypedEventBus
from src.core.flow import FlowEdge, FlowGraph, FlowNode, NodeType, chain_to_flow
from src.core.plugins.plugin_loader import PluginLoader, PluginState
from src.core.variables.pool import VariablePool

# 触发内置描述符的 @auto_register 装饰器（import 时自动注册）
import src.core.engine.descriptors as _desc  # noqa: F401
from _helpers import ActionChain


# ============================================================
# helpers
# ============================================================


def _mock_io():
    from src.core.vision import ScreenCapture, TemplateMatcher
    from src.core.input import InputController

    cap = MagicMock(spec=ScreenCapture)
    cap.grab.return_value = np.zeros((1080, 1920, 3), dtype=np.uint8)
    cap.to_logical.side_effect = lambda x, y: (x, y)
    matcher = MagicMock(spec=TemplateMatcher)
    matcher.find.return_value = None
    matcher.find_all.return_value = []
    input_ctrl = MagicMock(spec=InputController)
    return cap, matcher, input_ctrl


def _make_ctx(
    graph: FlowGraph,
    capture: MagicMock,
    matcher: MagicMock,
    input_ctrl: MagicMock,
    variables: VariablePool | None = None,
) -> ExecutionContext:
    start = graph.find_by_type("START")
    assert start is not None
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
        event_bus=None,
    )


def _run_v1_chain(
    chain: ActionChain,
    capture: MagicMock,
    matcher: MagicMock,
    input_ctrl: MagicMock,
) -> FlowGraph:
    graph = chain_to_flow(
        chain.name, chain.steps, loop=chain.loop, loop_count=chain.loop_count,
    )
    ctx = _make_ctx(graph, capture, matcher, input_ctrl)
    engine = GraphEngine()
    engine.run(graph, ctx)
    return graph


def _load_builtin_plugins(
    event_bus: TypedEventBus,
    capture: MagicMock,
    matcher: MagicMock,
    input_ctrl: MagicMock,
) -> PluginLoader:
    loader = PluginLoader(
        node_registry=NodeRegistry,
        event_bus=event_bus,
        screen_capture=capture,
        template_matcher=matcher,
        input_controller=input_ctrl,
    )
    loader.add_scan_dir("src/plugins/builtin")
    loader.scan()
    loaded, failed = loader.load_all()
    assert failed == []
    return loader


# ============================================================
# 1. 插件不影响 v1 ActionChain 执行
# ============================================================


class TestPluginDoesNotBreakV1:
    """插件加载前后，v1 ActionChain 执行结果一致。"""

    def test_v1_click_pos_unchanged_with_plugins(self) -> None:
        capture, matcher, input_ctrl = _mock_io()
        event_bus = TypedEventBus()

        chain = ActionChain(
            name="v1_no_plugin",
            steps=[STEP_CLASSES[ActionType.CLICK_POS](pos_x=111, pos_y=222)],
            loop=False,
        )
        _run_v1_chain(chain, capture, matcher, input_ctrl)
        no_plugin_calls = list(input_ctrl.click.call_args_list)

        _load_builtin_plugins(event_bus, capture, matcher, input_ctrl)

        input_ctrl.reset_mock()
        _run_v1_chain(chain, capture, matcher, input_ctrl)
        with_plugin_calls = list(input_ctrl.click.call_args_list)

        assert no_plugin_calls == with_plugin_calls

    def test_v1_press_key_unchanged_with_plugins(self) -> None:
        capture, matcher, input_ctrl = _mock_io()
        event_bus = TypedEventBus()

        chain = ActionChain(
            name="v1_key",
            steps=[STEP_CLASSES[ActionType.PRESS_KEY](key="space")],
            loop=False,
        )
        _run_v1_chain(chain, capture, matcher, input_ctrl)
        no_plugin_calls = list(input_ctrl.press_key.call_args_list)

        _load_builtin_plugins(event_bus, capture, matcher, input_ctrl)

        input_ctrl.reset_mock()
        _run_v1_chain(chain, capture, matcher, input_ctrl)
        with_plugin_calls = list(input_ctrl.press_key.call_args_list)

        assert no_plugin_calls == with_plugin_calls

    def test_v1_multi_step_chain_unchanged_with_plugins(self) -> None:
        capture, matcher, input_ctrl = _mock_io()
        event_bus = TypedEventBus()

        steps = [
            STEP_CLASSES[ActionType.WAIT](wait_seconds=0.01),
            STEP_CLASSES[ActionType.CLICK_POS](pos_x=300, pos_y=400),
            STEP_CLASSES[ActionType.PRESS_KEY](key="a"),
        ]
        chain = ActionChain(name="v1_multi", steps=steps, loop=False)

        _run_v1_chain(chain, capture, matcher, input_ctrl)
        no_plugin_clicks = list(input_ctrl.click.call_args_list)
        no_plugin_keys = list(input_ctrl.press_key.call_args_list)

        _load_builtin_plugins(event_bus, capture, matcher, input_ctrl)

        input_ctrl.reset_mock()
        _run_v1_chain(chain, capture, matcher, input_ctrl)
        with_plugin_clicks = list(input_ctrl.click.call_args_list)
        with_plugin_keys = list(input_ctrl.press_key.call_args_list)

        assert no_plugin_clicks == with_plugin_clicks
        assert no_plugin_keys == with_plugin_keys


# ============================================================
# 2. 内置描述符与插件描述符共存
# ============================================================


class TestBuiltinAndPluginDescriptorsCoexist:
    """内置描述符和插件描述符在同一个 NodeRegistry 中共存无冲突。"""

    def test_builtin_types_still_work_after_plugin_load(self) -> None:
        capture, matcher, input_ctrl = _mock_io()
        event_bus = TypedEventBus()
        _load_builtin_plugins(event_bus, capture, matcher, input_ctrl)

        assert NodeRegistry.has("CLICK_POS")
        desc_cls = NodeRegistry.get("CLICK_POS")
        assert desc_cls is not None

    def test_plugin_types_use_namespace_prefix(self) -> None:
        capture, matcher, input_ctrl = _mock_io()
        event_bus = TypedEventBus()
        _load_builtin_plugins(event_bus, capture, matcher, input_ctrl)

        assert NodeRegistry.has("combat.find_enemy")
        assert NodeRegistry.has("navigation.move_to")
        assert NodeRegistry.has("task.accept_quest")

    def test_plugin_unload_restores_registry(self) -> None:
        capture, matcher, input_ctrl = _mock_io()
        event_bus = TypedEventBus()
        loader = _load_builtin_plugins(event_bus, capture, matcher, input_ctrl)

        assert NodeRegistry.has("combat.find_enemy")
        assert NodeRegistry.has("CLICK_POS")

        loader.unload("combat")
        assert not NodeRegistry.has("combat.find_enemy")
        assert NodeRegistry.has("CLICK_POS")

    def test_full_unload_all_then_reload(self) -> None:
        capture, matcher, input_ctrl = _mock_io()
        event_bus = TypedEventBus()
        loader = _load_builtin_plugins(event_bus, capture, matcher, input_ctrl)

        plugin_keys = [
            "combat.find_enemy",
            "navigation.move_to",
            "task.accept_quest",
        ]
        for key in plugin_keys:
            assert NodeRegistry.has(key)

        loader.unload_all()
        for key in plugin_keys:
            assert not NodeRegistry.has(key)

        assert NodeRegistry.has("CLICK_POS")
        assert NodeRegistry.has("WAIT")

        loader.load_all()
        for key in plugin_keys:
            assert NodeRegistry.has(key)


# ============================================================
# 3. 插件 load/unload 不污染 NodeRegistry
# ============================================================


class TestPluginLoadUnloadRegistryIntegrity:
    """反复加载/卸载插件不污染全局 NodeRegistry。"""

    def test_repeated_load_unload_cycle(self) -> None:
        capture, matcher, input_ctrl = _mock_io()
        event_bus = TypedEventBus()
        loader = _load_builtin_plugins(event_bus, capture, matcher, input_ctrl)

        for _ in range(3):
            loader.unload("task")
            assert not NodeRegistry.has("task.accept_quest")

            loader.load("task")
            assert NodeRegistry.has("task.accept_quest")

    def test_registry_count_stable_after_cycle(self) -> None:
        capture, matcher, input_ctrl = _mock_io()
        event_bus = TypedEventBus()
        loader = _load_builtin_plugins(event_bus, capture, matcher, input_ctrl)

        count_before = len(NodeRegistry.all_types())

        loader.unload("navigation")
        count_after_unload = len(NodeRegistry.all_types())

        loader.load("navigation")
        count_after_reload = len(NodeRegistry.all_types())

        assert count_after_unload < count_before
        assert count_after_reload == count_before

    def test_no_stale_entries_after_unload(self) -> None:
        capture, matcher, input_ctrl = _mock_io()
        event_bus = TypedEventBus()
        loader = _load_builtin_plugins(event_bus, capture, matcher, input_ctrl)

        loader.unload_all()
        all_types = NodeRegistry.all_types()

        plugin_namespaced = [t for t in all_types if "." in t]
        assert plugin_namespaced == []


# ============================================================
# 4. 插件热重载后执行正确
# ============================================================


class TestPluginReloadExecutionCorrectness:
    """reload 后描述符执行结果与初次加载一致。"""

    def test_combat_find_enemy_after_reload(self) -> None:
        capture, matcher, input_ctrl = _mock_io()
        event_bus = TypedEventBus()
        loader = _load_builtin_plugins(event_bus, capture, matcher, input_ctrl)

        matcher.find.return_value = (50, 60, 80, 40)
        action = MagicMock()
        action.template = "enemy.png"
        action.confidence = 0.8
        action.click_target = True

        graph = FlowGraph(name="reload_test", start_node_id="start")
        graph.add_node(FlowNode(node_id="start", node_type=NodeType.START))
        current = FlowNode(node_id="n1", node_type=NodeType.ACTION, action=action)
        graph.add_node(current)
        graph.add_edge(FlowEdge(edge_id="e0", from_node="start", to_node="n1"))

        ctx = ExecutionContext(
            graph=graph,
            current_node=current,
            variables=VariablePool(),
            capture=capture,
            matcher=matcher,
            input_ctrl=input_ctrl,
            gen=0,
            stop_event=threading.Event(),
            pause_event=threading.Event(),
            event_bus=None,
        )

        desc_cls = NodeRegistry.get("combat.find_enemy")
        result1 = desc_cls().execute(ctx)

        loader.reload("combat")

        input_ctrl.reset_mock()
        desc_cls2 = NodeRegistry.get("combat.find_enemy")
        result2 = desc_cls2().execute(ctx)

        assert result1.success == result2.success
        assert result1.output_vars["enemy_found"] == result2.output_vars["enemy_found"]

    def test_navigation_move_to_after_reload(self) -> None:
        capture, matcher, input_ctrl = _mock_io()
        event_bus = TypedEventBus()
        loader = _load_builtin_plugins(event_bus, capture, matcher, input_ctrl)

        action = MagicMock()
        action.target_pos = (500, 600)

        graph = FlowGraph(name="reload_nav", start_node_id="start")
        graph.add_node(FlowNode(node_id="start", node_type=NodeType.START))
        current = FlowNode(node_id="n1", node_type=NodeType.ACTION, action=action)
        graph.add_node(current)
        graph.add_edge(FlowEdge(edge_id="e0", from_node="start", to_node="n1"))

        ctx = ExecutionContext(
            graph=graph,
            current_node=current,
            variables=VariablePool(),
            capture=capture,
            matcher=matcher,
            input_ctrl=input_ctrl,
            gen=0,
            stop_event=threading.Event(),
            pause_event=threading.Event(),
            event_bus=None,
        )

        desc_cls = NodeRegistry.get("navigation.move_to")
        result1 = desc_cls().execute(ctx)

        loader.reload("navigation")

        input_ctrl.reset_mock()
        desc_cls2 = NodeRegistry.get("navigation.move_to")
        result2 = desc_cls2().execute(ctx)

        assert result1.output_vars == result2.output_vars
        input_ctrl.click.assert_called_once_with(500, 600, button="left", clicks=1)


# ============================================================
# 5. ActionExecutor Facade 与 PluginLoader 协同
# ============================================================


class TestFacadeWithPluginLoader:
    """ActionExecutor + PluginLoader 同时工作时 v1/v2 执行正确。"""

    def test_converted_chain_works_with_loaded_plugins(self) -> None:
        from src.core.action_executor import ActionExecutor

        capture, matcher, input_ctrl = _mock_io()
        event_bus = TypedEventBus()
        _load_builtin_plugins(event_bus, capture, matcher, input_ctrl)

        ex = ActionExecutor(capture, matcher, input_ctrl)

        steps = [
            STEP_CLASSES[ActionType.WAIT](wait_seconds=0.01),
            STEP_CLASSES[ActionType.CLICK_POS](pos_x=99, pos_y=88),
        ]
        graph = chain_to_flow("facade_plugin", steps, loop=False)

        with pytest.MonkeyPatch.context() as m:
            original_thread = threading.Thread

            def mock_thread(*args, **kwargs):
                t = original_thread(*args, **kwargs)
                t.start = MagicMock()
                return t

            m.setattr(threading, "Thread", mock_thread)
            ex.start(graph)

        assert ex.is_running

    def test_v2_graph_works_with_loaded_plugins(self) -> None:
        from src.core.action_executor import ActionExecutor

        capture, matcher, input_ctrl = _mock_io()
        event_bus = TypedEventBus()
        _load_builtin_plugins(event_bus, capture, matcher, input_ctrl)

        ex = ActionExecutor(capture, matcher, input_ctrl)

        graph = FlowGraph(name="facade_v2_plugin", loop=False)
        graph.add_node(FlowNode(node_id="start", node_type=NodeType.START))
        graph.start_node_id = "start"
        graph.add_node(FlowNode(node_id="end", node_type=NodeType.END))
        graph.add_edge(FlowEdge(edge_id="e1", from_node="start", to_node="end"))

        with pytest.MonkeyPatch.context() as m:
            original_thread = threading.Thread

            def mock_thread(*args, **kwargs):
                t = original_thread(*args, **kwargs)
                t.start = MagicMock()
                return t

            m.setattr(threading, "Thread", mock_thread)
            ex.start(graph)

        assert ex.is_running


# ============================================================
# 6. 依赖链卸载顺序验证
# ============================================================


class TestDependencyChainUnloadOrder:
    """依赖链卸载顺序正确，不破坏依赖关系。"""

    def test_unload_dependency_prevents_dependent_reload(self) -> None:
        capture, matcher, input_ctrl = _mock_io()
        event_bus = TypedEventBus()
        loader = _load_builtin_plugins(event_bus, capture, matcher, input_ctrl)

        loader.unload("task")
        loader.unload("navigation")
        loader.unload("combat")

        with pytest.raises(RuntimeError, match="缺少依赖"):
            loader.load("navigation")

    def test_unload_all_reverses_dependency_order(self) -> None:
        capture, matcher, input_ctrl = _mock_io()
        event_bus = TypedEventBus()
        loader = _load_builtin_plugins(event_bus, capture, matcher, input_ctrl)

        loader.unload_all()
        for plugin_id in ("combat", "navigation", "task"):
            entry = loader.get_plugin(plugin_id)
            assert entry.state == PluginState.UNLOADED

    def test_reload_full_chain(self) -> None:
        capture, matcher, input_ctrl = _mock_io()
        event_bus = TypedEventBus()
        loader = _load_builtin_plugins(event_bus, capture, matcher, input_ctrl)

        loader.unload_all()

        loaded, failed = loader.load_all()
        assert "combat" in loaded
        assert "navigation" in loaded
        assert "task" in loaded
        assert failed == []

        assert NodeRegistry.has("combat.find_enemy")
        assert NodeRegistry.has("navigation.move_to")
        assert NodeRegistry.has("task.accept_quest")


# ============================================================
# 7. 插件描述符与内置描述符独立执行验证
# ============================================================


class TestMixedDescriptorExecution:
    """内置描述符和插件描述符可以独立执行且互不干扰。"""

    def test_builtin_descriptor_executes_correctly(self) -> None:
        capture, matcher, input_ctrl = _mock_io()
        event_bus = TypedEventBus()
        _load_builtin_plugins(event_bus, capture, matcher, input_ctrl)

        action = STEP_CLASSES[ActionType.CLICK_POS](pos_x=100, pos_y=200)
        graph = FlowGraph(name="builtin_exec", start_node_id="start")
        graph.add_node(FlowNode(node_id="start", node_type=NodeType.START))
        current = FlowNode(node_id="n1", node_type=NodeType.ACTION, action=action)
        graph.add_node(current)
        graph.add_edge(FlowEdge(edge_id="e0", from_node="start", to_node="n1"))

        ctx = ExecutionContext(
            graph=graph,
            current_node=current,
            variables=VariablePool(),
            capture=capture,
            matcher=matcher,
            input_ctrl=input_ctrl,
            gen=0,
            stop_event=threading.Event(),
            pause_event=threading.Event(),
            event_bus=None,
        )

        desc_cls = NodeRegistry.get("CLICK_POS")
        result = desc_cls().execute(ctx)

        assert result.success
        input_ctrl.click.assert_called_once_with(100, 200, button="left", clicks=1)

    def test_plugin_descriptor_executes_correctly(self) -> None:
        capture, matcher, input_ctrl = _mock_io()
        event_bus = TypedEventBus()
        _load_builtin_plugins(event_bus, capture, matcher, input_ctrl)

        action = MagicMock()
        action.target_pos = (300, 400)

        graph = FlowGraph(name="plugin_exec", start_node_id="start")
        graph.add_node(FlowNode(node_id="start", node_type=NodeType.START))
        current = FlowNode(node_id="n1", node_type=NodeType.ACTION, action=action)
        graph.add_node(current)
        graph.add_edge(FlowEdge(edge_id="e0", from_node="start", to_node="n1"))

        ctx = ExecutionContext(
            graph=graph,
            current_node=current,
            variables=VariablePool(),
            capture=capture,
            matcher=matcher,
            input_ctrl=input_ctrl,
            gen=0,
            stop_event=threading.Event(),
            pause_event=threading.Event(),
            event_bus=None,
        )

        desc_cls = NodeRegistry.get("navigation.move_to")
        result = desc_cls().execute(ctx)

        assert result.success
        input_ctrl.click.assert_called_once_with(300, 400, button="left", clicks=1)

    def test_builtin_and_plugin_descriptors_both_available(self) -> None:
        capture, matcher, input_ctrl = _mock_io()
        event_bus = TypedEventBus()
        _load_builtin_plugins(event_bus, capture, matcher, input_ctrl)

        builtin_cls = NodeRegistry.get("CLICK_POS")
        plugin_cls = NodeRegistry.get("navigation.move_to")

        assert builtin_cls is not None
        assert plugin_cls is not None
        assert builtin_cls is not plugin_cls
