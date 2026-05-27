"""ErrorFormatter — 标准化错误输出格式化。

提供 CLI、JSON、日志三种输出格式，将 StandardizedError 转换为
人类可读的终端消息、结构化 JSON 字典、或紧凑的日志行。
"""

from __future__ import annotations

import json
from typing import Any

from src.core.error.error_codes import StandardizedError

__all__ = ["ErrorFormatter"]


class ErrorFormatter:
    """标准化错误输出格式化器。"""

    @staticmethod
    def format_cli(error: StandardizedError) -> str:
        """CLI 友好格式 — 适合终端输出。"""
        lines = [
            f"[{error.code.value}] {error.message}",
            f"  建议: {error.recovery_suggestion}",
        ]
        if error.context:
            for key, value in error.context.items():
                lines.append(f"  {key}: {value}")
        return "\n".join(lines)

    @staticmethod
    def format_json(error: StandardizedError) -> dict[str, Any]:
        """JSON 结构化格式 — 适合 API 响应和序列化。"""
        return error.to_dict()

    @staticmethod
    def format_json_string(error: StandardizedError) -> str:
        """JSON 字符串格式 — 适合日志文件。"""
        return json.dumps(ErrorFormatter.format_json(error), ensure_ascii=False)

    @staticmethod
    def format_log(error: StandardizedError) -> str:
        """紧凑日志格式 — 适合单行日志记录。"""
        ctx_str = " ".join(f"{k}={v}" for k, v in error.context.items())
        parts = [
            f"code={error.code.value}",
            f"msg={error.message}",
        ]
        if ctx_str:
            parts.append(f"ctx=({ctx_str})")
        return " ".join(parts)

    @staticmethod
    def format_from_exception(exc: Exception) -> str | None:
        """从异常中提取 StandardizedError 并格式化为 CLI 格式。

        返回 None 如果异常不包含 StandardizedError。
        """
        from src.core.error.exceptions import DNAError

        if isinstance(exc, DNAError):
            error = getattr(exc, "std_error", None)
            if error is not None and isinstance(error, StandardizedError):
                return ErrorFormatter.format_cli(error)
        return None
