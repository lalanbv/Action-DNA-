"""平台后端基类 + pyautogui 回退实现。"""

from __future__ import annotations

from collections.abc import Callable

from src.core.input.randomizer import get_pyautogui


class PlatformBackend:
    """平台特定输入原语的基类。

    每个后端封装鼠标/键盘的底层 OS API 调用。
    InputController 委托给单个在初始化时选择的后端，
    消除重复的 if/elif/else 平台三段式判断。
    """

    def move(self, x: int, y: int) -> None:
        raise NotImplementedError

    def move_anim(
        self, x: int, y: int, duration: float,
        get_pos: Callable[[], tuple[int, int]],
        ensure_safe: Callable[[], None],
    ) -> None:
        raise NotImplementedError

    def mouse_down(self, x: int, y: int, button: str) -> int | None:
        """Press mouse button. Returns click count (Quartz) or None."""
        raise NotImplementedError

    def mouse_up(
        self, x: int, y: int, button: str, click_num: int | None,
    ) -> None:
        raise NotImplementedError

    def key_down(self, key: str) -> None:
        raise NotImplementedError

    def key_up(self, key: str) -> None:
        raise NotImplementedError

    def scroll(self, clicks: int) -> None:
        raise NotImplementedError

    def scroll_horizontal(self, clicks: int) -> None:
        raise NotImplementedError

    def get_mouse_pos(self) -> tuple[int, int]:
        raise NotImplementedError

    def micro(self, x: int, y: int) -> None:
        """Pre-click ±1px jitter."""
        raise NotImplementedError

    def hold_drift(
        self, px: int, py: int, button: str = "left", *,
        clamp: tuple[int, int, int, int] | None = None,
    ) -> tuple[int, int]:
        """Drift while button held. Returns final (x, y)."""
        raise NotImplementedError

    def reset_click_state(self) -> None:
        """Reset OS-level click tracking state."""


class PyAutoGUIBackend(PlatformBackend):
    """Fallback pyautogui backend."""

    def move(self, x: int, y: int) -> None:
        get_pyautogui().moveTo(x, y, duration=0)

    def move_anim(
        self, x: int, y: int, duration: float,
        get_pos: Callable[[], tuple[int, int]],
        ensure_safe: Callable[[], None],
    ) -> None:
        ensure_safe()
        get_pyautogui().moveTo(x, y, duration=duration)

    def mouse_down(self, x: int, y: int, button: str) -> int | None:
        pya = get_pyautogui()
        pya.moveTo(x, y, duration=0)
        pya.mouseDown(button=button)
        return None

    def mouse_up(
        self, x: int, y: int, button: str, click_num: int | None,
    ) -> None:
        get_pyautogui().mouseUp(button=button)

    def key_down(self, key: str) -> None:
        get_pyautogui().keyDown(key)

    def key_up(self, key: str) -> None:
        get_pyautogui().keyUp(key)

    def scroll(self, clicks: int) -> None:
        get_pyautogui().scroll(clicks)

    def scroll_horizontal(self, clicks: int) -> None:
        get_pyautogui().hscroll(clicks)

    def get_mouse_pos(self) -> tuple[int, int]:
        return get_pyautogui().position()

    def micro(self, x: int, y: int) -> None:
        pass  # pyautogui has no micro-jitter equivalent

    def hold_drift(
        self, px: int, py: int, button: str = "left", *,
        clamp: tuple[int, int, int, int] | None = None,
    ) -> tuple[int, int]:
        return px, py  # pyautogui has no drift equivalent
