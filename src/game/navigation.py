"""导航模块 — 自动寻路与地图移动"""

import time

from src.core.input import InputController
from src.core.logger import log
from src.core.vision import ScreenCapture, TemplateMatcher
from src.utils.i18n import t
from src.utils.paths import template_path


class Navigator:
    """自动寻路/移动"""

    def __init__(
        self,
        capture: ScreenCapture,
        matcher: TemplateMatcher,
        input_ctrl: InputController,
    ):
        self.capture = capture
        self.matcher = matcher
        self.input_ctrl = input_ctrl

    def open_map(self) -> bool:
        """打开地图"""
        self.input_ctrl.press_key("m")
        time.sleep(0.8)
        screen = self.capture.grab()
        try:
            result = self.matcher.find(screen, template_path("map_panel.png"), threshold=0.8)
            return result is not None
        except FileNotFoundError:
            return False

    def click_map_marker(self, marker_name: str) -> bool:
        """在地图上点击指定标记点"""
        screen = self.capture.grab()
        try:
            result = self.matcher.find(screen, template_path(marker_name), threshold=0.75)
            if result:
                log.info(t("game.log.map_marker_click", marker_name=marker_name))
                self.input_ctrl.click_rect_center(result, offset_y=-5)
                time.sleep(0.5)
                return True
        except FileNotFoundError:
            log.warning(t("game.log.map_marker_missing", marker_name=marker_name))
        return False

    def auto_run(self, duration: float = 2.0) -> None:
        """自动向前跑动指定时长（按住 W 键）"""
        self.input_ctrl.key_hold("w", duration)
