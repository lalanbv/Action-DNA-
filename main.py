"""Action<DNA> — 主入口（启动控制面板）"""

import os
import sys
import traceback

from src.utils.platform import IS_FROZEN, IS_MACOS, IS_WINDOWS


def _show_fatal_error(title: str, message: str) -> None:
    """打包模式下显示致命错误对话框，否则打印到 stderr。"""
    if IS_FROZEN and IS_WINDOWS:
        import ctypes
        _windll = getattr(ctypes, "windll", None)
        if _windll is not None:
            _windll.user32.MessageBoxW(0, message, title, 0x10)
    else:
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"[{title}]", file=sys.stderr)
        print(message, file=sys.stderr)
        print(f"{'='*60}\n", file=sys.stderr)


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
    """
    _stderr_fd = os.dup(2)
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
        if use_qt_backend():
            try:
                from PySide6.QtWidgets import QApplication
                if QApplication.instance() is None:
                    QApplication(sys.argv)
                from src.panel.qt_backend.app import QtPanelApp
                app = QtPanelApp()
            except ImportError:
                print(
                    "PySide6 未安装。Qt 后端需要 PySide6，"
                    "请运行: pip install PySide6>=6.5.0\n"
                    "回退到 tkinter 后端...",
                    file=sys.stderr,
                )
        if app is None:
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
