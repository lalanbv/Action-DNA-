"""屏幕防休眠 — 跨平台阻止显示器和系统休眠"""

import subprocess
import threading

from src.core.logger import log
from src.utils.i18n import t
from src.utils.platform import IS_MACOS, IS_WINDOWS


class DisplaySleepPreventer:
    """跨平台防止屏幕休眠

    macOS: 使用 caffeinate -d -i 阻止显示器和系统空闲休眠
    Windows: 使用 SetThreadExecutionState 阻止显示器和系统休眠
    """

    def __init__(self):
        self._process: subprocess.Popen | None = None
        self._active = False
        self._lock = threading.Lock()

    def start(self) -> None:
        """启动防休眠"""
        with self._lock:
            if self._active:
                return
            try:
                if IS_MACOS:
                    self._process = subprocess.Popen(
                        ["caffeinate", "-d", "-i"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    self._active = True
                    log.info(t("screen_guard.log.enabled_caffeinate"))
                elif IS_WINDOWS:
                    import ctypes
                    ES_CONTINUOUS = 0x80000000
                    ES_DISPLAY_REQUIRED = 0x00000002
                    ES_SYSTEM_REQUIRED = 0x00000001
                    ctypes.windll.kernel32.SetThreadExecutionState(  # type: ignore[attr-defined]
                        ES_CONTINUOUS | ES_DISPLAY_REQUIRED | ES_SYSTEM_REQUIRED
                    )
                    self._active = True
                    log.info(t("screen_guard.log.enabled_win32"))
                else:
                    log.info(t("screen_guard.log.unsupported_platform", platform="linux"))
            except Exception as e:
                log.warning(t("screen_guard.log.enable_failed", error=e))

    def stop(self) -> None:
        """停止防休眠，恢复正常电源管理"""
        with self._lock:
            if not self._active:
                return
            try:
                if IS_MACOS and self._process:
                    self._process.terminate()
                    try:
                        self._process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        self._process.kill()
                        self._process.wait()
                    self._process = None
                elif IS_WINDOWS:
                    import ctypes
                    ES_CONTINUOUS = 0x80000000
                    ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)  # type: ignore[attr-defined]
            except Exception as e:
                log.warning(t("screen_guard.log.stop_failed", error=e))
            self._active = False
            log.info(t("screen_guard.log.stopped"))

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False
