"""变量作用域枚举，定义 GLOBAL / NODE / STEP 三级分层查找。"""

from enum import Enum


class VariableScope(Enum):
    """
    变量作用域。

    分层设计：
    - GLOBAL: 全局作用域，整个执行期间有效。跨节点共享。
    - NODE:   节点作用域，单个节点执行期间有效。节点间隔离。
    - STEP:   步骤作用域，单次执行（一次 run）有效。

    查找顺序：STEP -> NODE -> GLOBAL（类似 Python 的 LEGB 规则）
    """

    GLOBAL = "global"
    NODE = "node"
    STEP = "step"

    @property
    def priority(self) -> int:
        """查找优先级（数字越大越优先查找）"""
        match self:
            case VariableScope.STEP:
                return 2
            case VariableScope.NODE:
                return 1
            case VariableScope.GLOBAL:
                return 0
        return 0
