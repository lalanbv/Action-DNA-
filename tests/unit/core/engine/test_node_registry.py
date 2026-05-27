"""NodeRegistry 单元测试 — 验证注册、查询、分类、注销和 auto_register。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.core.engine.node_descriptor import NodeDescriptor, PortDef
from src.core.engine.node_registry import NodeRegistry, auto_register


# ---- 固定桩：可复用的测试用 NodeDescriptor 子类 ----


def _make_descriptor(
    action_type: str = "TEST",
    display_name: str = "测试节点",
    category: str = "测试分类",
) -> type[NodeDescriptor]:
    """动态创建一个最小化的 NodeDescriptor 子类。"""

    class StubDescriptor(NodeDescriptor):
        @classmethod
        def action_type(cls) -> str:
            return action_type

        @classmethod
        def display_name(cls) -> str:
            return display_name

        @classmethod
        def category(cls) -> str:
            return category

        @classmethod
        def input_types(cls) -> dict[str, PortDef]:
            return {}

        @classmethod
        def output_types(cls) -> dict[str, PortDef]:
            return {}

        def execute(self, ctx: MagicMock) -> MagicMock:
            return MagicMock()

    StubDescriptor.__name__ = f"{action_type}Descriptor"
    StubDescriptor.__qualname__ = f"{action_type}Descriptor"
    return StubDescriptor


# ---- 每个测试前清空注册表 ----


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    NodeRegistry.clear()


# ---- register + get ----


class TestRegisterAndGet:
    """注册和查询。"""

    def test_register_and_get(self) -> None:
        desc = _make_descriptor("CLICK")
        NodeRegistry.register(desc)
        assert NodeRegistry.get("CLICK") is desc

    def test_get_unregistered_raises_key_error(self) -> None:
        with pytest.raises(KeyError, match="未注册的节点类型"):
            NodeRegistry.get("NONEXISTENT")

    def test_register_multiple_types(self) -> None:
        a = _make_descriptor("A")
        b = _make_descriptor("B")
        NodeRegistry.register(a)
        NodeRegistry.register(b)
        assert NodeRegistry.get("A") is a
        assert NodeRegistry.get("B") is b

    def test_register_overwrites_existing(self) -> None:
        old = _make_descriptor("X", display_name="旧")
        new = _make_descriptor("X", display_name="新")
        NodeRegistry.register(old)
        NodeRegistry.register(new)
        assert NodeRegistry.get("X") is new

    def test_register_overwrite_different_category_cleans_old(self) -> None:
        old = _make_descriptor("X", category="旧分类")
        new = _make_descriptor("X", category="新分类")
        NodeRegistry.register(old)
        NodeRegistry.register(new)
        palette = NodeRegistry.palette()
        assert "旧分类" not in palette
        assert "新分类" in palette
        assert palette["新分类"][0][0] == "X"


# ---- has ----


class TestHas:
    """检查是否已注册。"""

    def test_has_registered(self) -> None:
        NodeRegistry.register(_make_descriptor("Y"))
        assert NodeRegistry.has("Y") is True

    def test_has_not_registered(self) -> None:
        assert NodeRegistry.has("MISSING") is False


# ---- all_types ----


class TestAllTypes:
    """返回所有已注册 action_type。"""

    def test_empty(self) -> None:
        assert NodeRegistry.all_types() == []

    def test_returns_all(self) -> None:
        NodeRegistry.register(_make_descriptor("A"))
        NodeRegistry.register(_make_descriptor("B"))
        result = NodeRegistry.all_types()
        assert set(result) == {"A", "B"}


# ---- categories / palette ----


class TestPalette:
    """分类节点列表。"""

    def test_single_category(self) -> None:
        NodeRegistry.register(
            _make_descriptor("A", display_name="节点A", category="基础动作")
        )
        NodeRegistry.register(
            _make_descriptor("B", display_name="节点B", category="基础动作")
        )
        palette = NodeRegistry.palette()
        assert "基础动作" in palette
        assert palette["基础动作"] == [("A", "节点A"), ("B", "节点B")]

    def test_multiple_categories(self) -> None:
        NodeRegistry.register(
            _make_descriptor("A", category="基础动作")
        )
        NodeRegistry.register(
            _make_descriptor("B", category="流程控制")
        )
        palette = NodeRegistry.palette()
        assert "基础动作" in palette
        assert "流程控制" in palette

    def test_empty_after_clear(self) -> None:
        NodeRegistry.register(_make_descriptor("A"))
        NodeRegistry.clear()
        assert NodeRegistry.palette() == {}


# ---- unregister ----


class TestUnregister:
    """注销节点。"""

    def test_unregister_existing(self) -> None:
        NodeRegistry.register(_make_descriptor("X"))
        NodeRegistry.unregister("X")
        assert NodeRegistry.has("X") is False

    def test_unregister_removes_from_categories(self) -> None:
        NodeRegistry.register(
            _make_descriptor("X", category="流程控制")
        )
        NodeRegistry.unregister("X")
        palette = NodeRegistry.palette()
        assert "流程控制" not in palette

    def test_unregister_nonexistent_is_noop(self) -> None:
        NodeRegistry.unregister("GHOST")  # 不应抛异常

    def test_unregister_last_in_category_cleans_up(self) -> None:
        NodeRegistry.register(
            _make_descriptor("A", category="猫")
        )
        NodeRegistry.unregister("A")
        assert "猫" not in NodeRegistry.palette()

    def test_unregister_keeps_other_in_same_category(self) -> None:
        NodeRegistry.register(
            _make_descriptor("A", display_name="A", category="猫")
        )
        NodeRegistry.register(
            _make_descriptor("B", display_name="B", category="猫")
        )
        NodeRegistry.unregister("A")
        palette = NodeRegistry.palette()
        assert "猫" in palette
        types_in_cat = [t for t, _ in palette["猫"]]
        assert "B" in types_in_cat


# ---- clear ----


class TestClear:
    """清空注册表。"""

    def test_clear_empties_registry(self) -> None:
        NodeRegistry.register(_make_descriptor("A"))
        NodeRegistry.register(_make_descriptor("B"))
        NodeRegistry.clear()
        assert NodeRegistry.all_types() == []
        assert NodeRegistry.palette() == {}


# ---- auto_register 装饰器 ----


class TestAutoRegister:
    """auto_register 装饰器。"""

    def test_registers_class(self) -> None:
        desc = _make_descriptor("AUTO")
        decorated = auto_register(desc)
        assert NodeRegistry.has("AUTO") is True
        assert NodeRegistry.get("AUTO") is desc

    def test_returns_class_unchanged(self) -> None:
        desc = _make_descriptor("AUTO_RET")
        result = auto_register(desc)
        assert result is desc

    def test_can_instantiate_after_register(self) -> None:
        desc = _make_descriptor("INST")
        auto_register(desc)
        instance = NodeRegistry.get("INST")()
        assert isinstance(instance, NodeDescriptor)


# ---- 重复注册同分类不重复添加 ----


class TestDuplicateCategoryEntry:
    """同一 action_type 重复注册不应在 _categories 中产生重复条目。"""

    def test_no_duplicate_in_category(self) -> None:
        desc = _make_descriptor("DUP", category="分类")
        NodeRegistry.register(desc)
        NodeRegistry.register(desc)  # 再次注册
        types_in_cat = [t for t, _ in NodeRegistry.palette()["分类"]]
        assert types_in_cat.count("DUP") == 1
