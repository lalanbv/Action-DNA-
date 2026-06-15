"""节点描述符 ABC — ComfyUI「类即元数据」模式的核心抽象。

每种动作类型对应一个 NodeDescriptor 子类，同时声明元数据和行为，
替代 ActionExecutor 中的 140 行 match 语句。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from src.core.step_types import BaseStep
from src.utils.i18n import t

if TYPE_CHECKING:
    from src.core.engine.execution_blocker import ExecutionBlocker
    from src.core.engine.execution_context import ExecutionContext
    from src.core.engine.node_result import NodeResult

logger = logging.getLogger(__name__)

_MISSING = object()


@dataclass(frozen=True)
class PortDef:
    """端口定义 — 描述节点的输入/输出端口。

    用于 UI 自动生成连线界面、运行时类型检查、配置验证。
    """

    type: str
    description: str
    required: bool = True
    default: Any = None


class NodeDescriptor(ABC):
    """节点描述符抽象基类（ComfyUI 启发：类即元数据）。

    每种动作类型实现一个子类，声明自己的输入/输出类型、分类、执行逻辑。

    子类必须实现：
    - action_type()      -> 节点类型标识符
    - display_name()     -> UI 显示名称
    - category()         -> 分类
    - input_types()      -> 输入端口定义
    - output_types()     -> 输出端口定义
    - execute(ctx)       -> 执行逻辑

    可选覆盖：
    - validate_inputs()  -> 输入验证
    - build_dialog()     -> 配置对话框
    - on_enter()         -> 进入节点钩子
    - on_exit()          -> 退出节点钩子
    """

    # ---- 元数据（类方法，子类必须实现）----

    @classmethod
    @abstractmethod
    def action_type(cls) -> str:
        """节点类型标识符，如 'CLICK_IMAGE', 'WAIT'。"""

    @classmethod
    @abstractmethod
    def display_name(cls) -> str:
        """UI 显示名称，如 '点击图片', '等待'。"""

    @classmethod
    @abstractmethod
    def category(cls) -> str:
        """分类，如 '基础动作', '流程控制', '视觉检测'。"""

    @classmethod
    @abstractmethod
    def input_types(cls) -> dict[str, PortDef]:
        """输入端口定义: {端口名: PortDef(类型, 描述, 是否必需, 默认值)}。"""

    @classmethod
    @abstractmethod
    def output_types(cls) -> dict[str, PortDef]:
        """输出端口定义。"""

    # ---- 验证 ----

    @classmethod
    def validate_inputs(cls, action: BaseStep) -> list[str]:
        """验证输入参数，返回错误列表。空列表表示验证通过。"""
        errors: list[str] = []
        for name, port in cls.input_types().items():
            if port.required:
                value = getattr(action, name, _MISSING)
                if value is _MISSING or value is None:
                    errors.append(f"必需参数 '{name}' ({port.description}) 缺失")
        return errors

    # ---- UI 构建 ----

    @classmethod
    def build_dialog(
        cls,
        parent: Any,
        action: BaseStep,
        callback: Callable[[BaseStep], None],
    ) -> None:
        """构建配置对话框（可选覆盖）。

        默认使用通用对话框生成器（基于 input_types 自动生成）。
        复杂节点可以覆盖此方法提供自定义 UI。
        """
        try:
            from src.ui.dialogs.generic_node_dialog import build_generic_dialog

            build_generic_dialog(parent, cls, action, callback)
        except ImportError:
            logger.debug(t("engine.log.generic_dialog_unavailable"))

    # ---- 执行 ----

    @abstractmethod
    def execute(self, ctx: ExecutionContext) -> NodeResult | ExecutionBlocker:
        """执行节点逻辑。

        返回 NodeResult 或 ExecutionBlocker:
        - NodeResult(success=True) 表示成功
        - NodeResult(success=False) 表示失败
        - ExecutionBlocker 表示跳过（阻断信号）
        - output_vars 包含输出变量
        - next_label 指定下一条边
        - cooldown 指定执行后冷却时间
        """

    # ---- 生命周期钩子（PlayMaker 模式）----

    def on_enter(self, ctx: ExecutionContext) -> None:
        """进入节点时调用。用于初始化节点状态、重置计数器等。"""

    def on_exit(self, ctx: ExecutionContext) -> None:
        """退出节点时调用。用于清理资源、保存状态等。"""
