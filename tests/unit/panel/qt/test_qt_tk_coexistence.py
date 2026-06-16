"""回归：macOS 上 pytest 混合收集 Qt(cocoa) + Tk 测试不再硬崩。

背景：macOS 上 Qt6 用 cocoa 平台插件创建 QApplication 会初始化 NSApplication，
此后同进程创建 tk.Tk() 会触发 Tcl/Tk9 颜色初始化阶段的 SIGABRT（无法被
try/except 捕获；crash report: Tkapp_New→GetRGBA→doesNotRecognizeSelector）。
tests/conftest.py 的 ``_skip_tk_root_when_qt_cocoa_active`` autouse fixture
在此情况下把 ``tkinter.Tk()`` 创建拦截为 ``pytest.skip``。

本测试验证该防护：强制 cocoa 平台跑「Qt 测试 + Tk 测试」混合收集，断言
Tk 测试被 skip 且进程不硬崩（改动前此命令 SIGABRT，退出码 -6）。

darwin-only + 子进程隔离：cocoa QApplication 与 QT_QPA_PLATFORM 是进程级
全局状态，直接在主 pytest 进程创建会污染同会话其它 Qt 测试；故用子进程
跑真实测试文件（自动加载 tests/conftest.py 的防护），主进程零污染、零递归。
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

#: 混合收集的两个代表性文件：前者建 QApplication(cocoa)，后者建 tk.Tk()。
_QT_TEST = "tests/unit/panel/qt/test_fusion_style.py"
_TK_TEST = "tests/unit/panel/test_multi_template_editor.py"


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS 专属 Qt(cocoa)/Tk 冲突")
def test_mixed_cocoa_pytest_does_not_crash():
    """强制 cocoa 跑混合 Qt+Tk pytest：Tk 测试须 skip，进程不硬崩。

    断言两件事：
    1. ``returncode == 0`` —— 改动前为 SIGABRT（returncode 为负，通常 -6）。
    2. 输出含 "skipped" —— Tk 测试被 conftest 防护拦截为 skip（而非执行崩溃）。
    """
    env = {**os.environ, "QT_QPA_PLATFORM": "cocoa"}
    result = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            _QT_TEST,   # 建 QApplication(cocoa)，platformName 非 offscreen
            _TK_TEST,   # 建 tk.Tk() → 应被 conftest 拦截为 skip
            "-p", "no:cacheprovider", "-q", "--no-header",
        ],
        capture_output=True,
        text=True,
        env=env,
    )

    # 1. 不硬崩（核心：改动前这里 SIGABRT，returncode 为负）
    assert result.returncode == 0, (
        f"混合 cocoa pytest 硬崩（期望 skip 而非 crash）：\n"
        f"returncode={result.returncode}\n"
        f"--- stdout (tail) ---\n{result.stdout[-1500:]}\n"
        f"--- stderr (tail) ---\n{result.stderr[-800:]}"
    )
    # 2. Tk 测试被 skip
    assert "skipped" in result.stdout.lower(), (
        f"期望 Tk 测试被 conftest 防护 skip，实际输出：\n{result.stdout[-1500:]}"
    )
