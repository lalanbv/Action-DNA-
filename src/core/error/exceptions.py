"""Action<DNA> 异常层次结构。

提供统一的异常基类和上下文丰富的子类，便于顶层统一捕获和精细处理。
异常按领域分层：引擎、视觉、输入、插件。

所有异常支持 from_code() 工厂方法，通过 ErrorRegistry 数值错误码创建。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.error.error_codes import StandardizedError

__all__ = [
    "DNAError",
    "GraphExecutionError",
    "NodeExecutionError",
    "NodeTimeoutError",
    "EngineStoppedError",
    "VisionError",
    "TemplateNotFoundError",
    "OCRUnavailableError",
    "PixelNotFoundError",
    "InputError",
    "TargetOutOfBoundsError",
    "PluginError",
    "PluginLoadError",
    "PluginPermissionError",
]


class DNAError(Exception):
    """Action<DNA> 基础异常类。

    可选携带 StandardizedError 以提供结构化错误信息。
    支持通过 ErrorRegistry 数值错误码创建。
    """

    def __init__(
        self,
        message: str,
        *args: object,
        error: StandardizedError | None = None,
    ) -> None:
        super().__init__(message, *args)
        self.message = message
        self.std_error = error

    def __str__(self) -> str:
        return self.message

    @classmethod
    def from_code(cls, error_id: int, **context: object) -> DNAError:
        """从 ErrorRegistry 数值错误码创建异常。"""
        from src.core.error.error_registry import ErrorRegistry

        std_error = ErrorRegistry.create(error_id, **context)
        return cls(std_error.message, error=std_error)


# ══════════════════════════════════════════════════════════════════
#  引擎层异常
# ══════════════════════════════════════════════════════════════════


class GraphExecutionError(DNAError):
    """图执行级错误 — 终止整个图执行。"""

    def __init__(
        self,
        message: str,
        graph_id: str = "",
        node_id: str | None = None,
        *,
        error: StandardizedError | None = None,
    ) -> None:
        super().__init__(message, error=error)
        self.graph_id = graph_id
        self.node_id = node_id

    @classmethod
    def from_code(
        cls,
        error_id: int,
        graph_id: str = "",
        node_id: str | None = None,
        **context: object,
    ) -> GraphExecutionError:
        from src.core.error.error_registry import ErrorRegistry

        std_error = ErrorRegistry.create(error_id, **context)
        return cls(
            std_error.message, graph_id=graph_id, node_id=node_id, error=std_error
        )


class NodeExecutionError(DNAError):
    """节点执行级错误 — 携带节点上下文信息。"""

    def __init__(
        self,
        message: str,
        node_id: str,
        node_type: str,
        step_index: int = -1,
        retry_count: int = 0,
        original_error: Exception | None = None,
        *,
        error: StandardizedError | None = None,
    ) -> None:
        super().__init__(message, error=error)
        self.node_id = node_id
        self.node_type = node_type
        self.step_index = step_index
        self.retry_count = retry_count
        self.original_error = original_error

    @classmethod
    def from_code(
        cls,
        error_id: int,
        node_id: str,
        node_type: str = "",
        **context: object,
    ) -> NodeExecutionError:
        from src.core.error.error_registry import ErrorRegistry

        context.setdefault("node_id", node_id)
        std_error = ErrorRegistry.create(error_id, **context)
        return cls(
            std_error.message, node_id=node_id, node_type=node_type, error=std_error
        )


class NodeTimeoutError(NodeExecutionError):
    """节点执行超时。"""

    def __init__(
        self,
        message: str,
        node_id: str,
        node_type: str = "",
        timeout_seconds: float = 0.0,
        *,
        error: StandardizedError | None = None,
    ) -> None:
        super().__init__(message, node_id=node_id, node_type=node_type, error=error)
        self.timeout_seconds = timeout_seconds


class EngineStoppedError(DNAError):
    """引擎被主动停止。"""

    def __init__(
        self,
        message: str = "引擎已停止",
        *,
        error: StandardizedError | None = None,
    ) -> None:
        super().__init__(message, error=error)


# ══════════════════════════════════════════════════════════════════
#  视觉层异常
# ══════════════════════════════════════════════════════════════════


class VisionError(DNAError):
    """视觉检测层基础异常。"""


class TemplateNotFoundError(VisionError):
    """模板图片未找到或匹配失败。"""


class OCRUnavailableError(VisionError):
    """OCR 引擎不可用（依赖未安装）。"""


class PixelNotFoundError(VisionError):
    """指定颜色的像素未找到。"""


# ══════════════════════════════════════════════════════════════════
#  输入层异常
# ══════════════════════════════════════════════════════════════════


class InputError(DNAError):
    """输入模拟层基础异常。"""


class TargetOutOfBoundsError(InputError):
    """目标坐标超出屏幕范围。"""


# ══════════════════════════════════════════════════════════════════
#  插件层异常
# ══════════════════════════════════════════════════════════════════


class PluginError(DNAError):
    """插件系统基础异常。"""


class PluginLoadError(PluginError):
    """插件加载失败。"""


class PluginPermissionError(PluginError):
    """插件权限不足。"""
