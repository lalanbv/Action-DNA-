"""插件加载器与描述符注册测试 — 覆盖 NavigationPlugin、TaskPlugin 的元数据、
节点注册、描述符端口定义、PluginLoader 的完整扫描-加载-查询-卸载流程。"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.core.engine.node_registry import NodeRegistry
from src.core.events.bus import TypedEventBus
from src.core.plugins.plugin_context import PluginContext
from src.core.plugins.plugin_interface import PluginInterface
from src.core.plugins.plugin_loader import PluginLoader, PluginState


# ---- Fixtures ----


@pytest.fixture
def node_registry() -> NodeRegistry:
    NodeRegistry.clear()
    return NodeRegistry()


@pytest.fixture
def event_bus() -> TypedEventBus:
    return TypedEventBus()


def _make_context(
    plugin_id: str,
    node_registry: NodeRegistry,
    event_bus: TypedEventBus,
    permissions: set[str] | None = None,
) -> PluginContext:
    return PluginContext(
        plugin_id=plugin_id,
        node_registry=node_registry,
        event_bus=event_bus,
        permissions=permissions or {"events", "screen_capture", "template_matcher", "input_control"},
    )


# ============================================================================
# NavigationPlugin
# ============================================================================


class TestNavigationPlugin:
    """NavigationPlugin 元数据与节点注册。"""

    def test_metadata(self) -> None:
        from src.plugins.builtin.navigation import NavigationPlugin

        plugin = NavigationPlugin()
        meta = plugin.get_metadata()
        assert meta.plugin_id == "navigation"
        assert meta.plugin_name == "地图导航"
        assert meta.version == "1.0.0"
        assert "combat" in meta.dependencies
        assert "screen_capture" in meta.permissions
        assert "input_control" in meta.permissions

    def test_register_nodes(
        self, node_registry: NodeRegistry, event_bus: TypedEventBus,
    ) -> None:
        from src.plugins.builtin.navigation import NavigationPlugin

        plugin = NavigationPlugin()
        ctx = _make_context("navigation", node_registry, event_bus)
        plugin.register_nodes(ctx.registry)

        expected = [
            "navigation.move_to",
            "navigation.path_navigate",
            "navigation.zone_switch",
            "navigation.teleport",
            "navigation.path_follow",
        ]
        for key in expected:
            assert node_registry.has(key), f"Missing: {key}"
        assert ctx.registered_types == expected

    def test_move_to_descriptor_ports(self) -> None:
        from src.plugins.builtin.navigation import MoveToDescriptor

        inputs = MoveToDescriptor.input_types()
        assert "target_pos" in inputs
        assert inputs["target_pos"].required is True

        outputs = MoveToDescriptor.output_types()
        assert "arrived" in outputs

    def test_path_navigate_descriptor_ports(self) -> None:
        from src.plugins.builtin.navigation import PathNavigateDescriptor

        inputs = PathNavigateDescriptor.input_types()
        assert "waypoints" in inputs
        assert inputs["waypoints"].required is True
        assert "interrupt_template" in inputs
        assert inputs["step_delay"].default == 1.0

        outputs = PathNavigateDescriptor.output_types()
        assert "completed" in outputs
        assert "interrupted" in outputs
        assert "reached_index" in outputs

    def test_zone_switch_descriptor_ports(self) -> None:
        from src.plugins.builtin.navigation import ZoneSwitchDescriptor

        inputs = ZoneSwitchDescriptor.input_types()
        assert "zone_template" in inputs
        assert inputs["zone_template"].required is True
        assert "wait_after_switch" in inputs
        assert inputs["wait_after_switch"].default == 3.0

        outputs = ZoneSwitchDescriptor.output_types()
        assert "switched" in outputs

    def test_teleport_descriptor_ports(self) -> None:
        from src.plugins.builtin.navigation import TeleportDescriptor

        inputs = TeleportDescriptor.input_types()
        assert "map_template" in inputs
        assert "confirm_button" in inputs

        outputs = TeleportDescriptor.output_types()
        assert "teleported" in outputs

    def test_path_follow_descriptor_ports(self) -> None:
        from src.plugins.builtin.navigation import PathFollowDescriptor

        inputs = PathFollowDescriptor.input_types()
        assert "waypoints" in inputs
        assert inputs["waypoints"].required is True

        outputs = PathFollowDescriptor.output_types()
        assert "completed" in outputs


# ============================================================================
# TaskPlugin
# ============================================================================


class TestTaskPlugin:
    """TaskPlugin 元数据与节点注册。"""

    def test_metadata(self) -> None:
        from src.plugins.builtin.task import TaskPlugin

        plugin = TaskPlugin()
        meta = plugin.get_metadata()
        assert meta.plugin_id == "task"
        assert meta.plugin_name == "任务自动化"
        assert meta.version == "1.0.0"
        assert "navigation" in meta.dependencies

    def test_register_nodes(
        self, node_registry: NodeRegistry, event_bus: TypedEventBus,
    ) -> None:
        from src.plugins.builtin.task import TaskPlugin

        plugin = TaskPlugin()
        ctx = _make_context("task", node_registry, event_bus)
        plugin.register_nodes(ctx.registry)

        expected = [
            "task.accept_quest",
            "task.dialog_interact",
            "task.complete_quest",
            "task.daily_reset",
        ]
        for key in expected:
            assert node_registry.has(key), f"Missing: {key}"
        assert ctx.registered_types == expected

    def test_quest_accept_descriptor_ports(self) -> None:
        from src.plugins.builtin.task import QuestAcceptDescriptor

        inputs = QuestAcceptDescriptor.input_types()
        assert "quest_npc_template" in inputs
        assert inputs["quest_npc_template"].required is True

        outputs = QuestAcceptDescriptor.output_types()
        assert "accepted" in outputs

    def test_dialog_interact_descriptor_ports(self) -> None:
        from src.plugins.builtin.task import DialogInteractDescriptor

        inputs = DialogInteractDescriptor.input_types()
        assert "rounds" in inputs
        assert inputs["rounds"].default == 1
        assert "option_round" in inputs
        assert inputs["option_round"].default == 0
        assert "round_delay" in inputs
        assert inputs["round_delay"].default == 1.0

        outputs = DialogInteractDescriptor.output_types()
        assert "completed" in outputs
        assert "option_selected" in outputs

    def test_complete_quest_descriptor_ports(self) -> None:
        from src.plugins.builtin.task import CompleteQuestDescriptor

        inputs = CompleteQuestDescriptor.input_types()
        assert "npc_template" in inputs
        assert inputs["npc_template"].required is True

        outputs = CompleteQuestDescriptor.output_types()
        assert "completed" in outputs

    def test_daily_reset_descriptor_ports(self) -> None:
        from src.plugins.builtin.task import DailyResetDescriptor

        inputs = DailyResetDescriptor.input_types()
        assert "reset_time" in inputs
        assert inputs["reset_time"].default == "04:00"

        outputs = DailyResetDescriptor.output_types()
        assert "should_reset" in outputs


# ============================================================================
# PluginLoader — 完整流程（扫描 → 加载 → 查询 → 卸载）
# ============================================================================


class TestPluginLoaderFullFlow:
    """PluginLoader 完整生命周期测试。"""

    def test_scan_discovers_builtin_plugins(
        self, node_registry: NodeRegistry, event_bus: TypedEventBus,
    ) -> None:
        loader = PluginLoader(node_registry, event_bus)
        loader.add_scan_dir("src/plugins/builtin")
        discovered = loader.scan()
        assert "combat" in discovered
        assert "navigation" in discovered
        assert "task" in discovered

    def test_load_all_with_dependencies(
        self, node_registry: NodeRegistry, event_bus: TypedEventBus,
    ) -> None:
        loader = PluginLoader(node_registry, event_bus)
        loader.add_scan_dir("src/plugins/builtin")
        loader.scan()

        loaded, failed = loader.load_all()
        assert "combat" in loaded
        assert "navigation" in loaded
        assert "task" in loaded
        assert len(failed) == 0

    def test_loaded_plugins_have_correct_state(
        self, node_registry: NodeRegistry, event_bus: TypedEventBus,
    ) -> None:
        loader = PluginLoader(node_registry, event_bus)
        loader.add_scan_dir("src/plugins/builtin")
        loader.scan()
        loader.load_all()

        for plugin_id in ("combat", "navigation", "task"):
            entry = loader.get_plugin(plugin_id)
            assert entry is not None
            assert entry.state == PluginState.LOADED
            assert entry.instance is not None
            assert isinstance(entry.instance, PluginInterface)

    def test_nodes_registered_with_namespace(
        self, node_registry: NodeRegistry, event_bus: TypedEventBus,
    ) -> None:
        loader = PluginLoader(node_registry, event_bus)
        loader.add_scan_dir("src/plugins/builtin")
        loader.scan()
        loader.load_all()

        assert node_registry.has("combat.find_enemy")
        assert node_registry.has("navigation.path_navigate")
        assert node_registry.has("task.accept_quest")

    def test_unload_removes_nodes(
        self, node_registry: NodeRegistry, event_bus: TypedEventBus,
    ) -> None:
        loader = PluginLoader(node_registry, event_bus)
        loader.add_scan_dir("src/plugins/builtin")
        loader.scan()
        loader.load_all()

        loader.unload("task")
        assert not node_registry.has("task.accept_quest")
        assert node_registry.has("combat.find_enemy")

    def test_unload_all_reverses_order(
        self, node_registry: NodeRegistry, event_bus: TypedEventBus,
    ) -> None:
        loader = PluginLoader(node_registry, event_bus)
        loader.add_scan_dir("src/plugins/builtin")
        loader.scan()
        loader.load_all()

        unloaded = loader.unload_all()
        assert len(unloaded) == 3
        for plugin_id in ("combat", "navigation", "task"):
            entry = loader.get_plugin(plugin_id)
            assert entry.state == PluginState.UNLOADED

    def test_get_all_plugins(
        self, node_registry: NodeRegistry, event_bus: TypedEventBus,
    ) -> None:
        loader = PluginLoader(node_registry, event_bus)
        loader.add_scan_dir("src/plugins/builtin")
        loader.scan()

        all_plugins = loader.get_all_plugins()
        assert len(all_plugins) == 3
        assert "combat" in all_plugins
        assert "navigation" in all_plugins
        assert "task" in all_plugins

    def test_get_loaded_plugins_filters(
        self, node_registry: NodeRegistry, event_bus: TypedEventBus,
    ) -> None:
        loader = PluginLoader(node_registry, event_bus)
        loader.add_scan_dir("src/plugins/builtin")
        loader.scan()
        loader.load_all()

        loaded = loader.get_loaded_plugins()
        assert len(loaded) == 3

        loader.unload("task")
        loaded = loader.get_loaded_plugins()
        assert "task" not in loaded
        assert "combat" in loaded

    def test_reload_plugin(
        self, node_registry: NodeRegistry, event_bus: TypedEventBus,
    ) -> None:
        loader = PluginLoader(node_registry, event_bus)
        loader.add_scan_dir("src/plugins/builtin")
        loader.scan()
        loader.load_all()

        loader.reload("combat")
        entry = loader.get_plugin("combat")
        assert entry.state == PluginState.LOADED
        assert node_registry.has("combat.find_enemy")

    def test_load_fails_without_dependencies(
        self, node_registry: NodeRegistry, event_bus: TypedEventBus,
    ) -> None:
        loader = PluginLoader(node_registry, event_bus)
        loader.add_scan_dir("src/plugins/builtin")
        loader.scan()

        with pytest.raises(RuntimeError, match="缺少依赖"):
            loader.load("navigation")

    def test_plugin_manifest_json_valid(self) -> None:
        """验证内置插件的 plugin.json 格式正确。"""
        for plugin_dir in Path("src/plugins/builtin").iterdir():
            if not plugin_dir.is_dir():
                continue
            manifest_path = plugin_dir / "plugin.json"
            if not manifest_path.exists():
                continue

            with open(manifest_path, encoding="utf-8") as f:
                data = json.load(f)

            assert "plugin_id" in data
            assert "plugin_name" in data
            assert "version" in data
            assert "entry_class" in data
            assert data["plugin_id"] == plugin_dir.name
            parts = data["version"].split(".")
            assert len(parts) == 3 and all(p.isdigit() for p in parts)
