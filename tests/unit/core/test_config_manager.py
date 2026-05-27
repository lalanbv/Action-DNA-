"""ConfigurationManager 单元测试"""

import json
import os
from pathlib import Path

import pytest

from src.core.config import ConfigLayer, ConfigurationManager, _coerce_env_value, _flatten_dict


# ---------------------------------------------------------------------------
# _flatten_dict
# ---------------------------------------------------------------------------


class TestFlattenDict:
    def test_flat_dict(self) -> None:
        assert _flatten_dict({"a": 1, "b": "hello"}) == {"a": 1, "b": "hello"}

    def test_nested_dict(self) -> None:
        data = {"window": {"title": "game", "width": 1920}, "version": "2.0"}
        result = _flatten_dict(data)
        assert result == {"window.title": "game", "window.width": 1920, "version": "2.0"}

    def test_deeply_nested(self) -> None:
        data = {"a": {"b": {"c": 42}}}
        assert _flatten_dict(data) == {"a.b.c": 42}

    def test_empty_dict(self) -> None:
        assert _flatten_dict({}) == {}


# ---------------------------------------------------------------------------
# _coerce_env_value
# ---------------------------------------------------------------------------


class TestCoerceEnvValue:
    @pytest.mark.parametrize(
        "value, expected",
        [
            ("true", True),
            ("True", True),
            ("TRUE", True),
            ("yes", True),
            ("1", True),
            ("false", False),
            ("False", False),
            ("FALSE", False),
            ("no", False),
            ("0", False),
        ],
    )
    def test_boolean_coercion(self, value: str, expected: bool) -> None:
        assert _coerce_env_value(value) is expected

    def test_integer_coercion(self) -> None:
        assert _coerce_env_value("42") == 42
        assert _coerce_env_value("-5") == -5

    def test_float_coercion(self) -> None:
        assert _coerce_env_value("3.14") == 3.14

    def test_string_passthrough(self) -> None:
        assert _coerce_env_value("hello") == "hello"
        assert _coerce_env_value("not_a_number") == "not_a_number"


# ---------------------------------------------------------------------------
# ConfigurationManager — 层级优先级
# ---------------------------------------------------------------------------


class TestConfigManagerPriority:
    def test_default_layer(self) -> None:
        mgr = ConfigurationManager()
        mgr.set_default("timeout", 30)
        assert mgr.get("timeout") == 30

    def test_config_file_overrides_default(self) -> None:
        mgr = ConfigurationManager()
        mgr.set_default("timeout", 30)
        mgr._layers[ConfigLayer.CONFIG_FILE] = {"timeout": 60}
        assert mgr.get("timeout") == 60

    def test_env_overrides_config_file(self) -> None:
        mgr = ConfigurationManager()
        mgr.set_default("timeout", 30)
        mgr._layers[ConfigLayer.CONFIG_FILE] = {"timeout": 60}
        mgr._layers[ConfigLayer.ENV_VAR] = {"timeout": 90}
        assert mgr.get("timeout") == 90

    def test_runtime_overrides_all(self) -> None:
        mgr = ConfigurationManager()
        mgr.set_default("timeout", 30)
        mgr._layers[ConfigLayer.CONFIG_FILE] = {"timeout": 60}
        mgr._layers[ConfigLayer.ENV_VAR] = {"timeout": 90}
        mgr.save_runtime_override("timeout", 120)
        assert mgr.get("timeout") == 120

    def test_missing_key_returns_default(self) -> None:
        mgr = ConfigurationManager()
        assert mgr.get("nonexistent") is None
        assert mgr.get("nonexistent", "fallback") == "fallback"

    def test_none_value_skipped(self) -> None:
        mgr = ConfigurationManager()
        mgr.set_default("key", None)
        mgr._layers[ConfigLayer.CONFIG_FILE] = {"key": "from_file"}
        assert mgr.get("key") == "from_file"


# ---------------------------------------------------------------------------
# ConfigurationManager — set_defaults
# ---------------------------------------------------------------------------


class TestSetDefaults:
    def test_batch_set(self) -> None:
        mgr = ConfigurationManager()
        mgr.set_defaults({"a": 1, "b": "two", "c": True})
        assert mgr.get("a") == 1
        assert mgr.get("b") == "two"
        assert mgr.get("c") is True


# ---------------------------------------------------------------------------
# ConfigurationManager — load_config_file
# ---------------------------------------------------------------------------


class TestLoadConfigFile:
    def test_load_json_file(self, tmp_path: Path) -> None:
        config_file = tmp_path / "settings.json"
        config_file.write_text(json.dumps({"window": {"title": "test"}, "version": "2.0"}))

        mgr = ConfigurationManager(config_path=config_file)
        mgr.load_config_file()

        assert mgr.get("window.title") == "test"
        assert mgr.get("version") == "2.0"

    def test_missing_file_ignored(self, tmp_path: Path) -> None:
        mgr = ConfigurationManager(config_path=tmp_path / "nonexistent.json")
        mgr.load_config_file()
        assert mgr.get("anything") is None

    def test_invalid_json_ignored(self, tmp_path: Path) -> None:
        config_file = tmp_path / "bad.json"
        config_file.write_text("{invalid json")
        mgr = ConfigurationManager(config_path=config_file)
        mgr.load_config_file()
        assert mgr.get("anything") is None


# ---------------------------------------------------------------------------
# ConfigurationManager — load_env_overrides
# ---------------------------------------------------------------------------


class TestLoadEnvOverrides:
    def test_dna_prefix_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DNA_TIMEOUT", "120")
        monkeypatch.setenv("DNA_LANGUAGE", "en")

        mgr = ConfigurationManager()
        mgr.load_env_overrides()

        assert mgr.get("timeout") == 120
        assert mgr.get("language") == "en"

    def test_non_dna_vars_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OTHER_VAR", "value")
        monkeypatch.delenv("DNA_GUI_BACKEND", raising=False)

        mgr = ConfigurationManager()
        mgr.load_env_overrides()

        assert mgr.layers.get(ConfigLayer.ENV_VAR) is None

    def test_boolean_env_coercion(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DNA_DEBUG", "true")

        mgr = ConfigurationManager()
        mgr.load_env_overrides()

        assert mgr.get("debug") is True


# ---------------------------------------------------------------------------
# ConfigurationManager — runtime overrides
# ---------------------------------------------------------------------------


class TestRuntimeOverrides:
    def test_save_and_read(self) -> None:
        mgr = ConfigurationManager()
        mgr.save_runtime_override("key", "value")
        assert mgr.get("key") == "value"

    def test_remove_override(self) -> None:
        mgr = ConfigurationManager()
        mgr.save_runtime_override("key", "value")
        mgr.remove_runtime_override("key")
        assert mgr.get("key") is None

    def test_remove_nonexistent_is_safe(self) -> None:
        mgr = ConfigurationManager()
        mgr.remove_runtime_override("nonexistent")  # 不抛异常


# ---------------------------------------------------------------------------
# ConfigurationManager — load_all + snapshot
# ---------------------------------------------------------------------------


class TestLoadAllAndSnapshot:
    def test_load_all(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        config_file = tmp_path / "settings.json"
        config_file.write_text(json.dumps({"window": {"title": "from_file"}}))
        monkeypatch.setenv("DNA_LANGUAGE", "en")

        mgr = ConfigurationManager(config_path=config_file)
        mgr.load_all()

        assert mgr.get("window.title") == "from_file"
        assert mgr.get("language") == "en"

    def test_snapshot_merges_layers(self) -> None:
        mgr = ConfigurationManager()
        mgr.set_default("a", 1)
        mgr._layers[ConfigLayer.CONFIG_FILE] = {"b": 2}
        mgr.save_runtime_override("c", 3)

        snap = mgr.snapshot()
        assert snap == {"a": 1, "b": 2, "c": 3}

    def test_snapshot_override_order(self) -> None:
        mgr = ConfigurationManager()
        mgr.set_default("key", "default")
        mgr._layers[ConfigLayer.CONFIG_FILE] = {"key": "file"}
        mgr.save_runtime_override("key", "runtime")

        snap = mgr.snapshot()
        assert snap["key"] == "runtime"

    def test_layers_property_returns_copies(self) -> None:
        mgr = ConfigurationManager()
        mgr.set_default("key", "value")
        layers = mgr.layers
        layers[ConfigLayer.DEFAULT]["key"] = "modified"
        assert mgr.get("key") == "value"  # original unaffected
