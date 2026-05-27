"""DesktopContextService 单元测试"""

from typing import Any
from unittest.mock import MagicMock

import pytest

from src.core.debug.debugger import DesktopContext, DesktopContextService


# ---------------------------------------------------------------------------
# 辅助 mock 工厂
# ---------------------------------------------------------------------------


def _mock_pyautogui(
    pos: tuple[int, int] = (100, 200),
    size: tuple[int, int] = (1920, 1080),
) -> Any:
    m = MagicMock()
    m.position.return_value = pos
    m.size.return_value = size
    return m


def _mock_region_picker(region: tuple[int, int, int, int] | None = (10, 20, 800, 600)) -> Any:
    m = MagicMock()
    m.get_active_region.return_value = region
    return m


def _mock_frame_provider(cache_age: float = 0.15) -> Any:
    m = MagicMock()
    m.cache_age = cache_age
    return m


def _mock_executor(state: str = "running") -> Any:
    m = MagicMock()
    m.state = state
    return m


# ---------------------------------------------------------------------------
# DesktopContext dataclass
# ---------------------------------------------------------------------------


class TestDesktopContext:
    def test_frozen(self) -> None:
        ctx = DesktopContext(
            cursor_position=(0, 0),
            screen_size=(1920, 1080),
            active_region=None,
            buffer_pool_age_ms=0.0,
            engine_state="idle",
            timestamp=0.0,
        )
        with pytest.raises(AttributeError):
            ctx.engine_state = "running"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# DesktopContextService — 基础收集
# ---------------------------------------------------------------------------


class TestDesktopContextServiceBasic:
    def test_no_dependencies_returns_defaults(self) -> None:
        svc = DesktopContextService()
        ctx = svc.get_context()
        assert ctx.cursor_position == (0, 0)
        assert ctx.screen_size == (0, 0)
        assert ctx.active_region is None
        assert ctx.buffer_pool_age_ms == 0.0
        assert ctx.engine_state == "idle"
        assert ctx.timestamp > 0

    def test_pyautogui_injection(self) -> None:
        pya = _mock_pyautogui(pos=(500, 300), size=(2560, 1440))
        svc = DesktopContextService(pyautogui_module=pya)
        ctx = svc.get_context()
        assert ctx.cursor_position == (500, 300)
        assert ctx.screen_size == (2560, 1440)

    def test_region_picker_injection(self) -> None:
        svc = DesktopContextService()
        svc.set_region_picker(_mock_region_picker((50, 60, 400, 300)))
        ctx = svc.get_context()
        assert ctx.active_region == (50, 60, 400, 300)

    def test_frame_provider_injection(self) -> None:
        svc = DesktopContextService()
        svc.set_frame_provider(_mock_frame_provider(0.25))
        ctx = svc.get_context()
        assert ctx.buffer_pool_age_ms == pytest.approx(250.0)

    def test_executor_injection(self) -> None:
        svc = DesktopContextService()
        svc.set_executor(_mock_executor("paused"))
        ctx = svc.get_context()
        assert ctx.engine_state == "paused"

    def test_all_dependencies(self) -> None:
        svc = DesktopContextService(pyautogui_module=_mock_pyautogui())
        svc.set_region_picker(_mock_region_picker())
        svc.set_frame_provider(_mock_frame_provider(0.5))
        svc.set_executor(_mock_executor("running"))

        ctx = svc.get_context()
        assert ctx.cursor_position == (100, 200)
        assert ctx.screen_size == (1920, 1080)
        assert ctx.active_region == (10, 20, 800, 600)
        assert ctx.buffer_pool_age_ms == pytest.approx(500.0)
        assert ctx.engine_state == "running"


# ---------------------------------------------------------------------------
# DesktopContextService — 优雅降级
# ---------------------------------------------------------------------------


class TestDesktopContextServiceDegradation:
    def test_pyautogui_exception_returns_defaults(self) -> None:
        m = MagicMock()
        m.position.side_effect = RuntimeError("no screen")
        m.size.side_effect = RuntimeError("no screen")

        svc = DesktopContextService(pyautogui_module=m)
        ctx = svc.get_context()
        assert ctx.cursor_position == (0, 0)
        assert ctx.screen_size == (0, 0)

    def test_region_picker_exception_returns_none(self) -> None:
        m = MagicMock()
        m.get_active_region.side_effect = RuntimeError("no picker")
        svc = DesktopContextService()
        svc.set_region_picker(m)
        ctx = svc.get_context()
        assert ctx.active_region is None

    def test_frame_provider_exception_returns_zero(self) -> None:
        m = MagicMock()
        type(m).cache_age = property(lambda self: (_ for _ in ()).throw(RuntimeError("no frame")))  # type: ignore[arg-type]
        svc = DesktopContextService()
        svc.set_frame_provider(m)
        ctx = svc.get_context()
        assert ctx.buffer_pool_age_ms == 0.0

    def test_executor_exception_returns_idle(self) -> None:
        m = MagicMock()
        type(m).state = property(lambda self: (_ for _ in ()).throw(RuntimeError("no executor")))  # type: ignore[arg-type]
        svc = DesktopContextService()
        svc.set_executor(m)
        ctx = svc.get_context()
        assert ctx.engine_state == "idle"

    def test_setter_none_clears_dependency(self) -> None:
        svc = DesktopContextService(pyautogui_module=_mock_pyautogui())
        svc.set_region_picker(_mock_region_picker())
        svc.set_frame_provider(_mock_frame_provider())
        svc.set_executor(_mock_executor())

        svc.set_region_picker(None)
        svc.set_frame_provider(None)
        svc.set_executor(None)

        ctx = svc.get_context()
        assert ctx.active_region is None
        assert ctx.buffer_pool_age_ms == 0.0
        assert ctx.engine_state == "idle"


# ---------------------------------------------------------------------------
# DesktopContextService — 格式化
# ---------------------------------------------------------------------------


class TestDesktopContextServiceFormatting:
    def test_format_for_log(self) -> None:
        svc = DesktopContextService(pyautogui_module=_mock_pyautogui())
        svc.set_executor(_mock_executor("running"))

        log_line = svc.format_for_log()
        assert log_line.startswith("DESKTOP_CONTEXT |")
        assert "cursor=(100, 200)" in log_line
        assert "screen=(1920, 1080)" in log_line
        assert "engine=running" in log_line

    def test_format_for_debug(self) -> None:
        svc = DesktopContextService(pyautogui_module=_mock_pyautogui())
        svc.set_region_picker(_mock_region_picker((10, 20, 800, 600)))

        debug_dict = svc.format_for_debug()
        assert debug_dict["cursor_position"] == (100, 200)
        assert debug_dict["screen_size"] == (1920, 1080)
        assert debug_dict["active_region"] == (10, 20, 800, 600)
        assert "timestamp" in debug_dict
        assert isinstance(debug_dict["buffer_pool_age_ms"], float)
