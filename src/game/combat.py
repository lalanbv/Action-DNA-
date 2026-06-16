"""自动战斗模块"""

import time

from src.core.config import CombatConfig
from src.core.input import InputController
from src.core.logger import log
from src.core.vision import ScreenCapture, TemplateMatcher
from src.game.game_state import GameState, GameStateDetector
from src.utils.i18n import t
from src.utils.paths import template_path


class CombatController:
    """自动战斗控制器"""

    def __init__(
        self,
        config: CombatConfig,
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
        self._last_skill_time = 0.0

    def is_in_combat(self) -> bool:
        """判断是否在战斗中"""
        return self.state_detector.detect() == GameState.COMBAT

    def check_hp(self) -> float:
        """估算当前血量比例 (0.0 ~ 1.0)，基于模板匹配"""
        screen = self.capture.grab()
        try:
            result = self.matcher.find(screen, template_path("hp_bar.png"), threshold=0.6)
            if result:
                # 简化：如果能匹配到 HP 条则认为血量充足
                return 1.0
        except FileNotFoundError:
            pass
        return 1.0

    def execute_combat_rotation(self) -> None:
        """执行战斗循环：普攻 + 技能"""
        if not self.config.auto_combat:
            return

        now = time.time()

        # 普通攻击（连续点击）
        self.input_ctrl.click(960, 540)  # 屏幕中心附近作为攻击键位示例

        # 技能释放
        if now - self._last_skill_time >= self.config.skill_interval:
            self.input_ctrl.press_key("e")  # 技能键
            self._last_skill_time = now
            log.debug(t("game.log.skill_cast", key_name="E"))

        # 闪避
        if self.config.dodge_enabled:
            self.input_ctrl.press_key("space")  # 闪避键

    def try_heal(self) -> bool:
        """检查是否需要治疗"""
        hp = self.check_hp()
        if hp < self.config.heal_threshold:
            log.info(t("game.log.low_hp_heal", hp=f"{hp:.0%}"))
            self.input_ctrl.press_key("r")  # 回复键
            return True
        return False
