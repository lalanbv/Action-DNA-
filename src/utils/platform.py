"""platform.py — 集中式平台检测常量

所有 frozen/platform 检测统一由此模块提供，避免散布在 30+ 文件中。
"""

from __future__ import annotations

import platform
import struct
import sys

ARCH_BITS: int = struct.calcsize("P") * 8
"""当前 Python 解释器位数（32 或 64）。"""

IS_FROZEN: bool = getattr(sys, "frozen", False)
"""是否运行在 PyInstaller 打包环境中。"""

IS_MACOS: bool = sys.platform == "darwin"
IS_WINDOWS: bool = sys.platform == "win32"
IS_LINUX: bool = sys.platform == "linux"
IS_MACOS_ARM: bool = IS_MACOS and platform.machine() == "arm64"


def validate_64bit() -> int:
    """校验 64-bit Python，不满足时 sys.exit。返回 ARCH_BITS 供调用者使用。"""
    if ARCH_BITS != 64:
        sys.exit(f"错误: 需要 64-bit Python，当前 {ARCH_BITS}-bit")
    return ARCH_BITS
