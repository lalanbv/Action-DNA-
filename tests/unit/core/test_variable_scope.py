"""VariableScope 枚举测试。"""

from src.core.variables.scope import VariableScope


class TestVariableScopeMembers:

    def test_three_members_exist(self):
        members = list(VariableScope)
        assert len(members) == 3
        names = {m.name for m in members}
        assert names == {"GLOBAL", "NODE", "STEP"}

    def test_string_values(self):
        assert VariableScope.GLOBAL.value == "global"
        assert VariableScope.NODE.value == "node"
        assert VariableScope.STEP.value == "step"


class TestPriority:

    def test_step_highest(self):
        assert VariableScope.STEP.priority == 2

    def test_node_middle(self):
        assert VariableScope.NODE.priority == 1

    def test_global_lowest(self):
        assert VariableScope.GLOBAL.priority == 0

    def test_lookup_order(self):
        """STEP -> NODE -> GLOBAL 优先级递减"""
        order = sorted(VariableScope, key=lambda s: s.priority, reverse=True)
        assert order == [VariableScope.STEP, VariableScope.NODE, VariableScope.GLOBAL]
