"""插件加载集成测试 — 扫描→加载→注册→执行 完整流程。

参考: 13_风险与验证策略.md §5.3
验收标准:
- PluginLoader.scan() 发现所有内置插件
- PluginLoader.load_all() 按依赖顺序加载
- 节点注册到 NodeRegistry 且带命名空间前缀
- 注册的描述符可通过 NodeRegistry.get() 获取并实例化执行
- 错误隔离: 单个插件失败不影响其他插件
- 卸载后节点从注册表移除
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from src.core.engine.execution_context import ExecutionContext
from src.core.engine.node_descriptor import NodeDescriptor
from src.core.engine.node_registry import NodeRegistry
from src.core.engine.node_result import NodeResult
from src.core.events.bus import TypedEventBus
from src.core.plugins.plugin_context import PluginContext
from src.core.plugins.plugin_interface import PluginInterface, PluginMetadata
from src.core.plugins.plugin_loader import PluginLoader, PluginState
from src.core.plugins.plugin_node_registry import PluginNodeRegistry
from src.core.variables.pool import VariablePool


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture(autouse=True)
def _clear_registry():
    NodeRegistry.clear()
    yield
    NodeRegistry.clear()


@pytest.fixture
def node_registry() -> NodeRegistry:
    return NodeRegistry()


@pytest.fixture
def event_bus() -> TypedEventBus:
    return TypedEventBus()


@pytest.fixture
def mock_capture():
    from src.core.vision import ScreenCapture

    cap = MagicMock(spec=ScreenCapture)
    cap.grab.return_value = np.zeros((1080, 1920, 3), dtype=np.uint8)
    cap.to_logical.side_effect = lambda x, y: (x, y)
    return cap


@pytest.fixture
def mock_matcher():
    from src.core.vision import TemplateMatcher

    m = MagicMock(spec=TemplateMatcher)
    m.find.return_value = None
    m.find_all.return_value = []
    return m


@pytest.fixture
def mock_input():
    from src.core.input import InputController

    ctrl = MagicMock(spec=InputController)
    return ctrl


def _make_plugin_loader(
    node_registry: NodeRegistry,
    event_bus: TypedEventBus,
    mock_capture=None,
    mock_matcher=None,
    mock_input=None,
) -> PluginLoader:
    return PluginLoader(
        node_registry=node_registry,
        event_bus=event_bus,
        screen_capture=mock_capture,
        template_matcher=mock_matcher,
        input_controller=mock_input,
    )


# ============================================================
# 1. 扫描 → 发现
# ============================================================


class TestPluginScanning:
    """PluginLoader.scan() 发现所有内置插件。"""

    def test_scan_discovers_all_builtins(
        self, node_registry: NodeRegistry, event_bus: TypedEventBus,
    ) -> None:
        loader = _make_plugin_loader(node_registry, event_bus)
        loader.add_scan_dir("src/plugins/builtin")
        discovered = loader.scan()

        assert "combat" in discovered
        assert "navigation" in discovered
        assert "task" in discovered
        assert len(discovered) == 3

    def test_scan_skips_non_plugin_dirs(
        self, node_registry: NodeRegistry, event_bus: TypedEventBus,
        tmp_path: Path,
    ) -> None:
        (tmp_path / "not_a_plugin").mkdir()
        (tmp_path / "not_a_plugin" / "some_file.txt").write_text("hello")

        (tmp_path / "real_plugin").mkdir()
        (tmp_path / "real_plugin" / "plugin.json").write_text(json.dumps({
            "plugin_id": "real",
            "plugin_name": "Real",
            "version": "1.0.0",
            "entry_class": "RealPlugin",
        }))
        (tmp_path / "real_plugin" / "__init__.py").write_text(
            "from src.core.plugins.plugin_interface import PluginInterface, PluginMetadata\n"
            "class RealPlugin(PluginInterface):\n"
            "    def get_metadata(self): return PluginMetadata("
            "plugin_id='real', plugin_name='Real', version='1.0.0')\n"
            "    def on_load(self, ctx): pass\n"
            "    def on_unload(self): pass\n"
            "    def register_nodes(self, reg): pass\n"
        )

        loader = _make_plugin_loader(node_registry, event_bus)
        loader.add_scan_dir(tmp_path)
        discovered = loader.scan()

        assert "real_plugin" in discovered
        assert "not_a_plugin" not in discovered

    def test_scan_idempotent(
        self, node_registry: NodeRegistry, event_bus: TypedEventBus,
    ) -> None:
        loader = _make_plugin_loader(node_registry, event_bus)
        loader.add_scan_dir("src/plugins/builtin")

        first = loader.scan()
        second = loader.scan()

        assert first == ["combat", "navigation", "task"]
        assert second == []

    def test_scan_invalid_manifest_skipped(
        self, node_registry: NodeRegistry, event_bus: TypedEventBus,
        tmp_path: Path,
    ) -> None:
        bad_dir = tmp_path / "bad_plugin"
        bad_dir.mkdir()
        (bad_dir / "plugin.json").write_text("{ invalid json")

        loader = _make_plugin_loader(node_registry, event_bus)
        loader.add_scan_dir(tmp_path)
        discovered = loader.scan()

        assert "bad_plugin" not in discovered


# ============================================================
# 2. 加载 → 注册
# ============================================================


class TestPluginLoading:
    """PluginLoader.load_all() 按依赖顺序加载并注册节点。"""

    def test_load_all_succeeds(
        self, node_registry: NodeRegistry, event_bus: TypedEventBus,
    ) -> None:
        loader = _make_plugin_loader(node_registry, event_bus)
        loader.add_scan_dir("src/plugins/builtin")
        loader.scan()

        loaded, failed = loader.load_all()
        assert sorted(loaded) == ["combat", "navigation", "task"]
        assert failed == []

    def test_dependency_order_respected(
        self, node_registry: NodeRegistry, event_bus: TypedEventBus,
    ) -> None:
        loader = _make_plugin_loader(node_registry, event_bus)
        loader.add_scan_dir("src/plugins/builtin")
        loader.scan()

        sorted_ids = loader._topological_sort()
        assert sorted_ids.index("combat") < sorted_ids.index("navigation")
        assert sorted_ids.index("navigation") < sorted_ids.index("task")

    def test_nodes_registered_with_namespace(
        self, node_registry: NodeRegistry, event_bus: TypedEventBus,
    ) -> None:
        loader = _make_plugin_loader(node_registry, event_bus)
        loader.add_scan_dir("src/plugins/builtin")
        loader.scan()
        loader.load_all()

        assert node_registry.has("combat.find_enemy")
        assert node_registry.has("combat.attack")
        assert node_registry.has("combat.use_skill")
        assert node_registry.has("combat.dodge")
        assert node_registry.has("combat.target_select")

        assert node_registry.has("navigation.move_to")
        assert node_registry.has("navigation.path_navigate")
        assert node_registry.has("navigation.zone_switch")
        assert node_registry.has("navigation.teleport")
        assert node_registry.has("navigation.path_follow")

        assert node_registry.has("task.accept_quest")
        assert node_registry.has("task.dialog_interact")
        assert node_registry.has("task.complete_quest")
        assert node_registry.has("task.daily_reset")

    def test_registered_descriptors_are_subclasses(
        self, node_registry: NodeRegistry, event_bus: TypedEventBus,
    ) -> None:
        loader = _make_plugin_loader(node_registry, event_bus)
        loader.add_scan_dir("src/plugins/builtin")
        loader.scan()
        loader.load_all()

        for type_key in [
            "combat.find_enemy",
            "navigation.move_to",
            "task.accept_quest",
        ]:
            desc_cls = node_registry.get(type_key)
            assert issubclass(desc_cls, NodeDescriptor)

    def test_plugin_state_after_load(
        self, node_registry: NodeRegistry, event_bus: TypedEventBus,
    ) -> None:
        loader = _make_plugin_loader(node_registry, event_bus)
        loader.add_scan_dir("src/plugins/builtin")
        loader.scan()
        loader.load_all()

        for plugin_id in ("combat", "navigation", "task"):
            entry = loader.get_plugin(plugin_id)
            assert entry is not None
            assert entry.state == PluginState.LOADED
            assert entry.instance is not None
            assert isinstance(entry.instance, PluginInterface)
            assert entry.load_time > 0
            assert entry.error_message is None

    def test_load_without_dependency_fails(
        self, node_registry: NodeRegistry, event_bus: TypedEventBus,
    ) -> None:
        loader = _make_plugin_loader(node_registry, event_bus)
        loader.add_scan_dir("src/plugins/builtin")
        loader.scan()

        with pytest.raises(RuntimeError, match="缺少依赖"):
            loader.load("navigation")


# ============================================================
# 3. 注册 → 执行
# ============================================================


class TestPluginDescriptorExecution:
    """已注册的描述符可通过 NodeRegistry 获取并实例化执行。"""

    def _make_ctx(
        self,
        action: MagicMock,
        capture: MagicMock,
        matcher: MagicMock,
        input_ctrl: MagicMock,
    ) -> ExecutionContext:
        from src.core.flow import FlowGraph, FlowNode, NodeType

        graph = FlowGraph(name="plugin_test", start_node_id="start")
        graph.add_node(FlowNode(node_id="start", node_type=NodeType.START))

        current = FlowNode(node_id="n1", node_type=NodeType.ACTION, action=action)
        graph.add_node(current)

        return ExecutionContext(
            graph=graph,
            current_node=current,
            variables=VariablePool(),
            capture=capture,
            matcher=matcher,
            input_ctrl=input_ctrl,
            gen=0,
            stop_event=threading.Event(),
            pause_event=threading.Event(),
            event_bus=None,
        )

    def test_find_enemy_found(
        self,
        node_registry: NodeRegistry,
        event_bus: TypedEventBus,
        mock_capture: MagicMock,
        mock_matcher: MagicMock,
        mock_input: MagicMock,
    ) -> None:
        loader = _make_plugin_loader(
            node_registry, event_bus, mock_capture, mock_matcher, mock_input,
        )
        loader.add_scan_dir("src/plugins/builtin")
        loader.scan()
        loader.load_all()

        mock_matcher.find.return_value = (100, 200, 50, 60)
        action = MagicMock()
        action.template_path = "enemy.png"
        action.confidence = 0.7

        desc_cls = node_registry.get("combat.find_enemy")
        desc = desc_cls()
        ctx = self._make_ctx(action, mock_capture, mock_matcher, mock_input)
        result = desc.execute(ctx)

        assert result.success is True
        assert result.output_vars["enemy_found"] is True
        assert result.output_vars["enemy_pos"] == (125, 230)

    def test_find_enemy_not_found(
        self,
        node_registry: NodeRegistry,
        event_bus: TypedEventBus,
        mock_capture: MagicMock,
        mock_matcher: MagicMock,
        mock_input: MagicMock,
    ) -> None:
        loader = _make_plugin_loader(
            node_registry, event_bus, mock_capture, mock_matcher, mock_input,
        )
        loader.add_scan_dir("src/plugins/builtin")
        loader.scan()
        loader.load_all()

        mock_matcher.find.return_value = None
        action = MagicMock()
        action.template_path = "enemy.png"
        action.confidence = 0.7

        desc_cls = node_registry.get("combat.find_enemy")
        desc = desc_cls()
        ctx = self._make_ctx(action, mock_capture, mock_matcher, mock_input)
        result = desc.execute(ctx)

        assert result.success is True
        assert result.output_vars["enemy_found"] is False

    def test_attack_executes(
        self,
        node_registry: NodeRegistry,
        event_bus: TypedEventBus,
        mock_capture: MagicMock,
        mock_matcher: MagicMock,
        mock_input: MagicMock,
    ) -> None:
        loader = _make_plugin_loader(
            node_registry, event_bus, mock_capture, mock_matcher, mock_input,
        )
        loader.add_scan_dir("src/plugins/builtin")
        loader.scan()
        loader.load_all()

        action = MagicMock()
        action.target_pos = (300, 400)
        action.attack_count = 2

        desc_cls = node_registry.get("combat.attack")
        desc = desc_cls()
        ctx = self._make_ctx(action, mock_capture, mock_matcher, mock_input)
        result = desc.execute(ctx)

        assert result.success is True
        mock_input.click.assert_called_once()
        assert mock_input.press_key.call_count == 2

    def test_move_to_executes(
        self,
        node_registry: NodeRegistry,
        event_bus: TypedEventBus,
        mock_capture: MagicMock,
        mock_matcher: MagicMock,
        mock_input: MagicMock,
    ) -> None:
        loader = _make_plugin_loader(
            node_registry, event_bus, mock_capture, mock_matcher, mock_input,
        )
        loader.add_scan_dir("src/plugins/builtin")
        loader.scan()
        loader.load_all()

        action = MagicMock()
        action.target_pos = (500, 600)

        desc_cls = node_registry.get("navigation.move_to")
        desc = desc_cls()
        ctx = self._make_ctx(action, mock_capture, mock_matcher, mock_input)
        result = desc.execute(ctx)

        assert result.success is True
        assert result.output_vars["arrived"] is True
        mock_input.click.assert_called_once_with(500, 600, button="left", clicks=1)

    def test_daily_reset_executes(
        self,
        node_registry: NodeRegistry,
        event_bus: TypedEventBus,
        mock_capture: MagicMock,
        mock_matcher: MagicMock,
        mock_input: MagicMock,
    ) -> None:
        loader = _make_plugin_loader(
            node_registry, event_bus, mock_capture, mock_matcher, mock_input,
        )
        loader.add_scan_dir("src/plugins/builtin")
        loader.scan()
        loader.load_all()

        action = MagicMock()
        action.reset_time = "99:99"

        desc_cls = node_registry.get("task.daily_reset")
        desc = desc_cls()
        ctx = self._make_ctx(action, mock_capture, mock_matcher, mock_input)
        result = desc.execute(ctx)

        assert result.success is False
        assert "时间格式错误" in str(result.error)


# ============================================================
# 4. 卸载
# ============================================================


class TestPluginUnloading:
    """卸载后节点从注册表移除，插件状态变为 UNLOADED。"""

    def test_unload_removes_nodes(
        self, node_registry: NodeRegistry, event_bus: TypedEventBus,
    ) -> None:
        loader = _make_plugin_loader(node_registry, event_bus)
        loader.add_scan_dir("src/plugins/builtin")
        loader.scan()
        loader.load_all()

        assert node_registry.has("task.accept_quest")
        loader.unload("task")
        assert not node_registry.has("task.accept_quest")
        assert node_registry.has("combat.find_enemy")

    def test_unload_changes_state(
        self, node_registry: NodeRegistry, event_bus: TypedEventBus,
    ) -> None:
        loader = _make_plugin_loader(node_registry, event_bus)
        loader.add_scan_dir("src/plugins/builtin")
        loader.scan()
        loader.load_all()

        loader.unload("combat")
        entry = loader.get_plugin("combat")
        assert entry.state == PluginState.UNLOADED
        assert entry.instance is None
        assert entry.context is None

    def test_unload_all_reverses_order(
        self, node_registry: NodeRegistry, event_bus: TypedEventBus,
    ) -> None:
        loader = _make_plugin_loader(node_registry, event_bus)
        loader.add_scan_dir("src/plugins/builtin")
        loader.scan()
        loader.load_all()

        unloaded = loader.unload_all()
        assert len(unloaded) == 3
        assert node_registry.all_types() == []

    def test_reload_plugin(
        self, node_registry: NodeRegistry, event_bus: TypedEventBus,
    ) -> None:
        loader = _make_plugin_loader(node_registry, event_bus)
        loader.add_scan_dir("src/plugins/builtin")
        loader.scan()
        loader.load_all()

        loader.unload("combat")
        assert not node_registry.has("combat.find_enemy")

        loader.reload("combat")
        assert node_registry.has("combat.find_enemy")
        entry = loader.get_plugin("combat")
        assert entry.state == PluginState.LOADED


# ============================================================
# 5. 错误隔离
# ============================================================


class TestPluginErrorIsolation:
    """单个插件失败不影响其他插件。"""

    def test_bad_manifest_skipped(
        self,
        node_registry: NodeRegistry,
        event_bus: TypedEventBus,
        tmp_path: Path,
    ) -> None:
        bad_dir = tmp_path / "bad"
        bad_dir.mkdir()
        (bad_dir / "plugin.json").write_text(json.dumps({
            "plugin_id": "",
            "plugin_name": "",
            "version": "not.semver",
            "entry_class": "Bad",
        }))

        loader = _make_plugin_loader(node_registry, event_bus)
        loader.add_scan_dir("src/plugins/builtin")
        loader.add_scan_dir(tmp_path)
        discovered = loader.scan()

        assert "bad" not in discovered
        assert "combat" in discovered

    def test_load_failure_isolated(
        self,
        node_registry: NodeRegistry,
        event_bus: TypedEventBus,
        tmp_path: Path,
    ) -> None:
        fail_dir = tmp_path / "fail_plugin"
        fail_dir.mkdir()
        (fail_dir / "plugin.json").write_text(json.dumps({
            "plugin_id": "fail",
            "plugin_name": "Fail",
            "version": "1.0.0",
            "entry_class": "FailPlugin",
            "dependencies": [],
        }))
        (fail_dir / "__init__.py").write_text(
            "raise ImportError('intentional fail')\n"
        )

        loader = _make_plugin_loader(node_registry, event_bus)
        loader.add_scan_dir("src/plugins/builtin")
        loader.add_scan_dir(tmp_path)
        loader.scan()

        loaded, failed = loader.load_all()
        assert "combat" in loaded
        assert "fail_plugin" in failed


# ============================================================
# 6. 临时插件 — 完整生命周期
# ============================================================


class TestCustomPluginLifecycle:
    """使用临时插件目录验证完整生命周期。"""

    def test_custom_plugin_scan_load_execute_unload(
        self,
        node_registry: NodeRegistry,
        event_bus: TypedEventBus,
        mock_capture: MagicMock,
        mock_matcher: MagicMock,
        mock_input: MagicMock,
        tmp_path: Path,
    ) -> None:
        plugin_dir = tmp_path / "echo"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(json.dumps({
            "plugin_id": "echo",
            "plugin_name": "Echo",
            "version": "1.0.0",
            "entry_class": "EchoPlugin",
            "dependencies": [],
            "permissions": ["input_control"],
        }))
        (plugin_dir / "__init__.py").write_text(
            "from src.core.plugins.plugin_interface import PluginInterface, PluginMetadata\n"
            "from src.core.plugins.plugin_node_registry import PluginNodeRegistry\n"
            "from src.core.engine.node_descriptor import NodeDescriptor, PortDef\n"
            "from src.core.engine.node_result import NodeResult\n"
            "from src.core.engine.execution_context import ExecutionContext\n"
            "\n"
            "class EchoDescriptor(NodeDescriptor):\n"
            "    @classmethod\n"
            "    def action_type(cls): return 'echo'\n"
            "    @classmethod\n"
            "    def display_name(cls): return 'Echo'\n"
            "    @classmethod\n"
            "    def category(cls): return 'Test'\n"
            "    @classmethod\n"
            "    def input_types(cls): return {}\n"
            "    @classmethod\n"
            "    def output_types(cls): return {}\n"
            "    def execute(self, ctx):\n"
            "        action = ctx.current_node.action\n"
            "        ctx.input_ctrl.click(action.x, action.y, button='left', clicks=1)\n"
            "        return NodeResult.ok(clicked=True)\n"
            "\n"
            "class EchoPlugin(PluginInterface):\n"
            "    def get_metadata(self):\n"
            "        return PluginMetadata(\n"
            "            plugin_id='echo', plugin_name='Echo', version='1.0.0'\n"
            "        )\n"
            "    def on_load(self, ctx): pass\n"
            "    def on_unload(self): pass\n"
            "    def register_nodes(self, reg):\n"
            "        reg.register(EchoDescriptor)\n"
        )

        loader = _make_plugin_loader(
            node_registry, event_bus, mock_capture, mock_matcher, mock_input,
        )
        loader.add_scan_dir(tmp_path)
        discovered = loader.scan()
        assert "echo" in discovered

        loaded, failed = loader.load_all()
        assert "echo" in loaded
        assert failed == []

        assert node_registry.has("echo.echo")
        desc_cls = node_registry.get("echo.echo")
        desc = desc_cls()

        from src.core.flow import FlowGraph, FlowNode, NodeType

        graph = FlowGraph(name="echo_test", start_node_id="start")
        graph.add_node(FlowNode(node_id="start", node_type=NodeType.START))
        action = MagicMock()
        action.x = 42
        action.y = 99
        current = FlowNode(node_id="n1", node_type=NodeType.ACTION, action=action)
        graph.add_node(current)
        ctx = ExecutionContext(
            graph=graph, current_node=current, variables=VariablePool(),
            capture=mock_capture, matcher=mock_matcher, input_ctrl=mock_input,
            gen=0, stop_event=threading.Event(), pause_event=threading.Event(),
            event_bus=None,
        )
        result = desc.execute(ctx)
        assert result.success is True
        assert result.output_vars["clicked"] is True
        mock_input.click.assert_called_once_with(42, 99, button="left", clicks=1)

        loader.unload("echo")
        assert not node_registry.has("echo.echo")
