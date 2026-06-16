"""restart.py 单元测试 — 验证新进程的输出不被吞掉、防重入等不变量。

修复背景：旧实现把新进程 stdout/stderr 重定向到 DEVNULL，导致重启后
用户终端"看不到任何报错"。本测试锁定新行为：输出应继承父进程。
"""

from __future__ import annotations

import subprocess
import sys
from unittest import mock

import pytest

from src.utils import restart


class TestPopenKwargs:
    """_popen_kwargs() 必须保证新进程输出可见。"""

    def test_stdout_stderr_not_devnull(self) -> None:
        """新进程的 stdout/stderr 不应被重定向到 DEVNULL。

        否则重启后用户终端看不到任何日志/报错。
        """
        kwargs = restart._popen_kwargs()
        # 关键不变量：stdout 和 stderr 都不能是 DEVNULL
        assert kwargs.get("stdout") is not subprocess.DEVNULL, (
            "新进程 stdout 被吞掉，重启后终端将看不到日志"
        )
        assert kwargs.get("stderr") is not subprocess.DEVNULL, (
            "新进程 stderr 被吞掉，重启后终端将看不到报错"
        )

    def test_stdin_devnull_preserved(self) -> None:
        """stdin 保持 DEVNULL（新进程不需要终端输入）。"""
        kwargs = restart._popen_kwargs()
        assert kwargs.get("stdin") == subprocess.DEVNULL

    def test_unix_uses_start_new_session(self) -> None:
        """Unix 平台使用 start_new_session 让新进程与旧进程解耦。"""
        if sys.platform == "win32":
            pytest.skip("仅 Unix 平台")
        kwargs = restart._popen_kwargs()
        assert kwargs.get("start_new_session") is True


class TestRestartApp:
    """restart_app() 应启动新进程并退出，且不吞掉输出。"""

    def test_restart_does_not_pass_devnull_to_popen(self) -> None:
        """restart_app 调用 Popen 时，stdout/stderr 不能是 DEVNULL。"""
        with mock.patch.object(restart.subprocess, "Popen") as mock_popen, \
             mock.patch.object(restart.os, "_exit") as mock_exit:
            restart.restart_app()
            mock_popen.assert_called_once()
            _, kwargs = mock_popen.call_args
            assert kwargs.get("stdout") is not subprocess.DEVNULL
            assert kwargs.get("stderr") is not subprocess.DEVNULL
            mock_exit.assert_called_once_with(0)

    def test_build_cmd_uses_sys_argv(self) -> None:
        """非打包模式下，命令为 [sys.executable] + sys.argv。"""
        with mock.patch.object(restart.sys, "frozen", False, create=True):
            cmd = restart._build_cmd()
        assert cmd[0] == sys.executable
