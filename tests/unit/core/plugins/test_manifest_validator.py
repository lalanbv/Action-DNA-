"""manifest_validator 测试 — 插件清单验证。"""

import pytest

from src.core.plugins.manifest_validator import (
    EngineVersion,
    validate_manifest,
)


class TestEngineVersion:
    def test_parse_valid(self) -> None:
        v = EngineVersion.parse("2.0.0")
        assert v.major == 2
        assert v.minor == 0
        assert v.patch == 0

    def test_parse_with_whitespace(self) -> None:
        v = EngineVersion.parse(" 1.2.3 ")
        assert v.major == 1

    def test_parse_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="无效版本号"):
            EngineVersion.parse("abc")

    def test_comparison(self) -> None:
        v1 = EngineVersion(1, 0, 0)
        v2 = EngineVersion(2, 0, 0)
        assert v1 <= v2
        assert v2 >= v1
        assert not (v2 <= v1)

    def test_str(self) -> None:
        assert str(EngineVersion(1, 2, 3)) == "1.2.3"


class TestValidateManifest:
    def test_valid_manifest(self) -> None:
        manifest = {
            "id": "test-plugin",
            "version": "1.0.0",
            "permissions": ["screen_capture"],
        }
        errors = validate_manifest(manifest, "2.0.0")
        assert errors == []

    def test_missing_required_fields(self) -> None:
        manifest = {"id": "test-plugin"}
        errors = validate_manifest(manifest, "2.0.0")
        assert len(errors) > 0
        assert "缺少必填字段" in errors[0]

    def test_invalid_plugin_version(self) -> None:
        manifest = {
            "id": "test-plugin",
            "version": "not-a-version",
            "permissions": [],
        }
        errors = validate_manifest(manifest, "2.0.0")
        assert any("无效版本号" in e for e in errors)

    def test_engine_version_too_old(self) -> None:
        manifest = {
            "id": "test-plugin",
            "version": "1.0.0",
            "permissions": [],
            "engine_version_min": "3.0.0",
        }
        errors = validate_manifest(manifest, "2.0.0")
        assert any("不兼容" in e for e in errors)

    def test_engine_version_too_new(self) -> None:
        manifest = {
            "id": "test-plugin",
            "version": "1.0.0",
            "permissions": [],
            "engine_version_max": "1.0.0",
        }
        errors = validate_manifest(manifest, "2.0.0")
        assert any("不兼容" in e for e in errors)

    def test_engine_version_in_range(self) -> None:
        manifest = {
            "id": "test-plugin",
            "version": "1.0.0",
            "permissions": [],
            "engine_version_min": "1.0.0",
            "engine_version_max": "3.0.0",
        }
        errors = validate_manifest(manifest, "2.0.0")
        assert errors == []

    def test_permissions_not_list(self) -> None:
        manifest = {
            "id": "test-plugin",
            "version": "1.0.0",
            "permissions": "screen_capture",
        }
        errors = validate_manifest(manifest, "2.0.0")
        assert any("permissions" in e for e in errors)

    def test_no_engine_version_field_ok(self) -> None:
        """没有 engine_version 字段时不报错（向后兼容）。"""
        manifest = {
            "id": "test-plugin",
            "version": "1.0.0",
            "permissions": [],
        }
        errors = validate_manifest(manifest, "99.0.0")
        assert errors == []
