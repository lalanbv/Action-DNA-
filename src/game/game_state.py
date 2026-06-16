"""游戏状态识别模块"""

from enum import Enum, auto

from src.core.logger import log
from src.core.vision import ScreenCapture, TemplateMatcher
from src.utils.i18n import t
from src.utils.paths import template_path


class GameState(Enum):
    """游戏界面状态"""
    UNKNOWN = auto()
    LOADING = auto()       # 加载画面
    MAIN_MENU = auto()     # 主界面
    COMBAT = auto()        # 战斗中
    DIALOG = auto()        # 对话中
    MENU = auto()          # 菜单/背包等
    QUEST = auto()         # 任务界面
    DEATH = auto()         # 角色死亡
    DISCONNECTED = auto()  # 断线


# 状态对应的模板图片文件名
STATE_TEMPLATES: dict[GameState, str] = {
    GameState.LOADING: "state_loading.png",
    GameState.MAIN_MENU: "state_main_menu.png",
    GameState.COMBAT: "state_combat.png",
    GameState.DIALOG: "state_dialog.png",
    GameState.DEATH: "state_death.png",
    GameState.DISCONNECTED: "state_disconnected.png",
}


class GameStateDetector:
    """游戏状态检测器"""

    def __init__(
        self,
        capture: ScreenCapture,
        matcher: TemplateMatcher,
    ):
        self.capture = capture
        self.matcher = matcher

    def detect(self) -> GameState:
        """截图并判断当前游戏状态"""
        screen = self.capture.grab()

        for state, tpl_name in STATE_TEMPLATES.items():
            try:
                result = self.matcher.find(screen, template_path(tpl_name), threshold=0.85)
                if result is not None:
                    log.debug(t("game.log.state_detected", state_name=state.name))
                    return state
            except FileNotFoundError:
                continue

        return GameState.UNKNOWN

    def wait_for_state(
        self,
        target: GameState,
        timeout: float = 30.0,
        interval: float = 1.0,
    ) -> bool:
        """等待游戏进入指定状态，超时返回 False"""
        import time
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            if self.detect() == target:
                return True
            time.sleep(interval)
        log.warning(t("game.log.state_wait_timeout", state_name=target.name, timeout=timeout))
        return False
