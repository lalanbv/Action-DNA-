"""标准化错误码 + 错误详情 — 统一的错误描述模型。

参考 Peekaboo StandardizedError 设计，为 Action<DNA> 提供结构化的错误信息：
- 标准错误码枚举覆盖所有领域
- StandardizedError 携带恢复建议和上下文
- 支持序列化/反序列化用于跨组件传递
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

__all__ = ["StandardErrorCode", "StandardizedError"]


class StandardErrorCode(Enum):
    """标准化错误码枚举。"""

    # ── 权限 ──────────────────────────────────────────────────────
    PERMISSION_DENIED_SCREEN = "PERMISSION_DENIED_SCREEN"
    PERMISSION_DENIED_INPUT = "PERMISSION_DENIED_INPUT"

    # ── 视觉检测 ──────────────────────────────────────────────────
    TEMPLATE_NOT_FOUND = "TEMPLATE_NOT_FOUND"
    TEMPLATE_MATCH_THRESHOLD = "TEMPLATE_MATCH_THRESHOLD"
    OCR_UNAVAILABLE = "OCR_UNAVAILABLE"
    OCR_RECOGNITION_FAILED = "OCR_RECOGNITION_FAILED"
    PIXEL_NOT_FOUND = "PIXEL_NOT_FOUND"
    VISION_PREPROCESS_FAILED = "VISION_PREPROCESS_FAILED"

    # ── 输入模拟 ──────────────────────────────────────────────────
    INPUT_TARGET_OUT_OF_BOUNDS = "INPUT_TARGET_OUT_OF_BOUNDS"
    INPUT_MOUSE_MOVE_FAILED = "INPUT_MOUSE_MOVE_FAILED"
    INPUT_KEY_UNSUPPORTED = "INPUT_KEY_UNSUPPORTED"

    # ── 引擎执行 ──────────────────────────────────────────────────
    ENGINE_GRAPH_INVALID = "ENGINE_GRAPH_INVALID"
    ENGINE_NODE_TIMEOUT = "ENGINE_NODE_TIMEOUT"
    ENGINE_LOOP_LIMIT = "ENGINE_LOOP_LIMIT"
    ENGINE_STOPPED = "ENGINE_STOPPED"

    # ── 插件系统 ──────────────────────────────────────────────────
    PLUGIN_LOAD_FAILED = "PLUGIN_LOAD_FAILED"
    PLUGIN_PERMISSION_DENIED = "PLUGIN_PERMISSION_DENIED"
    PLUGIN_VERSION_MISMATCH = "PLUGIN_VERSION_MISMATCH"

    # ── 系统层 ────────────────────────────────────────────────────
    SYSTEM_SCREENSHOT_FAILED = "SYSTEM_SCREENSHOT_FAILED"
    SYSTEM_FILE_NOT_FOUND = "SYSTEM_FILE_NOT_FOUND"


@dataclass(frozen=True)
class StandardizedError:
    """标准化错误详情 — 携带错误码、消息、恢复建议和上下文。"""

    code: StandardErrorCode
    message: str
    recovery_suggestion: str
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "message": self.message,
            "recovery_suggestion": self.recovery_suggestion,
            "context": self.context,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StandardizedError:
        return cls(
            code=StandardErrorCode(data["code"]),
            message=data["message"],
            recovery_suggestion=data["recovery_suggestion"],
            context=data.get("context", {}),
        )
