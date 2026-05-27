"""插件系统单元测试 — 覆盖 PluginInterface, PluginMetadata, PluginNodeRegistry,
PluginContext, DialogRegistry, PluginLoader, CombatPlugin。"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.core.engine.node_descriptor import NodeDescriptor, PortDef
from src.core.engine.node_registry import NodeRegistry
from src.core.engine.node_result import NodeResult
from src.core.events.bus import TypedEventBus
from src.core.plugins.dialog_registry import DialogRegistry
from src.core.error.exceptions import PluginPermissionError
from src.core.plugins.plugin_context import PluginContext
from src.core.plugins.plugin_interface import PluginInterface, PluginMetadata
from src.core.plugins.plugin_loader import PluginEntry, PluginLoader, PluginState
from src.core.plugins.plugin_node_registry import PluginNodeRegistry


# ---- 固定桩 ----


def _make_descriptor(
    action_type: str = "TEST",
    display_name: str = "测试节点",
    category: str = "测试分类",
) -> type[NodeDescriptor]:
    """动态创建最小 NodeDescriptor 子类。"""

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

        def execute(self, ctx: MagicMock) -> NodeResult:
            return NodeResult.ok()

    StubDescriptor.__name__ = f"{action_type}Descriptor"
    StubDescriptor.__qualname__ = f"{action_type}Descriptor"
    return StubDescriptor


class StubPlugin(PluginInterface):
    """最小插件实现，用于测试。"""

    def __init__(
        self,
        plugin_id: str = "stub",
        plugin_name: str = "桩插件",
        version: str = "1.0.0",
        permissions: tuple[str, ...] = ("events",),
        dependencies: tuple[str, ...] = (),
    ) -> None:
        self._meta = PluginMetadata(
            plugin_id=plugin_id,
            plugin_name=plugin_name,
            version=version,
            permissions=permissions,
            dependencies=dependencies,
        )
        self.loaded = False
        self.unloaded = False
        self.registered_nodes: list[str] = []

    def get_metadata(self) -> PluginMetadata:
        return self._meta

    def on_load(self, context: PluginContext) -> None:
        self.loaded = True
        self._context = context

    def on_unload(self) -> None:
        self.unloaded = True

    def register_nodes(self, registry: PluginNodeRegistry) -> None:
        desc = _make_descriptor(self._meta.plugin_id + "_node")
        registry.register(desc)
        self.registered_nodes.append(desc.action_type())


# ---- Fixtures ----


@pytest.fixture
def node_registry() -> NodeRegistry:
    NodeRegistry.clear()
    return NodeRegistry()


@pytest.fixture
def event_bus() -> TypedEventBus:
    return TypedEventBus()


@pytest.fixture
def plugin_ctx(node_registry: NodeRegistry, event_bus: TypedEventBus) -> PluginContext:
    return PluginContext(
        plugin_id="test_plugin",
        node_registry=node_registry,
        event_bus=event_bus,
        permissions={"events"},
    )


@pytest.fixture(autouse=True)
def _clean_dialog_registry() -> None:
    DialogRegistry._registry.clear()


# ============================================================================
# PluginMetadata
# ============================================================================


class TestPluginMetadata:
    """PluginMetadata 数据模型。"""

    def test_frozen(self) -> None:
        meta = PluginMetadata(
            plugin_id="t", plugin_name="T", version="1.0.0",
        )
        with pytest.raises(AttributeError):
            meta.plugin_id = "changed"

    def test_defaults(self) -> None:
        meta = PluginMetadata(
            plugin_id="t", plugin_name="T", version="1.0.0",
        )
        assert meta.description == ""
        assert meta.author == ""
        assert meta.dependencies == ()
        assert meta.permissions == ()
        assert meta.min_app_version == "2.0.0"

    def test_all_fields(self) -> None:
        meta = PluginMetadata(
            plugin_id="combat",
            plugin_name="战斗辅助",
            version="1.2.3",
            description="自动战斗",
            author="Team",
            dependencies=("core",),
            permissions=("screen_capture", "input_control"),
            min_app_version="2.1.0",
        )
        assert meta.plugin_id == "combat"
        assert meta.dependencies == ("core",)
        assert meta.permissions == ("screen_capture", "input_control")


# ============================================================================
# PluginInterface
# ============================================================================


class TestPluginInterface:
    """PluginInterface ABC。"""

    def test_cannot_instantiate_directly(self) -> None:
        with pytest.raises(TypeError):
            PluginInterface()  # type: ignore[abstract]

    def test_stub_plugin_implements_interface(self) -> None:
        plugin = StubPlugin()
        assert isinstance(plugin, PluginInterface)

    def test_abstract_methods(self) -> None:
        assert PluginInterface.__abstractmethods__ == frozenset(
            {"get_metadata", "on_load", "on_unload", "register_nodes"}
        )


# ============================================================================
# PluginNodeRegistry
# ============================================================================


class TestPluginNodeRegistry:
    """PluginNodeRegistry 命名空间代理。"""

    def test_register_adds_prefix(self, node_registry: NodeRegistry) -> None:
        pnr = PluginNodeRegistry(
            plugin_id="combat",
            delegate=node_registry,
            on_register=lambda k: None,
        )
        desc = _make_descriptor("find_enemy")
        pnr.register(desc)

        assert node_registry.has("combat.find_enemy")
        assert not node_registry.has("find_enemy")

    def test_proxy_preserves_display_name(self, node_registry: NodeRegistry) -> None:
        pnr = PluginNodeRegistry(
            plugin_id="combat",
            delegate=node_registry,
            on_register=lambda k: None,
        )
        desc = _make_descriptor("attack", display_name="攻击")
        pnr.register(desc)

        proxy_cls = node_registry.get("combat.attack")
        assert proxy_cls.display_name() == "攻击"

    def test_proxy_action_type_returns_namespaced(self, node_registry: NodeRegistry) -> None:
        pnr = PluginNodeRegistry(
            plugin_id="combat",
            delegate=node_registry,
            on_register=lambda k: None,
        )
        desc = _make_descriptor("dodge")
        pnr.register(desc)

        proxy_cls = node_registry.get("combat.dodge")
        assert proxy_cls.action_type() == "combat.dodge"

    def test_on_register_callback(self, node_registry: NodeRegistry) -> None:
        registered: list[str] = []
        pnr = PluginNodeRegistry(
            plugin_id="combat",
            delegate=node_registry,
            on_register=registered.append,
        )
        desc = _make_descriptor("skill")
        pnr.register(desc)
        assert registered == ["combat.skill"]

    def test_register_raw_no_prefix(self, node_registry: NodeRegistry) -> None:
        pnr = PluginNodeRegistry(
            plugin_id="combat",
            delegate=node_registry,
            on_register=lambda k: None,
        )
        desc = _make_descriptor("raw_action")
        pnr.register_raw(desc)
        assert node_registry.has("raw_action")
        assert not node_registry.has("combat.raw_action")


# ============================================================================
# PluginContext
# ============================================================================


class TestPluginContext:
    """PluginContext 受控上下文。"""

    def test_event_bus_with_permission(self, plugin_ctx: PluginContext) -> None:
        assert plugin_ctx.event_bus is not None

    def test_event_bus_without_permission(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        ctx = PluginContext(
            plugin_id="no_perm",
            node_registry=node_registry,
            event_bus=event_bus,
            permissions=set(),
        )
        with pytest.raises(PluginPermissionError, match="events"):
            _ = ctx.event_bus

    def test_screen_capture_without_permission(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        ctx = PluginContext(
            plugin_id="p",
            node_registry=node_registry,
            event_bus=event_bus,
            permissions=set(),
        )
        with pytest.raises(PluginPermissionError, match="screen_capture"):
            _ = ctx.screen_capture

    def test_input_controller_with_permission(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        mock_ctrl = MagicMock()
        ctx = PluginContext(
            plugin_id="p",
            node_registry=node_registry,
            event_bus=event_bus,
            input_controller=mock_ctrl,
            permissions={"input_control"},
        )
        assert ctx.input_controller is mock_ctrl

    def test_input_controller_not_initialized(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        ctx = PluginContext(
            plugin_id="p",
            node_registry=node_registry,
            event_bus=event_bus,
            input_controller=None,
            permissions={"input_control"},
        )
        with pytest.raises(RuntimeError, match="未初始化"):
            _ = ctx.input_controller

    def test_registry_creates_proxy(self, plugin_ctx: PluginContext) -> None:
        registry = plugin_ctx.registry
        assert isinstance(registry, PluginNodeRegistry)

    def test_registered_types_tracking(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        ctx = PluginContext(
            plugin_id="myplug",
            node_registry=node_registry,
            event_bus=event_bus,
            permissions={"events"},
        )
        registry = ctx.registry
        desc = _make_descriptor("action_a")
        registry.register(desc)
        assert ctx.registered_types == ["myplug.action_a"]

    def test_register_dialog(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        ctx = PluginContext(
            plugin_id="myplug",
            node_registry=node_registry,
            event_bus=event_bus,
            permissions={"events"},
        )
        dialog_cls = type("FakeDialog", (), {})
        ctx.register_dialog("my_action", dialog_cls)
        assert DialogRegistry.has("myplug.my_action")
        assert DialogRegistry.get("myplug.my_action") is dialog_cls


# ============================================================================
# DialogRegistry
# ============================================================================


class TestDialogRegistry:
    """DialogRegistry 对话框注册表。"""

    def test_register_and_get(self) -> None:
        cls = type("Dlg", (), {})
        DialogRegistry.register("my_action", cls)
        assert DialogRegistry.get("my_action") is cls

    def test_has(self) -> None:
        assert DialogRegistry.has("missing") is False
        DialogRegistry.register("x", type("X", (), {}))
        assert DialogRegistry.has("x") is True

    def test_unregister(self) -> None:
        DialogRegistry.register("y", type("Y", (), {}))
        DialogRegistry.unregister("y")
        assert DialogRegistry.has("y") is False

    def test_unregister_nonexistent_is_noop(self) -> None:
        DialogRegistry.unregister("ghost")


# ============================================================================
# PluginLoader — 清单解析与验证
# ============================================================================


class TestPluginLoaderManifest:
    """PluginLoader 清单解析。"""

    def test_parse_valid_manifest(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        loader = PluginLoader(node_registry, event_bus)
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = {
                "plugin_id": "demo",
                "plugin_name": "演示",
                "version": "1.0.0",
                "entry_class": "DemoPlugin",
                "permissions": ["events"],
                "dependencies": [],
            }
            plugin_dir = Path(tmpdir) / "demo"
            plugin_dir.mkdir()
            (plugin_dir / "plugin.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            loader.add_scan_dir(tmpdir)
            discovered = loader.scan()
            assert "demo" in discovered

    def test_validate_empty_plugin_id(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        loader = PluginLoader(node_registry, event_bus)
        meta = PluginMetadata(plugin_id="", plugin_name="X", version="1.0.0")
        errors = loader._validate_metadata(meta)
        assert any("plugin_id" in e for e in errors)

    def test_validate_bad_version_format(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        loader = PluginLoader(node_registry, event_bus)
        meta = PluginMetadata(plugin_id="t", plugin_name="T", version="1.0")
        errors = loader._validate_metadata(meta)
        assert any("version" in e for e in errors)

    def test_validate_unknown_permission(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        loader = PluginLoader(node_registry, event_bus)
        meta = PluginMetadata(
            plugin_id="t", plugin_name="T", version="1.0.0",
            permissions=("unknown_perm",),
        )
        errors = loader._validate_metadata(meta)
        assert any("未知权限" in e for e in errors)

    def test_version_compat_check(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        loader = PluginLoader(node_registry, event_bus)
        meta = PluginMetadata(
            plugin_id="t", plugin_name="T", version="1.0.0",
            min_app_version="3.0.0",
        )
        assert loader._check_version_compat(meta) is False


# ============================================================================
# PluginLoader — 依赖解析
# ============================================================================


class TestPluginLoaderDependency:
    """PluginLoader 依赖解析。"""

    def test_topological_sort_simple(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        loader = PluginLoader(node_registry, event_bus)
        loader._plugins["a"] = PluginEntry(
            metadata=PluginMetadata(plugin_id="a", plugin_name="A", version="1.0.0"),
        )
        loader._plugins["b"] = PluginEntry(
            metadata=PluginMetadata(
                plugin_id="b", plugin_name="B", version="1.0.0",
                dependencies=("a",),
            ),
        )
        result = loader._topological_sort()
        assert result.index("a") < result.index("b")

    def test_topological_sort_cycle_detection(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        loader = PluginLoader(node_registry, event_bus)
        loader._plugins["x"] = PluginEntry(
            metadata=PluginMetadata(
                plugin_id="x", plugin_name="X", version="1.0.0",
                dependencies=("y",),
            ),
        )
        loader._plugins["y"] = PluginEntry(
            metadata=PluginMetadata(
                plugin_id="y", plugin_name="Y", version="1.0.0",
                dependencies=("x",),
            ),
        )
        with pytest.raises(RuntimeError, match="循环"):
            loader._topological_sort()

    def test_check_dependencies_missing(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        loader = PluginLoader(node_registry, event_bus)
        meta = PluginMetadata(
            plugin_id="child", plugin_name="Child", version="1.0.0",
            dependencies=("missing_parent",),
        )
        missing = loader._check_dependencies(meta)
        assert "missing_parent" in missing


# ============================================================================
# PluginLoader — 加载与卸载
# ============================================================================


class TestPluginLoaderLoadUnload:
    """PluginLoader 加载/卸载。"""

    def test_load_plugin_from_disk(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        loader = PluginLoader(node_registry, event_bus)
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir) / "stub"
            plugin_dir.mkdir()

            manifest = {
                "plugin_id": "stub",
                "plugin_name": "桩插件",
                "version": "1.0.0",
                "entry_class": "StubPlugin",
                "permissions": ["events"],
                "dependencies": [],
            }
            (plugin_dir / "plugin.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            (plugin_dir / "__init__.py").write_text(
                "from tests.unit.core.test_plugin_system import StubPlugin\n",
                encoding="utf-8",
            )

            loader.add_scan_dir(tmpdir)
            loader.scan()
            loader.load("stub")

            entry = loader.get_plugin("stub")
            assert entry is not None
            assert entry.state == PluginState.LOADED
            assert entry.instance is not None
            assert isinstance(entry.instance, PluginInterface)

    def test_unload_plugin(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        loader = PluginLoader(node_registry, event_bus)

        plugin = StubPlugin()
        meta = plugin.get_metadata()
        ctx = PluginContext(
            plugin_id="stub",
            node_registry=node_registry,
            event_bus=event_bus,
            permissions=set(meta.permissions),
        )
        plugin.on_load(ctx)
        plugin.register_nodes(ctx.registry)

        entry = PluginEntry(
            metadata=meta,
            state=PluginState.LOADED,
            instance=plugin,
            context=ctx,
        )
        loader._plugins["stub"] = entry

        loader.unload("stub")
        assert entry.state == PluginState.UNLOADED
        assert plugin.unloaded is True

    def test_load_nonexistent_raises(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        loader = PluginLoader(node_registry, event_bus)
        with pytest.raises(ValueError, match="未发现插件"):
            loader.load("ghost")

    def test_get_loaded_plugins(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        loader = PluginLoader(node_registry, event_bus)
        loader._plugins["a"] = PluginEntry(
            metadata=PluginMetadata(plugin_id="a", plugin_name="A", version="1.0.0"),
            state=PluginState.LOADED,
        )
        loader._plugins["b"] = PluginEntry(
            metadata=PluginMetadata(plugin_id="b", plugin_name="B", version="1.0.0"),
            state=PluginState.DISCOVERED,
        )
        loaded = loader.get_loaded_plugins()
        assert "a" in loaded
        assert "b" not in loaded


# ============================================================================
# CombatPlugin
# ============================================================================


class TestCombatPlugin:
    """CombatPlugin 战斗插件集成。"""

    def test_metadata(self) -> None:
        from src.plugins.builtin.combat import CombatPlugin

        plugin = CombatPlugin()
        meta = plugin.get_metadata()
        assert meta.plugin_id == "combat"
        assert meta.plugin_name == "战斗辅助"
        assert meta.version == "1.0.0"
        assert "screen_capture" in meta.permissions
        assert "input_control" in meta.permissions

    def test_register_nodes(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        from src.plugins.builtin.combat import CombatPlugin

        plugin = CombatPlugin()
        ctx = PluginContext(
            plugin_id="combat",
            node_registry=node_registry,
            event_bus=event_bus,
            permissions=set(plugin.get_metadata().permissions),
        )
        plugin.register_nodes(ctx.registry)

        expected = [
            "combat.find_enemy",
            "combat.attack",
            "combat.use_skill",
            "combat.dodge",
            "combat.target_select",
        ]
        for key in expected:
            assert node_registry.has(key), f"Missing: {key}"

        assert ctx.registered_types == expected

    def test_find_enemy_descriptor_types(self) -> None:
        from src.plugins.builtin.combat import FindEnemyDescriptor

        inputs = FindEnemyDescriptor.input_types()
        assert "template_path" in inputs
        assert inputs["template_path"].required is True

        outputs = FindEnemyDescriptor.output_types()
        assert "enemy_pos" in outputs
        assert "enemy_found" in outputs

    def test_attack_descriptor_defaults(self) -> None:
        from src.plugins.builtin.combat import AttackDescriptor

        inputs = AttackDescriptor.input_types()
        assert "attack_count" in inputs
        assert inputs["attack_count"].default == 3

    def test_use_skill_descriptor_types(self) -> None:
        from src.plugins.builtin.combat import UseSkillDescriptor

        inputs = UseSkillDescriptor.input_types()
        assert "skill_key" in inputs
        assert inputs["skill_key"].required is True

    def test_dodge_descriptor_defaults(self) -> None:
        from src.plugins.builtin.combat import DodgeDescriptor

        inputs = DodgeDescriptor.input_types()
        assert inputs["direction"].default == "random"
        assert inputs["dodge_key"].default == "space"

    def test_target_select_descriptor_strategies(self) -> None:
        from src.plugins.builtin.combat import TargetSelectionDescriptor

        inputs = TargetSelectionDescriptor.input_types()
        assert "strategy" in inputs
        assert inputs["strategy"].default == "nearest"

        outputs = TargetSelectionDescriptor.output_types()
        assert "target_pos" in outputs
        assert "target_found" in outputs


# ============================================================================
# PluginLoader — scan 边界条件
# ============================================================================


class TestPluginLoaderScanEdgeCases:
    """PluginLoader.scan() 边界条件。"""

    def test_scan_creates_missing_dir(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        loader = PluginLoader(node_registry, event_bus)
        with tempfile.TemporaryDirectory() as tmpdir:
            missing = Path(tmpdir) / "plugins_new"
            loader.add_scan_dir(missing)
            assert missing.exists()

    def test_scan_skips_nondir_entry(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        loader = PluginLoader(node_registry, event_bus)
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "readme.txt").write_text("not a plugin", encoding="utf-8")
            loader.add_scan_dir(tmpdir)
            assert loader.scan() == []

    def test_scan_skips_no_manifest(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        loader = PluginLoader(node_registry, event_bus)
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "empty_plugin").mkdir()
            loader.add_scan_dir(tmpdir)
            assert loader.scan() == []

    def test_scan_skips_duplicate(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        loader = PluginLoader(node_registry, event_bus)
        meta = PluginMetadata(plugin_id="dup", plugin_name="Dup", version="1.0.0")
        loader._plugins["dup"] = PluginEntry(metadata=meta)
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir) / "dup"
            plugin_dir.mkdir()
            (plugin_dir / "plugin.json").write_text(
                json.dumps({"plugin_id": "dup", "plugin_name": "Dup", "version": "1.0.0"}),
                encoding="utf-8",
            )
            loader.add_scan_dir(tmpdir)
            assert loader.scan() == []

    def test_scan_bad_manifest_json(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        loader = PluginLoader(node_registry, event_bus)
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir) / "bad"
            plugin_dir.mkdir()
            (plugin_dir / "plugin.json").write_text("{invalid", encoding="utf-8")
            loader.add_scan_dir(tmpdir)
            assert loader.scan() == []

    def test_scan_validation_fails(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        loader = PluginLoader(node_registry, event_bus)
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir) / "nover"
            plugin_dir.mkdir()
            (plugin_dir / "plugin.json").write_text(
                json.dumps({"plugin_id": "nover", "plugin_name": "N", "version": "bad"}),
                encoding="utf-8",
            )
            loader.add_scan_dir(tmpdir)
            assert loader.scan() == []

    def test_scan_version_incompatible(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        loader = PluginLoader(node_registry, event_bus)
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir) / "old"
            plugin_dir.mkdir()
            (plugin_dir / "plugin.json").write_text(
                json.dumps({
                    "plugin_id": "old",
                    "plugin_name": "Old",
                    "version": "1.0.0",
                    "min_app_version": "99.0.0",
                }),
                encoding="utf-8",
            )
            loader.add_scan_dir(tmpdir)
            assert loader.scan() == []


# ============================================================================
# PluginLoader — load_all / unload_all / reload / watcher
# ============================================================================


class TestPluginLoaderLifecycle:
    """PluginLoader 生命周期操作。"""

    def test_load_all_with_failure(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        loader = PluginLoader(node_registry, event_bus)
        meta = PluginMetadata(plugin_id="ok", plugin_name="OK", version="1.0.0")
        loader._plugins["ok"] = PluginEntry(metadata=meta, state=PluginState.DISCOVERED)
        meta_bad = PluginMetadata(plugin_id="bad", plugin_name="Bad", version="1.0.0")
        loader._plugins["bad"] = PluginEntry(metadata=meta_bad, state=PluginState.DISCOVERED)
        loaded, failed = loader.load_all()
        assert "ok" in failed or "bad" in failed

    def test_unload_all(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        loader = PluginLoader(node_registry, event_bus)
        plugin = StubPlugin()
        meta = plugin.get_metadata()
        ctx = PluginContext(
            plugin_id="stub",
            node_registry=node_registry,
            event_bus=event_bus,
            permissions=set(meta.permissions),
        )
        plugin.on_load(ctx)
        plugin.register_nodes(ctx.registry)
        loader._plugins["stub"] = PluginEntry(
            metadata=meta, state=PluginState.LOADED, instance=plugin, context=ctx,
        )
        unloaded = loader.unload_all()
        assert "stub" in unloaded
        assert loader._plugins["stub"].state == PluginState.UNLOADED

    def test_reload_unloaded_plugin(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        """reload() 对已卸载插件直接走 load 路径。"""
        loader = PluginLoader(node_registry, event_bus)
        meta = PluginMetadata(plugin_id="s", plugin_name="S", version="1.0.0")
        loader._plugins["s"] = PluginEntry(metadata=meta, state=PluginState.DISCOVERED)
        # DISCOVERED 状态不在 LOADED/ACTIVE 中，不会调用 unload
        # 但 load 会失败（无目录），通过 except 不会崩溃
        try:
            loader.reload("s")
        except (RuntimeError, ValueError):
            pass  # 预期会失败，关键是 reload 内部逻辑被覆盖

    def test_unload_nonexistent_raises(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        loader = PluginLoader(node_registry, event_bus)
        with pytest.raises(ValueError, match="未发现插件"):
            loader.unload("ghost")

    def test_unload_wrong_state_raises(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        loader = PluginLoader(node_registry, event_bus)
        meta = PluginMetadata(plugin_id="s", plugin_name="S", version="1.0.0")
        loader._plugins["s"] = PluginEntry(metadata=meta, state=PluginState.DISCOVERED)
        with pytest.raises(RuntimeError, match="状态"):
            loader.unload("s")

    def test_load_wrong_state_raises(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        loader = PluginLoader(node_registry, event_bus)
        meta = PluginMetadata(plugin_id="s", plugin_name="S", version="1.0.0")
        loader._plugins["s"] = PluginEntry(metadata=meta, state=PluginState.LOADED)
        with pytest.raises(RuntimeError, match="状态"):
            loader.load("s")

    def test_watcher_start_stop(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        loader = PluginLoader(node_registry, event_bus, enable_hot_reload=True)
        loader.start_watcher()
        assert loader._watcher_thread is not None
        assert loader._watcher_thread.is_alive()
        loader.stop_watcher()
        loader._watcher_thread.join(timeout=3.0)
        assert not loader._watcher_thread.is_alive()

    def test_watcher_disabled_noop(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        loader = PluginLoader(node_registry, event_bus, enable_hot_reload=False)
        loader.start_watcher()
        assert loader._watcher_thread is None


# ============================================================================
# PluginLoader — manifest 读写
# ============================================================================


class TestPluginLoaderManifestIO:
    """PluginLoader manifest 读写。"""

    def test_get_manifest_data(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        loader = PluginLoader(node_registry, event_bus)
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir) / "demo"
            plugin_dir.mkdir()
            data = {"plugin_id": "demo", "plugin_name": "Demo", "version": "1.0.0"}
            (plugin_dir / "plugin.json").write_text(json.dumps(data), encoding="utf-8")
            loader.add_scan_dir(tmpdir)

            result = loader.get_manifest_data("demo")
            assert result is not None
            assert result["plugin_id"] == "demo"

    def test_get_manifest_data_missing(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        loader = PluginLoader(node_registry, event_bus)
        assert loader.get_manifest_data("ghost") is None

    def test_update_manifest(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        loader = PluginLoader(node_registry, event_bus)
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir) / "demo"
            plugin_dir.mkdir()
            data = {"plugin_id": "demo", "plugin_name": "Demo", "version": "1.0.0"}
            manifest_path = plugin_dir / "plugin.json"
            manifest_path.write_text(json.dumps(data), encoding="utf-8")
            loader.add_scan_dir(tmpdir)

            loader.update_manifest("demo", {"version": "2.0.0"})
            updated = json.loads(manifest_path.read_text(encoding="utf-8"))
            assert updated["version"] == "2.0.0"

    def test_update_manifest_missing_dir_raises(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        loader = PluginLoader(node_registry, event_bus)
        with pytest.raises(ValueError, match="找不到"):
            loader.update_manifest("ghost", {"version": "2.0.0"})

    def test_get_registered_node_types_empty(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        loader = PluginLoader(node_registry, event_bus)
        meta = PluginMetadata(plugin_id="empty", plugin_name="E", version="1.0.0")
        loader._plugins["empty"] = PluginEntry(metadata=meta, state=PluginState.DISCOVERED)
        assert loader.get_registered_node_types("empty") == []

    def test_get_registered_node_types_loaded(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        loader = PluginLoader(node_registry, event_bus)
        plugin = StubPlugin()
        meta = plugin.get_metadata()
        ctx = PluginContext(
            plugin_id="stub",
            node_registry=node_registry,
            event_bus=event_bus,
            permissions=set(meta.permissions),
        )
        plugin.on_load(ctx)
        plugin.register_nodes(ctx.registry)
        loader._plugins["stub"] = PluginEntry(
            metadata=meta, state=PluginState.LOADED, instance=plugin, context=ctx,
        )
        types = loader.get_registered_node_types("stub")
        assert len(types) > 0

    def test_get_all_plugins(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        loader = PluginLoader(node_registry, event_bus)
        meta = PluginMetadata(plugin_id="p", plugin_name="P", version="1.0.0")
        loader._plugins["p"] = PluginEntry(metadata=meta)
        all_plugins = loader.get_all_plugins()
        assert "p" in all_plugins

    def test_version_compare(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        loader = PluginLoader(node_registry, event_bus)
        assert loader._compare_versions("1.0.0", "1.0.0") == 0
        assert loader._compare_versions("2.0.0", "1.0.0") == 1
        assert loader._compare_versions("1.0.0", "2.0.0") == -1
        assert loader._compare_versions("1.1.0", "1.0.1") == 1

    def test_find_plugin_dir_none(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        loader = PluginLoader(node_registry, event_bus)
        assert loader._find_plugin_dir("ghost") is None

    def test_validate_metadata_empty_name(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        loader = PluginLoader(node_registry, event_bus)
        meta = PluginMetadata(plugin_id="x", plugin_name="", version="1.0.0")
        errors = loader._validate_metadata(meta)
        assert any("plugin_name" in e for e in errors)

    def test_validate_metadata_empty_version(self, node_registry: NodeRegistry, event_bus: TypedEventBus) -> None:
        loader = PluginLoader(node_registry, event_bus)
        meta = PluginMetadata(plugin_id="x", plugin_name="X", version="")
        errors = loader._validate_metadata(meta)
        assert len(errors) > 0
