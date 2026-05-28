"""缩放常量和断点枚举 — 供 tkinter/Qt 两个后端共享。"""

from enum import Enum


class Breakpoint(Enum):
    COMPACT = "compact"  # 窗口宽度 < 900px
    NORMAL = "normal"  # 900-1200px
    WIDE = "wide"  # > 1200px


# 断点阈值
COMPACT_THRESHOLD = 900
WIDE_THRESHOLD = 1200

# 参考 DPI
BASE_DPI = 96.0
