"""项目路径工具 — 统一处理开发模式和 PyInstaller 打包模式的路径解析"""

import os
import sys

from src.utils.platform import IS_FROZEN, IS_MACOS

_project_root: str | None = None


def get_project_root() -> str:
    """获取项目根目录，兼容开发模式和 PyInstaller 打包模式（带缓存）"""
    global _project_root
    if _project_root is not None:
        return _project_root

    if IS_FROZEN:
        exe_dir = os.path.dirname(sys.executable)
        if IS_MACOS:
            # macOS .app bundle 结构:
            #   dist/Action-DNA/Action-DNA.app/Contents/MacOS/Action-DNA
            # 需要上溯到 dist/Action-DNA/（profiles/assets/config 所在位置）
            parent = os.path.dirname(exe_dir)
            if os.path.basename(parent) == "Contents":
                _project_root = os.path.dirname(os.path.dirname(parent))
                return _project_root
        _project_root = exe_dir
        return _project_root

    # src/utils/ → ../../  = project root
    _project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    return _project_root


def _read_only_root() -> str:
    """只读资源根目录：打包模式指向 _MEIPASS（PyInstaller 解压的临时 bundle），
    开发模式回退到项目根。

    config/settings.json、assets/templates/*.png 通过 --add-data 打进
    _MEIPASS（只读、每次启动重新解压），必须从此处读取。可写数据
    （profiles/、assets/logs/）仍用 get_project_root()，避免写入只读临时目录。
    """
    if IS_FROZEN:
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return meipass
    return get_project_root()


def get_assets_dir() -> str:
    """获取模板图片目录（只读资源，打包模式从 _MEIPASS 读取）"""
    return os.path.join(_read_only_root(), "assets", "templates")


def get_logs_dir() -> str:
    """获取日志目录"""
    return os.path.join(get_project_root(), "assets", "logs")


def get_config_dir() -> str:
    """获取配置目录"""
    return os.path.join(get_project_root(), "config")


def get_profiles_dir() -> str:
    """获取配置文件目录"""
    return os.path.join(get_project_root(), "profiles")


def template_path(filename: str) -> str:
    """将模板文件名解析为完整路径"""
    return os.path.join(get_assets_dir(), filename)
