"""应用重启工具 — 用于切换 GUI 后端后平滑重启。

调用方负责在调用前停止所有独占资源（hotkey、executor、plugin watcher），
本模块只做两件事：启动新进程、终止旧进程。
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys

logger = logging.getLogger(__name__)


def restart_app() -> None:
    """启动新进程并立即终止当前进程。

    使用 os._exit(0) 而非 sys.exit(0)：
    - sys.exit(0) 抛出 SystemExit，会穿透 tkinter/Qt 事件循环导致 TclError
    - os._exit(0) 直接终止，不抛异常、不触发 atexit/__del__
    - 调用方已负责释放独占资源，剩余资源由 OS 回收
    """
    cmd = _build_cmd()
    logger.info("重启应用: %s", " ".join(cmd))

    subprocess.Popen(cmd, **_popen_kwargs())
    os._exit(0)


def _build_cmd() -> list[str]:
    """构建新进程命令。"""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable] + sys.argv


def _popen_kwargs() -> dict:
    """构建平台相关的 Popen 参数，确保新进程完全解耦。"""
    if sys.platform == "win32":
        return {
            "creationflags": (
                subprocess.CREATE_NEW_PROCESS_GROUP
                | subprocess.DETACHED_PROCESS
            ),
            "close_fds": True,
        }
    return {
        "start_new_session": True,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
