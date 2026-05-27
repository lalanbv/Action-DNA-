"""properties 模块测试 — 属性验证系统。"""

import pytest

from src.core.properties import PropertyDef, ValidatedConfig


class _MockConfig(ValidatedConfig):
    _properties = {
        "interval": PropertyDef(
            name="interval", prop_type=float, default=1.0,
            min_value=0.1, max_value=60.0,
        ),
        "retries": PropertyDef(
            name="retries", prop_type=int, default=3,
            min_value=0, max_value=100,
        ),
        "name": PropertyDef(
            name="name", prop_type=str, default="unnamed",
        ),
        "enabled": PropertyDef(
            name="enabled", prop_type=bool, default=True,
        ),
    }


class TestPropertyDef:
    def test_validate_valid_int(self) -> None:
        prop = PropertyDef("count", int, 0, min_value=0, max_value=100)
        assert prop.validate(5) == 5

    def test_validate_valid_float(self) -> None:
        prop = PropertyDef("interval", float, 1.0, min_value=0.1, max_value=60.0)
        assert prop.validate(5.0) == 5.0

    def test_validate_coerce_int_to_float(self) -> None:
        prop = PropertyDef("interval", float, 1.0)
        assert prop.validate(5) == 5.0

    def test_validate_coerce_str_to_int(self) -> None:
        prop = PropertyDef("count", int, 0)
        assert prop.validate("42") == 42

    def test_validate_below_min_raises(self) -> None:
        prop = PropertyDef("count", int, 0, min_value=1)
        with pytest.raises(ValueError, match="必须 >="):
            prop.validate(0)

    def test_validate_above_max_raises(self) -> None:
        prop = PropertyDef("count", int, 0, max_value=10)
        with pytest.raises(ValueError, match="必须 <="):
            prop.validate(11)

    def test_validate_invalid_type_raises(self) -> None:
        prop = PropertyDef("count", int, 0)
        with pytest.raises(ValueError, match="无法转换"):
            prop.validate("not_a_number")


class TestValidatedConfig:
    def test_default_values(self) -> None:
        cfg = _MockConfig()
        assert cfg.interval == 1.0
        assert cfg.retries == 3
        assert cfg.name == "unnamed"
        assert cfg.enabled is True

    def test_valid_values(self) -> None:
        cfg = _MockConfig(interval=5.0, retries=10, name="test", enabled=False)
        assert cfg.interval == 5.0
        assert cfg.retries == 10
        assert cfg.name == "test"
        assert cfg.enabled is False

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            _MockConfig(interval=-1.0)

    def test_from_dict(self) -> None:
        cfg = _MockConfig.from_dict({"interval": 3.0, "retries": 5})
        assert cfg.interval == 3.0
        assert cfg.retries == 5
        assert cfg.name == "unnamed"

    def test_from_dict_missing_uses_default(self) -> None:
        cfg = _MockConfig.from_dict({})
        assert cfg.interval == 1.0
        assert cfg.retries == 3

    def test_to_dict(self) -> None:
        cfg = _MockConfig(interval=2.0)
        d = cfg.to_dict()
        assert d["interval"] == 2.0
        assert d["retries"] == 3

    def test_repr(self) -> None:
        cfg = _MockConfig()
        r = repr(cfg)
        assert "interval=1.0" in r
        assert "_MockConfig" in r

    def test_on_update_callback(self) -> None:
        changes: list[tuple[str, Any, Any]] = []

        class _CallbackConfig(ValidatedConfig):
            _properties = {
                "value": PropertyDef(
                    name="value", prop_type=int, default=0,
                    on_update=lambda n, old, new: changes.append((n, old, new)),
                ),
            }

        _CallbackConfig(value=42)
        assert changes == [("value", 0, 42)]
