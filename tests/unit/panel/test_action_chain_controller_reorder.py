"""ActionChainController 重排 / 复制 / 移动到序号 透传 + idle 守卫测试。

验证 controller 把 reorder_steps / duplicate_step / move_to_index 透传给 model，
且执行中（is_running=True）所有写操作被 _require_idle 拒绝（RuntimeError）。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.core.action import ActionType
from src.core.events.bus import TypedEventBus
from src.core.step_types import STEP_CLASSES
from src.panel.controllers.action_chain_controller import ActionChainController
from src.panel.models.chain_model import ChainModel
from src.panel.profile_manager import ProfileManager


def _make_controller(running: bool = False) -> ActionChainController:
    """构造 idle（默认）或 running 的 controller，依赖 mock 隔离。"""
    bus = TypedEventBus()
    model = ChainModel(bus)
    executor = MagicMock()
    executor.is_running = running
    return ActionChainController(
        model=model,
        executor=executor,
        capture=MagicMock(),
        matcher=MagicMock(),
        profile_mgr=ProfileManager(),
        event_bus=bus,
        main_thread_schedule=lambda ms, cb: cb(),
    )


def _add_types(ctrl: ActionChainController, *types: ActionType) -> None:
    for at in types:
        ctrl.model.add_step(STEP_CLASSES[at]())


class TestControllerReorder:
    def test_reorder_delegates(self) -> None:
        ctrl = _make_controller()
        _add_types(ctrl, ActionType.CLICK_POS, ActionType.WAIT,
                   ActionType.PRESS_KEY, ActionType.WAIT_RANDOM)
        ctrl.reorder_steps([1, 2, 0, 3])
        assert [s.action_type for s in ctrl.model.get_steps()] == [
            ActionType.WAIT, ActionType.PRESS_KEY,
            ActionType.CLICK_POS, ActionType.WAIT_RANDOM]

    def test_reorder_blocked_when_running(self) -> None:
        ctrl = _make_controller(running=True)
        _add_types(ctrl, ActionType.WAIT, ActionType.PRESS_KEY)
        with pytest.raises(RuntimeError):
            ctrl.reorder_steps([1, 0])


class TestControllerDuplicate:
    def test_returns_index_and_inserts_after(self) -> None:
        ctrl = _make_controller()
        _add_types(ctrl, ActionType.WAIT, ActionType.PRESS_KEY)
        assert ctrl.duplicate_step(0) == 1
        assert [s.action_type for s in ctrl.model.get_steps()] == [
            ActionType.WAIT, ActionType.WAIT, ActionType.PRESS_KEY]

    def test_blocked_when_running(self) -> None:
        ctrl = _make_controller(running=True)
        _add_types(ctrl, ActionType.WAIT)
        with pytest.raises(RuntimeError):
            ctrl.duplicate_step(0)


class TestControllerMoveToIndex:
    def test_move_to_index_insert_semantic(self) -> None:
        ctrl = _make_controller()
        _add_types(ctrl, ActionType.WAIT, ActionType.PRESS_KEY, ActionType.WAIT_RANDOM)
        ctrl.move_to_index(0, 2)  # A→末尾：[B,C,A]
        assert [s.action_type for s in ctrl.model.get_steps()] == [
            ActionType.PRESS_KEY, ActionType.WAIT_RANDOM, ActionType.WAIT]

    def test_noop_when_same_index(self) -> None:
        ctrl = _make_controller()
        _add_types(ctrl, ActionType.WAIT, ActionType.PRESS_KEY)
        ctrl.move_to_index(0, 0)
        assert [s.action_type for s in ctrl.model.get_steps()] == [
            ActionType.WAIT, ActionType.PRESS_KEY]

    def test_blocked_when_running(self) -> None:
        ctrl = _make_controller(running=True)
        _add_types(ctrl, ActionType.WAIT, ActionType.PRESS_KEY, ActionType.WAIT_RANDOM)
        with pytest.raises(RuntimeError):
            ctrl.move_to_index(0, 2)
