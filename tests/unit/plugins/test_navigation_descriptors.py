"""NavigationPlugin 描述符执行单元测试。

逐一完成每日任务,确保代码和功能都完成 — D17 交付。

覆盖:
- MoveToDescriptor: 点击目标坐标并返回 arrived=True
- PathNavigateDescriptor: 逐点移动，支持中断检测
- ZoneSwitchDescriptor: 模板匹配找传送入口 + 可选确认
- TeleportDescriptor: 模板匹配找传送点 + 确认
- PathFollowDescriptor: 逐点移动（无中断检测）
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

import numpy as np
import pytest

from src.core.engine.execution_context import ExecutionContext
from src.core.engine.node_descriptor import NodeDescriptor
from src.core.engine.node_registry import NodeRegistry
from src.core.events.bus import TypedEventBus
from src.core.flow import FlowEdge, FlowGraph, FlowNode, NodeType
from src.core.plugins.plugin_loader import PluginLoader
from src.core.variables.pool import VariablePool


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture(autouse=True)
def _clear_registry():
    NodeRegistry.clear()
    yield
    NodeRegistry.clear()


@pytest.fixture
def node_registry() -> NodeRegistry:
    return NodeRegistry()


@pytest.fixture
def event_bus() -> TypedEventBus:
    return TypedEventBus()


@pytest.fixture
def mock_capture():
    from src.core.vision import ScreenCapture

    cap = MagicMock(spec=ScreenCapture)
    cap.grab.return_value = np.zeros((1080, 1920, 3), dtype=np.uint8)
    cap.to_logical.side_effect = lambda x, y: (x, y)
    return cap


@pytest.fixture
def mock_matcher():
    from src.core.vision import TemplateMatcher

    m = MagicMock(spec=TemplateMatcher)
    m.find.return_value = None
    m.find_all.return_value = []
    return m


@pytest.fixture
def mock_input():
    from src.core.input import InputController

    return MagicMock(spec=InputController)


@pytest.fixture(autouse=True)
def _load_plugins(
    node_registry: NodeRegistry,
    event_bus: TypedEventBus,
    mock_capture: MagicMock,
    mock_matcher: MagicMock,
    mock_input: MagicMock,
) -> None:
    loader = PluginLoader(
        node_registry=node_registry,
        event_bus=event_bus,
        screen_capture=mock_capture,
        template_matcher=mock_matcher,
        input_controller=mock_input,
    )
    loader.add_scan_dir("src/plugins/builtin")
    loader.scan()
    loaded, failed = loader.load_all()
    assert "navigation" in loaded
    assert failed == []


def _make_ctx(
    action: MagicMock,
    capture: MagicMock,
    matcher: MagicMock,
    input_ctrl: MagicMock,
    variables: VariablePool | None = None,
) -> ExecutionContext:
    graph = FlowGraph(name="nav_unit", start_node_id="start")
    graph.add_node(FlowNode(node_id="start", node_type=NodeType.START))
    current = FlowNode(node_id="n1", node_type=NodeType.ACTION, action=action)
    graph.add_node(current)
    graph.add_edge(FlowEdge(edge_id="e0", from_node="start", to_node="n1"))
    return ExecutionContext(
        graph=graph,
        current_node=current,
        variables=variables or VariablePool(),
        capture=capture,
        matcher=matcher,
        input_ctrl=input_ctrl,
        gen=0,
        stop_event=threading.Event(),
        pause_event=threading.Event(),
        event_bus=None,
    )


# ============================================================
# MoveToDescriptor
# ============================================================


class TestMoveToDescriptor:

    def test_clicks_target_and_arrives(
        self, node_registry: NodeRegistry,
        mock_capture: MagicMock, mock_matcher: MagicMock, mock_input: MagicMock,
    ) -> None:
        action = MagicMock()
        action.target_pos = (500, 600)

        desc_cls = node_registry.get("navigation.move_to")
        result = desc_cls().execute(
            _make_ctx(action, mock_capture, mock_matcher, mock_input),
        )

        assert result.success is True
        assert result.output_vars["arrived"] is True
        mock_input.click.assert_called_once_with(500, 600, button="left", clicks=1)


# ============================================================
# PathNavigateDescriptor
# ============================================================


class TestPathNavigateDescriptor:

    def test_completes_all_waypoints(
        self, node_registry: NodeRegistry,
        mock_capture: MagicMock, mock_matcher: MagicMock, mock_input: MagicMock,
    ) -> None:
        action = MagicMock()
        action.waypoints = [(100, 200), (300, 400), (500, 600)]
        action.step_delay = 0.01

        desc_cls = node_registry.get("navigation.path_navigate")
        result = desc_cls().execute(
            _make_ctx(action, mock_capture, mock_matcher, mock_input),
        )

        assert result.success is True
        assert result.output_vars["completed"] is True
        assert result.output_vars["interrupted"] is False
        assert result.output_vars["reached_index"] == 2
        assert mock_input.click.call_count == 3

    def test_interrupts_on_template_match(
        self, node_registry: NodeRegistry,
        mock_capture: MagicMock, mock_matcher: MagicMock, mock_input: MagicMock,
    ) -> None:
        mock_matcher.find.return_value = (10, 20, 30, 40)

        action = MagicMock()
        action.waypoints = [(100, 200), (300, 400), (500, 600)]
        action.step_delay = 0.01
        action.interrupt_template = "dest.png"
        action.interrupt_confidence = 0.8

        desc_cls = node_registry.get("navigation.path_navigate")
        result = desc_cls().execute(
            _make_ctx(action, mock_capture, mock_matcher, mock_input),
        )

        assert result.success is True
        assert result.output_vars["completed"] is False
        assert result.output_vars["interrupted"] is True
        assert result.output_vars["reached_index"] == 0

    def test_no_interrupt_without_template(
        self, node_registry: NodeRegistry,
        mock_capture: MagicMock, mock_matcher: MagicMock, mock_input: MagicMock,
    ) -> None:
        action = MagicMock()
        action.waypoints = [(10, 20)]
        action.step_delay = 0.01
        action.interrupt_template = None
        action.interrupt_confidence = 0.8

        desc_cls = node_registry.get("navigation.path_navigate")
        result = desc_cls().execute(
            _make_ctx(action, mock_capture, mock_matcher, mock_input),
        )

        assert result.output_vars["completed"] is True
        mock_capture.grab.assert_not_called()


# ============================================================
# ZoneSwitchDescriptor
# ============================================================


class TestZoneSwitchDescriptor:

    def test_finds_zone_and_switches(
        self, node_registry: NodeRegistry,
        mock_capture: MagicMock, mock_matcher: MagicMock, mock_input: MagicMock,
    ) -> None:
        mock_matcher.find.return_value = (50, 60, 80, 90)
        action = MagicMock()
        action.zone_template = "portal.png"
        action.confidence = 0.8
        action.wait_after_switch = 0.01

        desc_cls = node_registry.get("navigation.zone_switch")
        result = desc_cls().execute(
            _make_ctx(action, mock_capture, mock_matcher, mock_input),
        )

        assert result.success is True
        assert result.output_vars["switched"] is True
        mock_input.click.assert_called()

    def test_zone_not_found(
        self, node_registry: NodeRegistry,
        mock_capture: MagicMock, mock_matcher: MagicMock, mock_input: MagicMock,
    ) -> None:
        mock_matcher.find.return_value = None
        action = MagicMock()
        action.zone_template = "portal.png"
        action.confidence = 0.8

        desc_cls = node_registry.get("navigation.zone_switch")
        result = desc_cls().execute(
            _make_ctx(action, mock_capture, mock_matcher, mock_input),
        )

        assert result.success is True
        assert result.output_vars["switched"] is False

    def test_switch_with_confirm(
        self, node_registry: NodeRegistry,
        mock_capture: MagicMock, mock_matcher: MagicMock, mock_input: MagicMock,
    ) -> None:
        mock_matcher.find.return_value = (10, 20, 30, 40)
        action = MagicMock()
        action.zone_template = "portal.png"
        action.confirm_template = "confirm.png"
        action.confidence = 0.8
        action.wait_after_switch = 0.01

        desc_cls = node_registry.get("navigation.zone_switch")
        result = desc_cls().execute(
            _make_ctx(action, mock_capture, mock_matcher, mock_input),
        )

        assert result.output_vars["switched"] is True
        assert mock_input.click.call_count == 2


# ============================================================
# TeleportDescriptor
# ============================================================


class TestTeleportDescriptor:

    def test_teleport_success(
        self, node_registry: NodeRegistry,
        mock_capture: MagicMock, mock_matcher: MagicMock, mock_input: MagicMock,
    ) -> None:
        mock_matcher.find.return_value = (100, 200, 50, 60)
        action = MagicMock()
        action.map_template = "tp_point.png"

        desc_cls = node_registry.get("navigation.teleport")
        result = desc_cls().execute(
            _make_ctx(action, mock_capture, mock_matcher, mock_input),
        )

        assert result.success is True
        assert result.output_vars["teleported"] is True
        mock_input.click.assert_called()

    def test_teleport_not_found(
        self, node_registry: NodeRegistry,
        mock_capture: MagicMock, mock_matcher: MagicMock, mock_input: MagicMock,
    ) -> None:
        mock_matcher.find.return_value = None
        action = MagicMock()
        action.map_template = "tp_point.png"

        desc_cls = node_registry.get("navigation.teleport")
        result = desc_cls().execute(
            _make_ctx(action, mock_capture, mock_matcher, mock_input),
        )

        assert result.success is False

    def test_teleport_with_confirm(
        self, node_registry: NodeRegistry,
        mock_capture: MagicMock, mock_matcher: MagicMock, mock_input: MagicMock,
    ) -> None:
        mock_matcher.find.return_value = (10, 20, 30, 40)
        action = MagicMock()
        action.map_template = "tp.png"
        action.confirm_button = "ok.png"

        desc_cls = node_registry.get("navigation.teleport")
        result = desc_cls().execute(
            _make_ctx(action, mock_capture, mock_matcher, mock_input),
        )

        assert result.output_vars["teleported"] is True
        assert mock_input.click.call_count == 2

    def test_teleport_confirm_not_found(
        self, node_registry: NodeRegistry,
        mock_capture: MagicMock, mock_matcher: MagicMock, mock_input: MagicMock,
    ) -> None:
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (10, 20, 30, 40)
            return None

        mock_matcher.find.side_effect = side_effect
        action = MagicMock()
        action.map_template = "tp.png"
        action.confirm_button = "ok.png"

        desc_cls = node_registry.get("navigation.teleport")
        result = desc_cls().execute(
            _make_ctx(action, mock_capture, mock_matcher, mock_input),
        )

        assert result.output_vars["teleported"] is False


# ============================================================
# PathFollowDescriptor
# ============================================================


class TestPathFollowDescriptor:

    def test_follows_all_waypoints(
        self, node_registry: NodeRegistry,
        mock_capture: MagicMock, mock_matcher: MagicMock, mock_input: MagicMock,
    ) -> None:
        action = MagicMock()
        action.waypoints = [(10, 20), (30, 40), (50, 60)]
        action.step_delay = 0.01

        desc_cls = node_registry.get("navigation.path_follow")
        result = desc_cls().execute(
            _make_ctx(action, mock_capture, mock_matcher, mock_input),
        )

        assert result.success is True
        assert result.output_vars["completed"] is True
        assert mock_input.click.call_count == 3
        mock_input.click.assert_any_call(10, 20, button="left", clicks=1)
        mock_input.click.assert_any_call(30, 40, button="left", clicks=1)
        mock_input.click.assert_any_call(50, 60, button="left", clicks=1)

    def test_single_waypoint(
        self, node_registry: NodeRegistry,
        mock_capture: MagicMock, mock_matcher: MagicMock, mock_input: MagicMock,
    ) -> None:
        action = MagicMock()
        action.waypoints = [(100, 200)]
        action.step_delay = 0.01

        desc_cls = node_registry.get("navigation.path_follow")
        result = desc_cls().execute(
            _make_ctx(action, mock_capture, mock_matcher, mock_input),
        )

        assert result.output_vars["completed"] is True
        mock_input.click.assert_called_once_with(100, 200, button="left", clicks=1)
