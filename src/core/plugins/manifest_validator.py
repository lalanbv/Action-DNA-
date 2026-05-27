"""插件清单验证器 — 受 Blender blender_manifest.toml 启发。

在加载插件代码之前，先验证 plugin.json 清单的完整性和版本兼容性，
拒绝不兼容或有缺陷的插件，避免运行时崩溃。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

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
            raise ValueError(f"无效版本号格式: {version_str!r}，预期 'X.Y.Z'")
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
        errors.append(f"缺少必填字段: {missing}")
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
                        f"引擎版本不兼容: 插件要求 >= {min_ver}，当前 {current}"
                    )
            if engine_max:
                max_ver = EngineVersion.parse(engine_max)
                if current > max_ver:
                    errors.append(
                        f"引擎版本不兼容: 插件要求 <= {max_ver}，当前 {current}"
                    )
        except ValueError as e:
            errors.append(f"版本解析失败: {e}")

    # permissions 类型检查
    permissions = manifest.get("permissions")
    if not isinstance(permissions, list):
        errors.append("permissions 必须是列表")

    return errors
