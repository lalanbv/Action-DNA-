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


@pytest.fixture(autouse=True)
def _skip_tk_root_when_qt_cocoa_active():
    """macOS 防护：QApplication(cocoa) 与 tk.Tk() 不可同进程共存。

    根因：macOS 上 Qt6 用 cocoa 平台插件创建 QApplication 时会初始化
    NSApplication。此后在同一进程创建 tk.Tk()，Tcl/Tk9 在颜色初始化阶段
    (TkCreateFrame→Tk_InitOptions→Tk_Alloc3DBorderFromObj→Tk_GetColor→
    TkpGetColor→SetCGColorComponents→GetRGBA) 会对 ObjC 对象发送不识别的
    selector (doesNotRecognizeSelector)，抛出未捕获 NSException → SIGABRT。
    这是 Python try/except 拦不住的硬崩溃 —— 已用最小复现 + 强制 cocoa 的
    pytest 运行逐帧确认（与 crash report 完全一致）。

    本防护：当本进程已存在「非 offscreen」的 QApplication（即真实 macOS GUI
    平台，会与 Tk 冲突）时，把 ``tkinter.Tk.__init__`` 临时替换为抛
    ``pytest.skip()`` 的函数，使后续 Tk 测试优雅跳过而非硬崩。

    设计要点：
    - 仅 macOS(darwin)：Linux 下 Qt(xcb/wayland) 与 Tk(X11) 可共存，CI 跑
      ubuntu+offscreen；加平台守卫避免误伤 Linux Tk 契约测试覆盖。
    - 仅「非 offscreen」平台跳过：offscreen 不创建冲突的 NSApplication，
      Tk 测试仍可正常运行（保留 macOS offscreen 下的 Tk 覆盖）。
    - ``pytest.skip()`` 抛 Skipped（继承 BaseException，非 Exception），故
      即便 Tk 测试内部用 ``try/except Exception`` 包裹 tk.Tk()，skip 仍能
      正确传播（不会被吞）。
    - 进程级拦截 ``tkinter.Tk.__init__``，同时覆盖「fixture 创建」与「直接
      tk.Tk()」两种路径，无需改动各 Tk 测试文件。

    实现注意：generator fixture 必须每条路径都恰好 ``yield`` 一次，故先求值
    ``need_guard`` 再分流——无需拦截的路径仅 ``yield``（无 teardown）。
    """
    # 求值是否需要拦截（不满足任一条件则 Tk 自由创建）
    need_guard = False
    if sys.platform == "darwin":
        try:
            from PySide6.QtWidgets import QApplication
        except Exception:
            QApplication = None  # noqa: F841 — 无 PySide6：无需拦截
        else:
            qt_app = QApplication.instance()
            # cocoa 等 macOS 原生 GUI 平台已激活才需拦截（offscreen 不冲突）
            need_guard = (
                qt_app is not None and qt_app.platformName() != "offscreen"
            )

    if not need_guard:
        yield  # 无需拦截：Tk 自由创建（此路径无 teardown）
        return

    # 拦截 Tk root 创建 → 转为 pytest.skip
    import tkinter as _tk
    _orig_init = _tk.Tk.__init__

    def _guarded_init(self, *args, **kwargs):
        pytest.skip(
            "macOS: tk.Tk() 不可在已存在 QApplication(cocoa) 的进程中创建"
            "（Qt6/Tk9 颜色初始化 SIGABRT，无法被 try/except 捕获）；"
            "Tk 测试须在独立进程或 offscreen 下运行"
        )

    _tk.Tk.__init__ = _guarded_init
    try:
        yield
    finally:
        _tk.Tk.__init__ = _orig_init


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
