"""共享测试 fixtures。

参考: 13_风险与验证策略.md §5.5 测试基础设施
"""

import sys
from pathlib import Path

import numpy as np
import pytest
from unittest.mock import MagicMock

# Ensure tests/ is on sys.path so _helpers can be imported
_tests_dir = str(Path(__file__).parent)
if _tests_dir not in sys.path:
    sys.path.insert(0, _tests_dir)

from src.core.action import ActionType
from src.core.step_types import BaseStep, STEP_CLASSES
from src.core.variables.pool import VariablePool
from _helpers import ActionChain

# 触发所有 @auto_register 装饰器（首次 import 时注册内置描述符）
import src.core.engine.descriptors as _builtin_descriptors  # noqa: F401
from src.core.engine.node_registry import NodeRegistry


# ============================================================
# NodeRegistry 隔离 — 确保每个测试都有内置描述符
# ============================================================

_ALL_BUILTIN_DESCRIPTOR_CLASSES = [
    _builtin_descriptors.StartDescriptor,
    _builtin_descriptors.EndDescriptor,
    _builtin_descriptors.LoopDescriptor,
    _builtin_descriptors.MergeDescriptor,
    _builtin_descriptors.WaitDescriptor,
    _builtin_descriptors.WaitRandomDescriptor,
    _builtin_descriptors.ClickPosDescriptor,
    _builtin_descriptors.ClickImageDescriptor,
    _builtin_descriptors.PressKeyDescriptor,
    _builtin_descriptors.ConditionDescriptor,
    _builtin_descriptors.HoldKeyDescriptor,
    _builtin_descriptors.MouseScrollDescriptor,
    _builtin_descriptors.MouseDragDescriptor,
    _builtin_descriptors.KeyComboDescriptor,
    _builtin_descriptors.MultiKeySequenceDescriptor,
    _builtin_descriptors.IdleBehaviorDescriptor,
    _builtin_descriptors.StartTimerDescriptor,
    _builtin_descriptors.PixelSearchDescriptor,
    _builtin_descriptors.OCRDescriptor,
]


def _ensure_builtins_registered() -> None:
    """重新注册所有内置描述符（处理 NodeRegistry.clear() 后的恢复）。"""
    for cls in _ALL_BUILTIN_DESCRIPTOR_CLASSES:
        key = cls.action_type()
        if not NodeRegistry.has(key):
            NodeRegistry.register(cls)


@pytest.fixture(autouse=True)
def _restore_builtin_descriptors():
    """每个测试前确保内置描述符已注册。

    部分 test 调用 NodeRegistry.clear() 会清空全局注册表，
    导致后续测试找不到内置描述符。此 fixture 在每个测试
    前检查并恢复必要的注册项。
    """
    _ensure_builtins_registered()
    yield
    _ensure_builtins_registered()


# ============================================================
# 变量系统 fixtures
# ============================================================


@pytest.fixture
def pool() -> VariablePool:
    """全新的 VariablePool 实例。"""
    return VariablePool()


# ============================================================
# 视觉/输入 mock fixtures
# ============================================================


@pytest.fixture
def mock_capture():
    """模拟 ScreenCapture，返回预定义截图数据，避免真实屏幕截图。"""
    from src.core.vision import ScreenCapture

    capture = MagicMock(spec=ScreenCapture)
    capture.grab.return_value = np.zeros((120, 160, 3), dtype=np.uint8)
    capture.grab_reuse.return_value = np.zeros((120, 160, 3), dtype=np.uint8)
    capture.to_logical.side_effect = lambda x, y: (x, y)
    capture.to_logical_rect.side_effect = lambda r: r
    capture.get_screen_size.return_value = (1920, 1080)
    capture.is_screen_black.return_value = False
    capture.scale_factor = 1.0
    return capture


@pytest.fixture
def mock_matcher():
    """模拟 TemplateMatcher，默认返回未找到，可通过 side_effect 覆盖。"""
    from src.core.vision import TemplateMatcher

    matcher = MagicMock(spec=TemplateMatcher)
    matcher.find.return_value = None
    matcher.find_all.return_value = []
    return matcher


@pytest.fixture
def mock_input():
    """模拟 InputController，记录所有调用但不执行真实操作。"""
    from src.core.input import InputController

    controller = MagicMock(spec=InputController)
    controller.move_to.return_value = (347, 519)
    controller.click_rect_center.return_value = (100, 200)
    controller.wait_interruptible.return_value = False
    controller.wait_random_interruptible.return_value = False
    controller.key_hold_interruptible.return_value = False
    controller.key_combo_staggered.return_value = False
    return controller


# ============================================================
# 动作链 fixtures
# ============================================================


@pytest.fixture
def sample_chain() -> ActionChain:
    """测试用动作链: WAIT -> CLICK_POS"""
    return ActionChain(
        name="test_chain",
        steps=[
            STEP_CLASSES[ActionType.WAIT](wait_seconds=0.01),
            STEP_CLASSES[ActionType.CLICK_POS](pos_x=100, pos_y=200),
        ],
        loop=False,
    )


@pytest.fixture
def sample_chain_with_image() -> ActionChain:
    """测试用动作链: CLICK_IMAGE（需要模板图片）"""
    return ActionChain(
        name="test_image_chain",
        steps=[
            STEP_CLASSES[ActionType.CLICK_IMAGE](
                image_path="test_template.png",
                threshold=0.8,
            ),
        ],
        loop=False,
    )
