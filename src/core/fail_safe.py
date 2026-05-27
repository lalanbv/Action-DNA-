"""FAIL-SAFE 机制 — 检测鼠标在屏幕角落触发紧急停止。

借鉴 PyAutoGUI 的 FAIL-SAFE 设计：鼠标移到屏幕四角时触发停止。
检测区域仅 5×5px（4 角共 100px²），误触发概率极低。
"""


class FailSafeTriggered(Exception):
    """鼠标在角落，紧急停止。"""


class FailSafeMonitor:
    """检测鼠标是否在屏幕角落，触发紧急停止。"""

    CORNER_SIZE: int = 5

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled

    def check(
        self, mouse_x: int, mouse_y: int, screen_w: int, screen_h: int
    ) -> None:
        if not self.enabled:
            return
        cs = self.CORNER_SIZE
        in_corner = (
            (mouse_x < cs and mouse_y < cs)
            or (mouse_x > screen_w - cs and mouse_y < cs)
            or (mouse_x < cs and mouse_y > screen_h - cs)
            or (mouse_x > screen_w - cs and mouse_y > screen_h - cs)
        )
        if in_corner:
            raise FailSafeTriggered(
                f"鼠标在角落 ({mouse_x}, {mouse_y})，紧急停止"
            )
