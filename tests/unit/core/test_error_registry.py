"""ErrorRegistry 单元测试。"""

import pytest

from src.core.error.error_codes import StandardErrorCode, StandardizedError
from src.core.error.error_registry import ErrorCategory, ErrorRegistry


class TestErrorRegistryCreate:
    """ErrorRegistry.create() 测试。"""

    def test_create_template_not_found(self) -> None:
        err = ErrorRegistry.create(1001, template_path="enemy.png")
        assert isinstance(err, StandardizedError)
        assert err.code == StandardErrorCode.TEMPLATE_NOT_FOUND
        assert "enemy.png" in err.message
        assert err.recovery_suggestion
        assert err.context == {"template_path": "enemy.png"}

    def test_create_pixel_not_found(self) -> None:
        err = ErrorRegistry.create(1005, target_color="(0, 200, 0)")
        assert err.code == StandardErrorCode.PIXEL_NOT_FOUND
        assert "(0, 200, 0)" in err.message

    def test_create_no_context(self) -> None:
        err = ErrorRegistry.create(1003)
        assert err.code == StandardErrorCode.OCR_UNAVAILABLE
        assert err.message
        assert err.context == {}

    def test_create_unknown_code_raises(self) -> None:
        with pytest.raises(KeyError, match="未知错误码"):
            ErrorRegistry.create(9999)

    def test_create_engine_node_timeout(self) -> None:
        err = ErrorRegistry.create(3002, node_id="node_1", timeout="30")
        assert err.code == StandardErrorCode.ENGINE_NODE_TIMEOUT
        assert "node_1" in err.message
        assert "30" in err.message

    def test_create_plugin_load_failed(self) -> None:
        err = ErrorRegistry.create(
            4001, plugin_name="combat", reason="missing descriptor"
        )
        assert err.code == StandardErrorCode.PLUGIN_LOAD_FAILED
        assert "combat" in err.message
        assert "missing descriptor" in err.message

    def test_create_system_screenshot_failed(self) -> None:
        err = ErrorRegistry.create(5001, reason="permission denied")
        assert err.code == StandardErrorCode.SYSTEM_SCREENSHOT_FAILED
        assert "permission denied" in err.message


class TestErrorRegistryConversion:
    """数值码 → 标准码 转换测试。"""

    def test_to_numeric(self) -> None:
        assert ErrorRegistry.to_numeric(StandardErrorCode.TEMPLATE_NOT_FOUND) == 1001
        assert ErrorRegistry.to_numeric(StandardErrorCode.ENGINE_STOPPED) == 3004

    def test_to_numeric_unknown_raises(self) -> None:
        with pytest.raises(KeyError, match="未注册"):
            ErrorRegistry.to_numeric(StandardErrorCode.PERMISSION_DENIED_SCREEN)


class TestErrorCategory:
    """ErrorCategory 常量测试。"""

    def test_category_constants(self) -> None:
        assert ErrorCategory.VISION == 1000
        assert ErrorCategory.INPUT == 2000
        assert ErrorCategory.ENGINE == 3000
        assert ErrorCategory.PLUGIN == 4000
        assert ErrorCategory.SYSTEM == 5000
