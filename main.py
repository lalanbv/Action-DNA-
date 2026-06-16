"""Action<DNA> — 主入口（启动控制面板）"""

import os
import sys
import traceback

from src.utils.platform import IS_FROZEN, IS_MACOS, IS_WINDOWS

# macOS 警告抑制时保存的原始 stderr fd 副本（指向真实终端）。
# _suppress_macos_warnings() 会把 C 层 fd 2 重定向到 /dev/null 以屏蔽
# 无害的 TSM/IMK 警告，但这也吞掉了 Qt/底层 C 库的致命错误输出。
# 这里保留原始副本，供 _show_fatal_error() 临时恢复，确保致命错误可见。
_original_stderr_fd: int | None = None


def _show_fatal_error(title: str, message: str) -> None:
    """打包模式下显示致命错误对话框，否则打印到 stderr。

    macOS 下若已启用警告抑制（C 层 fd 2 → /dev/null），临时恢复 fd 2
    指向真实终端，确保致命错误的 traceback 一定能输出到控制台。
    """
    global _original_stderr_fd
    if IS_FROZEN and IS_WINDOWS:
        import ctypes
        _windll = getattr(ctypes, "windll", None)
        if _windll is not None:
            _windll.user32.MessageBoxW(0, message, title, 0x10)
        return

    # macOS: 临时把 C 层 fd 2 恢复到真实终端（若曾被抑制）
    restored = False
    if IS_MACOS and _original_stderr_fd is not None:
        try:
            os.dup2(_original_stderr_fd, 2)
            restored = True
        except OSError:
            pass

    print(f"\n{'='*60}", file=sys.stderr, flush=True)
    print(f"[{title}]", file=sys.stderr, flush=True)
    print(message, file=sys.stderr, flush=True)
    print(f"{'='*60}\n", file=sys.stderr, flush=True)


def _setup():
    """跨平台初始化：工作目录 + macOS 警告抑制 + Windows DPI 感知"""
    # 打包模式：固定工作目录到项目根目录，确保 profiles/assets 路径正确
    # macOS .app bundle 中 exe 位于 XXX.app/Contents/MacOS/，需要上溯
    if IS_FROZEN:
        from src.utils.paths import get_project_root
        os.chdir(get_project_root())

    # macOS: 抑制输入框架产生的无害控制台警告 (TSM/IMK)
    if IS_MACOS:
        _suppress_macos_warnings()

    # Windows: 启用 DPI 感知，避免高 DPI 缩放导致坐标系错乱和界面模糊
    if IS_WINDOWS:
        _enable_dpi_awareness()


def _suppress_macos_warnings() -> None:
    """macOS: 抑制输入框架产生的无害控制台警告 (TSM/IMK)

    pyautogui 使用 macOS 输入 API 时，系统框架会向 C 层 stderr 输出
    TSM CapsLock / IMK mach port 等警告。这些警告不影响功能，
    但会污染控制台输出。通过将 C 层 fd 2 重定向到 /dev/null 抑制，
    同时将 Python sys.stderr 重指向原始 fd，保留 Python 错误输出。

    原始 fd 2 的副本同时存入模块变量 _original_stderr_fd，
    供 _show_fatal_error() 在输出致命错误时临时恢复，避免 Qt/底层
    C 库的致命错误被一并吞掉。
    """
    global _original_stderr_fd
    _stderr_fd = os.dup(2)
    _original_stderr_fd = _stderr_fd
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, 2)
    os.close(devnull)
    sys.stderr = os.fdopen(_stderr_fd, 'w')


def _enable_dpi_awareness() -> None:
    """Windows DPI 感知设置，兼容不同 Windows 版本和 Python 3.11+"""
    import ctypes

    windll = getattr(ctypes, "windll", None)
    if windll is None:
        return

    # 优先使用 Per-Monitor DPI Awareness V2（Windows 10 1703+）
    for func, args in [
        (windll.shcore.SetProcessDpiAwareness, (2,)),  # Per-Monitor V2
        (windll.shcore.SetProcessDpiAwareness, (1,)),  # System DPI
        (windll.user32.SetProcessDPIAware, ()),        # Legacy
    ]:
        try:
            func(*args)
            return
        except (AttributeError, OSError):
            continue


def _qt_cocoa_active() -> bool:
    """检测本进程是否已存在「非 offscreen」的 QApplication（macOS 原生 GUI）。

    用于 main() 的 Qt→Tk 回退决策：macOS 上用 cocoa 平台插件创建的
    QApplication 会初始化 NSApplication，此后创建 tk.Tk() 会触发 Tcl/Tk9
    颜色初始化的 SIGABRT（无法被 try/except 捕获；crash report:
    Tkapp_New→GetRGBA→doesNotRecognizeSelector）。offscreen/minimal 不创建
    冲突的 NSApplication，可安全与 Tk 共存。

    与 tests/conftest.py 的 ``_skip_tk_root_when_qt_cocoa_active`` 同源逻辑。
    """
    if not IS_MACOS:
        return False
    try:
        from PySide6.QtWidgets import QApplication
    except Exception:
        return False
    app = QApplication.instance()
    return app is not None and app.platformName() != "offscreen"


def main():
    try:
        _setup()

        # Preload heavy C extensions (cv2, mss, numpy, pyautogui, pynput)
        # in background while UI starts — modules land in sys.modules so
        # later imports on the main thread are instant.
        from src.utils.preload import start_preload
        start_preload()  # fire-and-forget; ensure_preloaded() blocks when needed

        from src.panel.backend_selector import use_qt_backend
        app = None
        qt_init_error: Exception | None = None
        if use_qt_backend():
            try:
                from PySide6.QtWidgets import QApplication
                if QApplication.instance() is None:
                    QApplication(sys.argv)
                from src.panel.qt_backend.app import QtPanelApp
                app = QtPanelApp()
            except Exception as exc:
                # 记录 Qt 失败原因，供下方回退决策使用
                qt_init_error = exc
                # 同时打印到 stderr，避免仅靠 logging（可能未配置 handler）
                # 导致用户看不到回退原因。
                import logging
                logging.getLogger(__name__).warning(
                    "Qt 后端初始化失败: %s", exc, exc_info=True
                )
                print(
                    f"[警告] Qt 后端初始化失败: {exc}",
                    file=sys.stderr, flush=True,
                )
        if app is None:
            # macOS 防护：若 Qt 已用 cocoa 创建 QApplication(NSApplication)，
            # 再创建 tk.Tk() 会触发 Tcl/Tk9 颜色初始化的 SIGABRT（无法被
            # try/except 捕获）。此时回退到 tkinter 不安全，改为报致命错误
            # 退出，避免静默硬崩。Linux/Windows 不受影响（无此冲突）。
            if _qt_cocoa_active():
                _show_fatal_error(
                    "Action<DNA> Qt 后端初始化失败",
                    f"Qt 后端初始化失败，且 macOS 下无法安全回退到 tkinter"
                    f"（QApplication(cocoa) 已存在，回退会触发 Tcl/Tk9 颜色"
                    f"初始化的 SIGABRT 硬崩溃）。\n\n原因: {qt_init_error}",
                )
                sys.exit(1)
            from src.panel.app import PanelApp
            app = PanelApp()

        app.run()
    except Exception:
        tb = traceback.format_exc()
        _show_fatal_error("Action<DNA> 启动失败", tb)
        if IS_FROZEN:
            input("按回车键退出...")
            sys.exit(1)
        raise


if __name__ == "__main__":
    main()
