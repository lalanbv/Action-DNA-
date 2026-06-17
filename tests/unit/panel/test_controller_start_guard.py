"""控制器启动守卫测试 — 验证 executor 缺失时给出清晰错误而非静默 AttributeError。

背景: Windows 打包 exe 中,若分阶段服务初始化失败导致 executor 未注册,
页面拿到的 controller._executor 为 None。旧实现直接访问 self._executor.is_running
抛 AttributeError,被 Qt/Tk 槽静默吞掉(exe 无控制台),表现为「点启动完全无反应」。
本测试锁定新契约: start_chain 必须抛出带可读消息的 RuntimeError。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.core.events.bus import TypedEventBus
from src.panel.controllers.action_chain_controller import ActionChainController
from src.panel.controllers.workflow_controller import WorkflowController
from src.panel.models.chain_model import ChainModel
from src.panel.profile_manager import ProfileManager
from src.core.step_types import WaitStep


def _make_controller(cls, executor):
    """用给定 executor(可为 None)构造控制器。"""
    bus = TypedEventBus()
    model = ChainModel(bus)
    return cls(
        model=model,
        executor=executor,
        capture=MagicMock(),
        matcher=MagicMock(),
        profile_mgr=ProfileManager(),
        event_bus=bus,
        main_thread_schedule=lambda ms, cb: cb(),
    )


class TestExecutorMissingGuard:
    """executor 为 None 时,start_chain 必须抛 RuntimeError(可读消息),而非 AttributeError。"""

    def test_action_chain_raises_runtime_error_when_executor_none(self) -> None:
        controller = _make_controller(ActionChainController, executor=None)
        # 先加一个步骤,避免触发「无步骤」ValueError 干扰
        controller.model.add_step(WaitStep(wait_seconds=0.01))
        with pytest.raises(RuntimeError) as exc_info:
            controller.start_chain()
        # 错误消息必须可读,指向 executor/服务未就绪
        msg = str(exc_info.value)
        assert "executor" in msg.lower() or "服务" in msg or "就绪" in msg

    def test_workflow_raises_runtime_error_when_executor_none(self) -> None:
        controller = _make_controller(WorkflowController, executor=None)
        # workflow 检查 graph.nodes 非空(ChainModel 初始有 start/end),不会先因空图报错
        with pytest.raises(RuntimeError) as exc_info:
            controller.start_chain()
        msg = str(exc_info.value)
        assert "executor" in msg.lower() or "服务" in msg or "就绪" in msg

    def test_action_chain_works_when_executor_present(self) -> None:
        """正常路径不应被守卫影响:有 executor 时照常调用(不会抛 RuntimeError)。"""
        executor = MagicMock()
        executor.is_running = False
        controller = _make_controller(ActionChainController, executor=executor)
        controller.model.add_step(WaitStep(wait_seconds=0.01))
        controller.start_chain()  # 不应抛 RuntimeError
        executor.start.assert_called_once()
