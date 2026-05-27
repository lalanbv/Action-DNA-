"""自动任务模块 — 自动接取/完成任务、自动对话"""

import time

from src.core.config import TaskConfig
from src.core.input import InputController
from src.core.logger import log
from src.utils.i18n import t
from src.core.vision import ScreenCapture, TemplateMatcher
from src.game.game_state import GameState, GameStateDetector
from src.utils.paths import template_path


class TaskController:
    """自动任务控制器"""

    def __init__(
        self,
        config: TaskConfig,
        capture: ScreenCapture,
        matcher: TemplateMatcher,
        input_ctrl: InputController,
        state_detector: GameStateDetector,
    ):
        self.config = config
        self.capture = capture
        self.matcher = matcher
        self.input_ctrl = input_ctrl
        self.state_detector = state_detector

    def handle_dialog(self) -> bool:
        """处理对话界面，点击继续。返回是否正在对话中"""
        state = self.state_detector.detect()
        if state != GameState.DIALOG:
            return False

        log.debug(t("game.log.dialog_click"))
        screen = self.capture.grab()

        # 查找对话选项/继续按钮
        try:
            btn = self.matcher.find(screen, template_path("btn_dialog_continue.png"), threshold=0.8)
            if btn:
                self.input_ctrl.click_rect_center(btn)
                time.sleep(self.config.dialog_delay)
                return True
        except FileNotFoundError:
            pass

        # 回退方案：直接按空格/点击固定区域
        self.input_ctrl.press_key("space")
        time.sleep(self.config.dialog_delay)
        return True

    def try_accept_quest(self) -> bool:
        """尝试接取任务"""
        if not self.config.auto_accept_quest:
            return False

        screen = self.capture.grab()
        try:
            btn = self.matcher.find(screen, template_path("btn_accept_quest.png"), threshold=0.8)
            if btn:
                log.info(t("game.log.quest_accept"))
                self.input_ctrl.click_rect_center(btn)
                time.sleep(1.0)
                return True
        except FileNotFoundError:
            pass
        return False

    def try_complete_quest(self) -> bool:
        """尝试完成任务"""
        if not self.config.auto_complete_quest:
            return False

        screen = self.capture.grab()
        try:
            btn = self.matcher.find(screen, template_path("btn_complete_quest.png"), threshold=0.8)
            if btn:
                log.info(t("game.log.quest_complete"))
                self.input_ctrl.click_rect_center(btn)
                time.sleep(1.0)
                return True
        except FileNotFoundError:
            pass
        return False
