"""系统主题检测 — 跨平台深浅色偏好"""

import logging
import subprocess

from src.utils.platform import IS_MACOS, IS_WINDOWS

logger = logging.getLogger(__name__)


def detect_system_theme() -> str:
    """检测操作系统当前深浅色偏好，返回 'dark' 或 'light'"""
    try:
        if IS_MACOS:
            result = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True, text=True, timeout=3,
            )
            return "dark" if result.returncode == 0 and "Dark" in result.stdout else "light"
        elif IS_WINDOWS:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return "light" if value else "dark"
        else:
            import os
            gtk_theme = os.environ.get("GTK_THEME", "")
            if "dark" in gtk_theme.lower():
                return "dark"
            try:
                result = subprocess.run(
                    ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                    capture_output=True, text=True, timeout=3,
                )
                if "dark" in result.stdout.lower():
                    return "dark"
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass
            return "light"
    except Exception:
        logger.debug("System theme detection failed, falling back to light")
        return "light"
