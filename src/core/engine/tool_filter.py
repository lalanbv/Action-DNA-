"""ToolFilter — 描述符类型的 allow/deny 过滤。

支持配置文件和环境变量两种配置方式，集成到 GraphEngine 管道中。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

__all__ = ["ToolFilter"]


@dataclass(frozen=True)
class ToolFilter:
    """描述符类型的 allow/deny 过滤。

    规则优先级：deny > allow > 默认允许。
    - allow=None 且 deny 为空：允许所有类型
    - allow 非空：仅允许列表中的类型
    - deny 中的类型始终被拒绝，即使在 allow 列表中
    """

    allow: frozenset[str] | None = None
    deny: frozenset[str] = field(default_factory=frozenset)

    def is_allowed(self, action_type: str) -> bool:
        """检查 action_type 是否被允许执行。"""
        if action_type in self.deny:
            return False
        if self.allow is not None and action_type not in self.allow:
            return False
        return True

    def filter_types(self, types: list[str]) -> list[str]:
        """过滤类型列表，返回允许的子集。"""
        return [t for t in types if self.is_allowed(t)]

    @classmethod
    def from_config(cls, config: dict) -> ToolFilter:
        """从配置字典创建过滤器。

        格式: {"allow": ["click_image", "click_pos"], "deny": ["record"]}
        """
        allow_raw = config.get("allow", [])
        deny_raw = config.get("deny", [])
        allow = frozenset(allow_raw) if allow_raw else None
        deny = frozenset(deny_raw)
        return cls(allow=allow, deny=deny)

    @classmethod
    def from_env(cls) -> ToolFilter:
        """从环境变量创建过滤器。

        DNA_ALLOW_TOOLS=click_image,click_pos,press_key
        DNA_DENY_TOOLS=record,idle_behavior
        """
        allow_str = os.environ.get("DNA_ALLOW_TOOLS", "")
        deny_str = os.environ.get("DNA_DENY_TOOLS", "")
        allow = frozenset(allow_str.split(",")) if allow_str else None
        deny = frozenset(deny_str.split(",")) if deny_str else frozenset()
        return cls(allow=allow, deny=deny)

    @classmethod
    def allow_all(cls) -> ToolFilter:
        """创建允许所有类型的过滤器。"""
        return cls()
