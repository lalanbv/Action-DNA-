"""config_schema 模块测试 — Schema 版本管理。"""

from src.core.config_schema import (
    SCHEMA_VERSION,
    FieldDescriptor,
    apply_field_renames,
    fill_defaults,
    migrate_config,
    register_migration,
)


class TestFieldDescriptor:
    def test_basic_creation(self) -> None:
        fd = FieldDescriptor("interval", "float", 1.0)
        assert fd.name == "interval"
        assert fd.default == 1.0

    def test_renamed_from(self) -> None:
        fd = FieldDescriptor("action_interval", renamed_from=("skill_interval",))
        assert fd.renamed_from == ("skill_interval",)


class TestMigrateConfig:
    def test_no_migration_needed(self) -> None:
        data = {"_schema_version": SCHEMA_VERSION, "key": "value"}
        result = migrate_config(data, "test")
        assert result["key"] == "value"

    def test_migration_from_version_0(self) -> None:
        @register_migration("test_section", 0)
        def _migrate(data: dict) -> dict:
            data["new_key"] = data.pop("old_key", "default")
            return data

        data = {"old_key": "hello"}
        result = migrate_config(data, "test_section")
        assert result["new_key"] == "hello"
        assert result["_schema_version"] == SCHEMA_VERSION

    def test_unknown_section_no_crash(self) -> None:
        data = {"key": "value"}
        result = migrate_config(data, "nonexistent_section")
        assert result["key"] == "value"


class TestApplyFieldRenames:
    def test_rename_applied(self) -> None:
        fields = (
            FieldDescriptor("new_name", renamed_from=("old_name",)),
        )
        data = {"old_name": 42}
        result = apply_field_renames(data, fields)
        assert result["new_name"] == 42
        assert "old_name" not in result

    def test_no_rename_when_new_exists(self) -> None:
        fields = (
            FieldDescriptor("new_name", renamed_from=("old_name",)),
        )
        data = {"old_name": 1, "new_name": 2}
        result = apply_field_renames(data, fields)
        assert result["new_name"] == 2

    def test_no_rename_when_old_missing(self) -> None:
        fields = (
            FieldDescriptor("new_name", renamed_from=("old_name",)),
        )
        data: dict = {"other": 3}
        result = apply_field_renames(data, fields)
        assert result == {"other": 3}


class TestFillDefaults:
    def test_fill_missing(self) -> None:
        fields = (
            FieldDescriptor("timeout", "int", 30),
            FieldDescriptor("retries", "int", 3),
        )
        data: dict = {"timeout": 60}
        result = fill_defaults(data, fields)
        assert result["timeout"] == 60
        assert result["retries"] == 3

    def test_no_override_existing(self) -> None:
        fields = (
            FieldDescriptor("timeout", "int", 30),
        )
        data = {"timeout": 60}
        result = fill_defaults(data, fields)
        assert result["timeout"] == 60

    def test_skip_none_default(self) -> None:
        fields = (
            FieldDescriptor("optional", default=None),
        )
        data: dict = {}
        result = fill_defaults(data, fields)
        assert "optional" not in result
