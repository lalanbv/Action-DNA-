"""插件清单验证器 — 受 Blender blender_manifest.toml 启发。

在加载插件代码之前，先验证 plugin.json 清单的完整性和版本兼容性，
拒绝不兼容或有缺陷的插件，避免运行时崩溃。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from src.utils.i18n import t

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = {"id", "version", "permissions"}


@dataclass(frozen=True)
class EngineVersion:
    """语义化版本号。"""

    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, version_str: str) -> EngineVersion:
        """解析 "X.Y.Z" 格式的版本号。"""
        match = re.match(r"^(\d+)\.(\d+)\.(\d+)", version_str.strip())
        if not match:
            raise ValueError(
                t("plugins.exc.invalid_version_format", version_str=version_str)
            )
        return cls(int(match[1]), int(match[2]), int(match[3]))

    def __lt__(self, other: EngineVersion) -> bool:
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)

    def __le__(self, other: EngineVersion) -> bool:
        return (self.major, self.minor, self.patch) <= (other.major, other.minor, other.patch)

    def __gt__(self, other: EngineVersion) -> bool:
        return (self.major, self.minor, self.patch) > (other.major, other.minor, other.patch)

    def __ge__(self, other: EngineVersion) -> bool:
        return (self.major, self.minor, self.patch) >= (other.major, other.minor, other.patch)

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


def validate_manifest(
    manifest: dict,
    app_version: str,
) -> list[str]:
    """验证插件清单，返回错误列表（空列表表示通过）。

    Args:
        manifest: 从 plugin.json 加载的字典。
        app_version: 当前引擎版本号（如 "2.0.0"）。
    """
    errors: list[str] = []

    # 必填字段检查
    missing = REQUIRED_FIELDS - set(manifest.keys())
    if missing:
        errors.append(t("plugins.validation.missing_required_fields", missing=missing))
        return errors

    # 版本格式检查
    plugin_version = manifest.get("version", "")
    try:
        EngineVersion.parse(plugin_version)
    except ValueError as e:
        errors.append(str(e))

    # 引擎版本兼容性检查
    engine_min = manifest.get("engine_version_min")
    engine_max = manifest.get("engine_version_max")
    if engine_min or engine_max:
        try:
            current = EngineVersion.parse(app_version)
            if engine_min:
                min_ver = EngineVersion.parse(engine_min)
                if current < min_ver:
                    errors.append(
                        t("plugins.validation.engine_version_incompatible_min", min_ver=min_ver, current=current)
                    )
            if engine_max:
                max_ver = EngineVersion.parse(engine_max)
                if current > max_ver:
                    errors.append(
                        t("plugins.validation.engine_version_incompatible_max", max_ver=max_ver, current=current)
                    )
        except ValueError as e:
            errors.append(t("plugins.validation.version_parse_failed", error=e))

    # permissions 类型检查
    permissions = manifest.get("permissions")
    if not isinstance(permissions, list):
        errors.append(t("plugins.validation.permissions_not_list"))

    return errors
