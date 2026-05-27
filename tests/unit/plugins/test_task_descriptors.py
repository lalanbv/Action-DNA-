"""TaskPlugin 描述符执行单元测试。

逐一完成每日任务,确保代码和功能都完成 — D17 交付。

覆盖:
- QuestAcceptDescriptor: 找NPC+接取任务
- DialogInteractDescriptor: 多轮对话推进+选项选择
- CompleteQuestDescriptor: 找NPC+领奖
- DailyResetDescriptor: 时间判断重置
"""

from __future__ import annotations

import threading
from datetime import datetime
from unittest.mock import patch
from unittest.mock import MagicMock

import numpy as np
import pytest

pytestmark = pytest.mark.unit

from src.core.engine.execution_context import ExecutionContext
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
    cap.grab.return_value = np.zeros((120, 160, 3), dtype=np.uint8)
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
    assert "task" in loaded
    assert failed == []


def _make_ctx(
    action: MagicMock,
    capture: MagicMock,
    matcher: MagicMock,
    input_ctrl: MagicMock,
    variables: VariablePool | None = None,
) -> ExecutionContext:
    graph = FlowGraph(name="task_unit", start_node_id="start")
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
# QuestAcceptDescriptor
# ============================================================


class TestQuestAcceptDescriptor:

    def test_accept_quest_npc_found(
        self, node_registry: NodeRegistry,
        mock_capture: MagicMock, mock_matcher: MagicMock, mock_input: MagicMock,
    ) -> None:
        mock_matcher.find.return_value = (100, 200, 60, 80)
        action = MagicMock()
        action.quest_npc_template = "npc.png"
        action.dialog_button_template = None

        desc_cls = node_registry.get("task.accept_quest")
        result = desc_cls().execute(
            _make_ctx(action, mock_capture, mock_matcher, mock_input),
        )

        assert result.success is True
        assert result.output_vars["accepted"] is True
        mock_input.click.assert_called_once()

    def test_accept_quest_npc_not_found(
        self, node_registry: NodeRegistry,
        mock_capture: MagicMock, mock_matcher: MagicMock, mock_input: MagicMock,
    ) -> None:
        mock_matcher.find.return_value = None
        action = MagicMock()
        action.quest_npc_template = "npc.png"

        desc_cls = node_registry.get("task.accept_quest")
        result = desc_cls().execute(
            _make_ctx(action, mock_capture, mock_matcher, mock_input),
        )

        assert result.success is True
        assert result.output_vars["accepted"] is False
        mock_input.click.assert_not_called()

    def test_accept_with_dialog_button(
        self, node_registry: NodeRegistry,
        mock_capture: MagicMock, mock_matcher: MagicMock, mock_input: MagicMock,
    ) -> None:
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (100, 200, 60, 80)
            return (300, 400, 80, 40)

        mock_matcher.find.side_effect = side_effect
        action = MagicMock()
        action.quest_npc_template = "npc.png"
        action.dialog_button_template = "accept_btn.png"

        desc_cls = node_registry.get("task.accept_quest")
        result = desc_cls().execute(
            _make_ctx(action, mock_capture, mock_matcher, mock_input),
        )

        assert result.output_vars["accepted"] is True
        assert mock_input.click.call_count == 2


# ============================================================
# DialogInteractDescriptor
# ============================================================


class TestDialogInteractDescriptor:

    def test_basic_dialog_advance(
        self, node_registry: NodeRegistry,
        mock_capture: MagicMock, mock_matcher: MagicMock, mock_input: MagicMock,
    ) -> None:
        action = MagicMock()
        action.click_region = None
        action.rounds = 3
        action.round_delay = 0.01

        desc_cls = node_registry.get("task.dialog_interact")
        result = desc_cls().execute(
            _make_ctx(action, mock_capture, mock_matcher, mock_input),
        )

        assert result.success is True
        assert result.output_vars["completed"] is True
        assert result.output_vars["option_selected"] is False
        assert mock_input.click.call_count == 3

    def test_dialog_with_option_selection(
        self, node_registry: NodeRegistry,
        mock_capture: MagicMock, mock_matcher: MagicMock, mock_input: MagicMock,
    ) -> None:
        mock_matcher.find.return_value = (50, 60, 80, 40)
        action = MagicMock()
        action.click_region = None
        action.rounds = 2
        action.round_delay = 0.01
        action.option_template = "opt.png"
        action.option_round = 1

        desc_cls = node_registry.get("task.dialog_interact")
        result = desc_cls().execute(
            _make_ctx(action, mock_capture, mock_matcher, mock_input),
        )

        assert result.output_vars["option_selected"] is True

    def test_dialog_option_not_found_falls_back(
        self, node_registry: NodeRegistry,
        mock_capture: MagicMock, mock_matcher: MagicMock, mock_input: MagicMock,
    ) -> None:
        mock_matcher.find.return_value = None
        action = MagicMock()
        action.click_region = None
        action.rounds = 1
        action.round_delay = 0.01
        action.option_template = "opt.png"
        action.option_round = 1

        desc_cls = node_registry.get("task.dialog_interact")
        result = desc_cls().execute(
            _make_ctx(action, mock_capture, mock_matcher, mock_input),
        )

        assert result.output_vars["option_selected"] is False
        mock_input.click.assert_called()


# ============================================================
# CompleteQuestDescriptor
# ============================================================


class TestCompleteQuestDescriptor:

    def test_complete_quest_success(
        self, node_registry: NodeRegistry,
        mock_capture: MagicMock, mock_matcher: MagicMock, mock_input: MagicMock,
    ) -> None:
        mock_matcher.find.return_value = (200, 300, 50, 60)
        action = MagicMock()
        action.npc_template = "turnin_npc.png"

        desc_cls = node_registry.get("task.complete_quest")
        result = desc_cls().execute(
            _make_ctx(action, mock_capture, mock_matcher, mock_input),
        )

        assert result.success is True
        assert result.output_vars["completed"] is True
        mock_input.click.assert_called()

    def test_complete_quest_npc_not_found(
        self, node_registry: NodeRegistry,
        mock_capture: MagicMock, mock_matcher: MagicMock, mock_input: MagicMock,
    ) -> None:
        mock_matcher.find.return_value = None
        action = MagicMock()
        action.npc_template = "turnin_npc.png"

        desc_cls = node_registry.get("task.complete_quest")
        result = desc_cls().execute(
            _make_ctx(action, mock_capture, mock_matcher, mock_input),
        )

        assert result.output_vars["completed"] is False

    def test_complete_with_reward_button(
        self, node_registry: NodeRegistry,
        mock_capture: MagicMock, mock_matcher: MagicMock, mock_input: MagicMock,
    ) -> None:
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (100, 200, 50, 60)
            return (400, 500, 80, 40)

        mock_matcher.find.side_effect = side_effect
        action = MagicMock()
        action.npc_template = "npc.png"
        action.reward_button_template = "reward.png"

        desc_cls = node_registry.get("task.complete_quest")
        result = desc_cls().execute(
            _make_ctx(action, mock_capture, mock_matcher, mock_input),
        )

        assert result.output_vars["completed"] is True
        assert mock_input.click.call_count == 2


# ============================================================
# DailyResetDescriptor
# ============================================================


class TestDailyResetDescriptor:

    def test_invalid_time_format_returns_fail(
        self, node_registry: NodeRegistry,
        mock_capture: MagicMock, mock_matcher: MagicMock, mock_input: MagicMock,
    ) -> None:
        action = MagicMock()
        action.reset_time = "99:99"

        desc_cls = node_registry.get("task.daily_reset")
        result = desc_cls().execute(
            _make_ctx(action, mock_capture, mock_matcher, mock_input),
        )

        assert result.success is False
        assert "时间格式错误" in str(result.error)

    def test_should_reset_at_correct_time(
        self,
        node_registry: NodeRegistry,
        mock_capture: MagicMock, mock_matcher: MagicMock, mock_input: MagicMock,
    ) -> None:
        fixed_now = datetime(2026, 4, 29, 14, 30, 0)
        action = MagicMock()
        action.reset_time = "14:30"

        desc_cls = node_registry.get("task.daily_reset")
        mock_dt = MagicMock()
        mock_dt.now.return_value = fixed_now
        globs = desc_cls.execute.__globals__
        original = globs["datetime"]
        try:
            globs["datetime"] = mock_dt
            result = desc_cls().execute(
                _make_ctx(action, mock_capture, mock_matcher, mock_input),
            )
        finally:
            globs["datetime"] = original

        assert result.output_vars["should_reset"] is True

    def test_should_not_reset_at_wrong_time(
        self,
        node_registry: NodeRegistry,
        mock_capture: MagicMock, mock_matcher: MagicMock, mock_input: MagicMock,
    ) -> None:
        fixed_now = datetime(2026, 4, 29, 14, 30, 0)
        action = MagicMock()
        action.reset_time = "03:33"

        desc_cls = node_registry.get("task.daily_reset")
        mock_dt = MagicMock()
        mock_dt.now.return_value = fixed_now
        globs = desc_cls.execute.__globals__
        original = globs["datetime"]
        try:
            globs["datetime"] = mock_dt
            result = desc_cls().execute(
                _make_ctx(action, mock_capture, mock_matcher, mock_input),
            )
        finally:
            globs["datetime"] = original

        assert result.output_vars["should_reset"] is False
