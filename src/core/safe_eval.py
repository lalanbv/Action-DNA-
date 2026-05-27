"""安全表达式求值器 — 用于断点条件、调试器和通知触发器。

提供受限的 AST 白名单验证 + eval 求值，防止代码注入。
所有条件断点和调试器的 eval() 调用都应使用此模块。
"""

from __future__ import annotations

import ast
import logging
from typing import Any

logger = logging.getLogger(__name__)

_ALLOWED_AST_NODES = (
    ast.Expression, ast.Compare, ast.BoolOp, ast.BinOp,
    ast.UnaryOp, ast.Constant, ast.Name, ast.Load,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.In, ast.NotIn,
    ast.And, ast.Or, ast.Not,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.USub,
)


def safe_eval(
    expression: str,
    local_vars: dict[str, Any] | None = None,
) -> bool:
    """安全评估表达式字符串，返回布尔结果。

    Args:
        expression: 要评估的条件表达式。
        local_vars: 可用变量字典。

    Returns:
        评估结果；语法错误或不安全表达式返回 False。
    """
    if local_vars is None:
        local_vars = {}

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as e:
        logger.warning("表达式语法错误: %s, 错误: %s", expression, e)
        return False

    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_AST_NODES):
            logger.warning("表达式包含不允许的节点: %s", expression)
            return False

    try:
        code = compile(tree, "<safe_eval>", "eval")
        return bool(eval(code, {"__builtins__": {}}, local_vars))  # noqa: S307
    except Exception as e:
        logger.warning("表达式评估失败: %s → %s", expression, e)
        return False


def build_eval_context(
    ctx: Any,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """从执行上下文构建安全求值的变量字典。

    Args:
        ctx: ExecutionContext 实例（可能有 flatten_variables 方法）。
        extra: 额外变量（如 hit_count、step_index）。

    Returns:
        可直接传给 safe_eval 的 local_vars 字典。
    """
    local_vars: dict[str, Any] = {}
    if hasattr(ctx, "flatten_variables"):
        local_vars.update(ctx.flatten_variables())
    if extra:
        local_vars.update(extra)
    return local_vars
