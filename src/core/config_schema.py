"""配置 Schema 版本管理 — 受 Blender DNA/SDNA 启发。

每个配置节点的 JSON 文件内嵌 _schema_version 字段。
加载旧版本配置时，自动运行迁移链从旧版本升级到当前版本，
实现前向兼容。新增/重命名/删除字段只需添加一个迁移函数。
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from src.utils.i18n import t

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1


class FieldDescriptor:
    """字段描述符 — 记录字段元信息用于迁移。"""

    __slots__ = ("name", "field_type", "default", "renamed_from")

    def __init__(
        self,
        name: str,
        field_type: str = "str",
        default: Any = None,
        renamed_from: tuple[str, ...] = (),
    ) -> None:
        self.name = name
        self.field_type = field_type
        self.default = default
        self.renamed_from = renamed_from


# 迁移链：key=(section_name, from_version), value=migration_function
_MIGRATIONS: dict[tuple[str, int], Callable[[dict[str, Any]], dict[str, Any]]] = {}


def register_migration(section: str, from_version: int):
    """装饰器：注册版本迁移函数。

    用法::

        @register_migration("combat", 0)
        def _combat_v0_to_v1(data: dict) -> dict:
            data["action_interval"] = data.pop("skill_interval", 2.0)
            return data
    """
    def decorator(fn: Callable[[dict[str, Any]], dict[str, Any]]) -> Callable[[dict[str, Any]], dict[str, Any]]:
        _MIGRATIONS[(section, from_version)] = fn
        return fn
    return decorator


def migrate_config(raw: dict[str, Any], section: str) -> dict[str, Any]:
    """运行迁移链：从存储版本升级到当前 SCHEMA_VERSION。

    Args:
        raw: 从 JSON 加载的原始配置字典。
        section: 配置节名称（如 "combat", "window"）。

    Returns:
        迁移后的配置字典（原地修改并返回）。
    """
    stored_version = raw.get("_schema_version", 0)
    if stored_version >= SCHEMA_VERSION:
        return raw

    current = raw
    for version in range(stored_version, SCHEMA_VERSION):
        migrator = _MIGRATIONS.get((section, version))
        if migrator:
            logger.debug(
                t("config.log.migration", section=section, old_version=version, new_version=version + 1)
            )
            current = migrator(current)

    current["_schema_version"] = SCHEMA_VERSION
    return current


def apply_field_renames(
    data: dict[str, Any],
    fields: tuple[FieldDescriptor, ...],
) -> dict[str, Any]:
    """根据字段描述符的 renamed_from 自动重命名字段。"""
    rename_map: dict[str, str] = {}
    for f in fields:
        for old_name in f.renamed_from:
            rename_map[old_name] = f.name

    for old_name, new_name in rename_map.items():
        if old_name in data and new_name not in data:
            data[new_name] = data.pop(old_name)
    return data


def fill_defaults(
    data: dict[str, Any],
    fields: tuple[FieldDescriptor, ...],
) -> dict[str, Any]:
    """为缺失字段填充默认值。"""
    for f in fields:
        if f.name not in data and f.default is not None:
            data[f.name] = f.default
    return data
