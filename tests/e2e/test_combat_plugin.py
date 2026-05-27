"""CombatPlugin 端到端测试 — 完整战斗流程: 加载→找怪→攻击→技能→闪避→选怪。

参考: 13_风险与验证策略.md §5.4
验收标准:
- 加载 CombatPlugin 后所有战斗描述符可用
- FindEnemyDescriptor → 查找敌人并输出位置
- AttackDescriptor → 点击目标 + 攻击连击
- UseSkillDescriptor → 释放技能按键
- DodgeDescriptor → 方向闪避
- TargetSelectionDescriptor → 多目标选优
- 完整战斗循环: find_enemy → attack → use_skill → dodge
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

import numpy as np
import pytest

from src.core.engine.execution_context import ExecutionContext
from src.core.engine.node_descriptor import NodeDescriptor
from src.core.engine.node_registry import NodeRegistry
from src.core.engine.node_result import NodeResult
from src.core.events.bus import TypedEventBus
from src.core.flow import FlowEdge, FlowGraph, FlowNode, NodeType
from src.core.plugins.plugin_loader import PluginLoader, PluginState
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


@pytest.fixture
def _loaded_plugins(
    node_registry: NodeRegistry,
    event_bus: TypedEventBus,
    mock_capture: MagicMock,
    mock_matcher: MagicMock,
    mock_input: MagicMock,
) -> None:
    """加载所有内置插件，使描述符可通过 NodeRegistry 访问。"""
    loader = PluginLoader(
        node_registry=node_registry,
        event_bus=event_bus,
        screen_capture=mock_capture,
        template_matcher=mock_matcher,
        input_controller=mock_input,
    )
    loader.add_scan_dir("src/plugins/builtin")
    loader.scan()
    loaded, failed = loader.load_all()
    assert "combat" in loaded
    assert failed == []


@pytest.fixture
def loader(
    node_registry: NodeRegistry,
    event_bus: TypedEventBus,
    mock_capture: MagicMock,
    mock_matcher: MagicMock,
    mock_input: MagicMock,
) -> PluginLoader:
    _loader = PluginLoader(
        node_registry=node_registry,
        event_bus=event_bus,
        screen_capture=mock_capture,
        template_matcher=mock_matcher,
        input_controller=mock_input,
    )
    _loader.add_scan_dir("src/plugins/builtin")
    _loader.scan()
    loaded, failed = _loader.load_all()
    assert "combat" in loaded
    assert failed == []
    return _loader


def _make_ctx(
    action: MagicMock,
    capture: MagicMock,
    matcher: MagicMock,
    input_ctrl: MagicMock,
    variables: VariablePool | None = None,
) -> ExecutionContext:
    graph = FlowGraph(name="combat_e2e", start_node_id="start")
    graph.add_node(FlowNode(node_id="start", node_type=NodeType.START))
    current = FlowNode(node_id="n1", node_type=NodeType.ACTION, action=action)
    graph.add_node(current)
    graph.add_edge(FlowEdge(
        edge_id="e_start_n1", from_node="start", to_node="n1",
    ))
    return ExecutionContext(
        graph=graph,
        current_node=current,
        variables=variables or VariablePool(),
        capture=capture,
        matcher=matcher,
        input_ctrl=input_ctrl,
        gen=0,
        stop_event=threading.Event(),
        pause_event=threading.Event(),
        event_bus=None,
    )


# ============================================================
# 1. FindEnemyDescriptor — 查找敌人
# ============================================================


class TestFindEnemyE2E:
    """FindEnemyDescriptor E2E: 找到敌人输出位置，未找到标记 False。"""

    @pytest.fixture(autouse=True)
    def _setup(self, _loaded_plugins):
        pass

    def test_enemy_found_outputs_position(
        self, node_registry: NodeRegistry,
        mock_capture: MagicMock, mock_matcher: MagicMock, mock_input: MagicMock,
    ) -> None:
        mock_matcher.find.return_value = (200, 300, 80, 100)
        action = MagicMock()
        action.template_path = "enemy.png"
        action.confidence = 0.8

        desc_cls = node_registry.get("combat.find_enemy")
        desc = desc_cls()
        ctx = _make_ctx(action, mock_capture, mock_matcher, mock_input)
        result = desc.execute(ctx)

        assert result.success is True
        assert result.output_vars["enemy_found"] is True
        assert result.output_vars["enemy_pos"] == (240, 350)
        mock_matcher.find.assert_called_once()

    def test_enemy_not_found(
        self, node_registry: NodeRegistry,
        mock_capture: MagicMock, mock_matcher: MagicMock, mock_input: MagicMock,
    ) -> None:
        mock_matcher.find.return_value = None
        action = MagicMock()
        action.template_path = "enemy.png"
        action.confidence = 0.8

        desc_cls = node_registry.get("combat.find_enemy")
        desc = desc_cls()
        ctx = _make_ctx(action, mock_capture, mock_matcher, mock_input)
        result = desc.execute(ctx)

        assert result.success is True
        assert result.output_vars["enemy_found"] is False

    def test_grabs_screenshot(
        self, node_registry: NodeRegistry,
        mock_capture: MagicMock, mock_matcher: MagicMock, mock_input: MagicMock,
    ) -> None:
        mock_matcher.find.return_value = (100, 200, 50, 60)
        action = MagicMock()
        action.template_path = "enemy.png"

        desc_cls = node_registry.get("combat.find_enemy")
        desc = desc_cls()
        ctx = _make_ctx(action, mock_capture, mock_matcher, mock_input)
        desc.execute(ctx)

        mock_capture.grab.assert_called_once()


# ============================================================
# 2. AttackDescriptor — 攻击
# ============================================================


class TestAttackE2E:
    """AttackDescriptor E2E: 点击目标 + 按键连击。"""

    @pytest.fixture(autouse=True)
    def _setup(self, _loaded_plugins):
        pass

    def test_attack_with_target_clicks_and_presses(
        self, node_registry: NodeRegistry,
        mock_capture: MagicMock, mock_matcher: MagicMock, mock_input: MagicMock,
    ) -> None:
        action = MagicMock()
        action.target_pos = (400, 500)
        action.attack_count = 3

        desc_cls = node_registry.get("combat.attack")
        desc = desc_cls()
        ctx = _make_ctx(action, mock_capture, mock_matcher, mock_input)
        result = desc.execute(ctx)

        assert result.success is True
        mock_input.click.assert_called_once()
        click_args = mock_input.click.call_args[0]
        assert abs(click_args[0] - 400) <= 5
        assert abs(click_args[1] - 500) <= 5
        assert mock_input.press_key.call_count == 3

    def test_attack_without_target_only_presses(
        self, node_registry: NodeRegistry,
        mock_capture: MagicMock, mock_matcher: MagicMock, mock_input: MagicMock,
    ) -> None:
        action = MagicMock()
        action.target_pos = None
        action.attack_count = 2

        desc_cls = node_registry.get("combat.attack")
        desc = desc_cls()
        ctx = _make_ctx(action, mock_capture, mock_matcher, mock_input)
        result = desc.execute(ctx)

        assert result.success is True
        mock_input.click.assert_not_called()
        assert mock_input.press_key.call_count == 2

    def test_attack_default_count(
        self, node_registry: NodeRegistry,
        mock_capture: MagicMock, mock_matcher: MagicMock, mock_input: MagicMock,
    ) -> None:
        action = MagicMock()
        action.target_pos = None
        del action.attack_count

        desc_cls = node_registry.get("combat.attack")
        desc = desc_cls()
        ctx = _make_ctx(action, mock_capture, mock_matcher, mock_input)
        result = desc.execute(ctx)

        assert result.success is True
        assert mock_input.press_key.call_count == 3


# ============================================================
# 3. UseSkillDescriptor — 技能
# ============================================================


class TestUseSkillE2E:
    """UseSkillDescriptor E2E: 按键释放技能。"""

    @pytest.fixture(autouse=True)
    def _setup(self, _loaded_plugins):
        pass

    def test_skill_presses_key(
        self, node_registry: NodeRegistry,
        mock_capture: MagicMock, mock_matcher: MagicMock, mock_input: MagicMock,
    ) -> None:
        action = MagicMock()
        action.skill_key = "q"
        action.wait_after = 0.01

        desc_cls = node_registry.get("combat.use_skill")
        desc = desc_cls()
        ctx = _make_ctx(action, mock_capture, mock_matcher, mock_input)
        result = desc.execute(ctx)

        assert result.success is True
        mock_input.press_key.assert_called_once_with("q")

    def test_skill_with_wait(
        self, node_registry: NodeRegistry,
        mock_capture: MagicMock, mock_matcher: MagicMock, mock_input: MagicMock,
    ) -> None:
        action = MagicMock()
        action.skill_key = "e"
        action.wait_after = 0.01

        desc_cls = node_registry.get("combat.use_skill")
        desc = desc_cls()
        ctx = _make_ctx(action, mock_capture, mock_matcher, mock_input)
        result = desc.execute(ctx)

        assert result.success is True
        mock_input.press_key.assert_called_once_with("e")


# ============================================================
# 4. DodgeDescriptor — 闪避
# ============================================================


class TestDodgeE2E:
    """DodgeDescriptor E2E: 方向键 + 闪避键。"""

    @pytest.fixture(autouse=True)
    def _setup(self, _loaded_plugins):
        pass

    def test_dodge_left(
        self, node_registry: NodeRegistry,
        mock_capture: MagicMock, mock_matcher: MagicMock, mock_input: MagicMock,
    ) -> None:
        action = MagicMock()
        action.direction = "left"
        action.dodge_key = "space"

        desc_cls = node_registry.get("combat.dodge")
        desc = desc_cls()
        ctx = _make_ctx(action, mock_capture, mock_matcher, mock_input)
        result = desc.execute(ctx)

        assert result.success is True
        calls = [c.args[0] for c in mock_input.press_key.call_args_list]
        assert "a" in calls
        assert "space" in calls

    def test_dodge_right(
        self, node_registry: NodeRegistry,
        mock_capture: MagicMock, mock_matcher: MagicMock, mock_input: MagicMock,
    ) -> None:
        action = MagicMock()
        action.direction = "right"
        action.dodge_key = "space"

        desc_cls = node_registry.get("combat.dodge")
        desc = desc_cls()
        ctx = _make_ctx(action, mock_capture, mock_matcher, mock_input)
        result = desc.execute(ctx)

        assert result.success is True
        calls = [c.args[0] for c in mock_input.press_key.call_args_list]
        assert "d" in calls
        assert "space" in calls

    def test_dodge_random_uses_a_or_d(
        self, node_registry: NodeRegistry,
        mock_capture: MagicMock, mock_matcher: MagicMock, mock_input: MagicMock,
    ) -> None:
        action = MagicMock()
        action.direction = "random"
        action.dodge_key = "space"

        desc_cls = node_registry.get("combat.dodge")
        desc = desc_cls()
        ctx = _make_ctx(action, mock_capture, mock_matcher, mock_input)
        result = desc.execute(ctx)

        assert result.success is True
        calls = [c.args[0] for c in mock_input.press_key.call_args_list]
        assert ("a" in calls) or ("d" in calls)
        assert "space" in calls


# ============================================================
# 5. TargetSelectionDescriptor — 目标选择
# ============================================================


class TestTargetSelectionE2E:
    """TargetSelectionDescriptor E2E: 多目标选优策略。"""

    @pytest.fixture(autouse=True)
    def _setup(self, _loaded_plugins):
        pass

    def test_nearest_strategy(
        self, node_registry: NodeRegistry,
        mock_capture: MagicMock, mock_matcher: MagicMock, mock_input: MagicMock,
    ) -> None:
        mock_matcher.find_all.return_value = [
            (500, 500, 50, 50),
            (100, 100, 50, 50),
            (800, 800, 50, 50),
        ]
        action = MagicMock()
        action.template_path = "enemies.png"
        action.confidence = 0.7
        action.strategy = "nearest"

        desc_cls = node_registry.get("combat.target_select")
        desc = desc_cls()
        ctx = _make_ctx(action, mock_capture, mock_matcher, mock_input)
        result = desc.execute(ctx)

        assert result.success is True
        assert result.output_vars["target_found"] is True
        assert result.output_vars["target_pos"] == (125, 125)

    def test_farthest_strategy(
        self, node_registry: NodeRegistry,
        mock_capture: MagicMock, mock_matcher: MagicMock, mock_input: MagicMock,
    ) -> None:
        mock_matcher.find_all.return_value = [
            (100, 100, 50, 50),
            (500, 500, 50, 50),
        ]
        action = MagicMock()
        action.template_path = "enemies.png"
        action.confidence = 0.7
        action.strategy = "farthest"

        desc_cls = node_registry.get("combat.target_select")
        desc = desc_cls()
        ctx = _make_ctx(action, mock_capture, mock_matcher, mock_input)
        result = desc.execute(ctx)

        assert result.success is True
        assert result.output_vars["target_found"] is True
        assert result.output_vars["target_pos"] == (525, 525)

    def test_no_targets_found(
        self, node_registry: NodeRegistry,
        mock_capture: MagicMock, mock_matcher: MagicMock, mock_input: MagicMock,
    ) -> None:
        mock_matcher.find_all.return_value = []
        action = MagicMock()
        action.template_path = "enemies.png"
        action.confidence = 0.7
        action.strategy = "nearest"

        desc_cls = node_registry.get("combat.target_select")
        desc = desc_cls()
        ctx = _make_ctx(action, mock_capture, mock_matcher, mock_input)
        result = desc.execute(ctx)

        assert result.success is True
        assert result.output_vars["target_found"] is False


# ============================================================
# 6. 完整战斗循环 — find_enemy → attack → use_skill → dodge
# ============================================================


class TestCombatLoopE2E:
    """完整战斗循环 E2E: 模拟一轮完整的战斗流程。"""

    @pytest.fixture(autouse=True)
    def _setup(self, _loaded_plugins):
        pass

    def test_full_combat_cycle(
        self, node_registry: NodeRegistry,
        mock_capture: MagicMock, mock_matcher: MagicMock, mock_input: MagicMock,
    ) -> None:
        pool = VariablePool()

        # Step 1: find_enemy
        mock_matcher.find.return_value = (300, 400, 60, 80)
        action_find = MagicMock()
        action_find.template_path = "boss.png"
        action_find.confidence = 0.8

        desc_find_cls = node_registry.get("combat.find_enemy")
        desc_find = desc_find_cls()
        ctx = _make_ctx(action_find, mock_capture, mock_matcher, mock_input, variables=pool)
        result_find = desc_find.execute(ctx)

        assert result_find.success is True
        assert result_find.output_vars["enemy_found"] is True
        enemy_pos = result_find.output_vars["enemy_pos"]
        assert enemy_pos == (330, 440)

        pool.set("enemy_pos", enemy_pos)
        pool.set("enemy_found", True)

        # Step 2: attack
        action_attack = MagicMock()
        action_attack.target_pos = enemy_pos
        action_attack.attack_count = 2

        desc_attack_cls = node_registry.get("combat.attack")
        desc_attack = desc_attack_cls()
        ctx = _make_ctx(action_attack, mock_capture, mock_matcher, mock_input, variables=pool)
        result_attack = desc_attack.execute(ctx)

        assert result_attack.success is True
        mock_input.click.assert_called_once()
        click_args = mock_input.click.call_args[0]
        assert abs(click_args[0] - 330) <= 5
        assert abs(click_args[1] - 440) <= 5

        # Step 3: use_skill
        action_skill = MagicMock()
        action_skill.skill_key = "q"
        action_skill.wait_after = 0.01

        desc_skill_cls = node_registry.get("combat.use_skill")
        desc_skill = desc_skill_cls()
        ctx = _make_ctx(action_skill, mock_capture, mock_matcher, mock_input, variables=pool)
        result_skill = desc_skill.execute(ctx)

        assert result_skill.success is True
        mock_input.press_key.assert_any_call("q")

        # Step 4: dodge
        action_dodge = MagicMock()
        action_dodge.direction = "right"
        action_dodge.dodge_key = "space"

        desc_dodge_cls = node_registry.get("combat.dodge")
        desc_dodge = desc_dodge_cls()
        ctx = _make_ctx(action_dodge, mock_capture, mock_matcher, mock_input, variables=pool)
        result_dodge = desc_dodge.execute(ctx)

        assert result_dodge.success is True

    def test_combat_loop_with_target_selection(
        self, node_registry: NodeRegistry,
        mock_capture: MagicMock, mock_matcher: MagicMock, mock_input: MagicMock,
    ) -> None:
        pool = VariablePool()

        # Step 1: target_select (multi-match)
        mock_matcher.find_all.return_value = [
            (200, 200, 50, 50),
            (600, 600, 50, 50),
        ]
        action_select = MagicMock()
        action_select.template_path = "mob.png"
        action_select.confidence = 0.7
        action_select.strategy = "nearest"

        desc_select_cls = node_registry.get("combat.target_select")
        desc_select = desc_select_cls()
        ctx = _make_ctx(action_select, mock_capture, mock_matcher, mock_input, variables=pool)
        result_select = desc_select.execute(ctx)

        assert result_select.success is True
        assert result_select.output_vars["target_found"] is True
        target_pos = result_select.output_vars["target_pos"]
        assert target_pos == (225, 225)

        pool.set("target_pos", target_pos)

        # Step 2: attack the selected target
        action_attack = MagicMock()
        action_attack.target_pos = target_pos
        action_attack.attack_count = 1

        desc_attack_cls = node_registry.get("combat.attack")
        desc_attack = desc_attack_cls()
        ctx = _make_ctx(action_attack, mock_capture, mock_matcher, mock_input, variables=pool)
        result_attack = desc_attack.execute(ctx)

        assert result_attack.success is True
        click_args = mock_input.click.call_args[0]
        assert abs(click_args[0] - 225) <= 5
        assert abs(click_args[1] - 225) <= 5

    def test_no_enemy_skips_combat(
        self, node_registry: NodeRegistry,
        mock_capture: MagicMock, mock_matcher: MagicMock, mock_input: MagicMock,
    ) -> None:
        pool = VariablePool()

        mock_matcher.find.return_value = None
        action_find = MagicMock()
        action_find.template_path = "enemy.png"
        action_find.confidence = 0.8

        desc_find_cls = node_registry.get("combat.find_enemy")
        desc_find = desc_find_cls()
        ctx = _make_ctx(action_find, mock_capture, mock_matcher, mock_input, variables=pool)
        result_find = desc_find.execute(ctx)

        assert result_find.success is True
        assert result_find.output_vars["enemy_found"] is False

        pool.set("enemy_found", False)
        assert pool.get("enemy_found") is False


# ============================================================
# 7. 插件生命周期 — 加载/卸载不影响战斗流程
# ============================================================


class TestCombatPluginLifecycle:
    """CombatPlugin 加载→执行→卸载→重新加载完整生命周期。"""

    def test_reload_and_execute(
        self, loader: PluginLoader,
        node_registry: NodeRegistry,
        mock_capture: MagicMock, mock_matcher: MagicMock, mock_input: MagicMock,
    ) -> None:
        mock_matcher.find.return_value = (100, 200, 50, 60)
        action = MagicMock()
        action.template_path = "test.png"
        action.confidence = 0.7

        # First execution
        desc_cls = node_registry.get("combat.find_enemy")
        desc = desc_cls()
        ctx = _make_ctx(action, mock_capture, mock_matcher, mock_input)
        result = desc.execute(ctx)
        assert result.success is True

        # Unload
        loader.unload("combat")
        assert not node_registry.has("combat.find_enemy")

        # Reload
        loader.reload("combat")
        assert node_registry.has("combat.find_enemy")

        # Execute again after reload
        desc_cls2 = node_registry.get("combat.find_enemy")
        desc2 = desc_cls2()
        result2 = desc2.execute(ctx)
        assert result2.success is True

    def test_all_combat_descriptors_registered(
        self, node_registry: NodeRegistry, _loaded_plugins,
    ) -> None:
        expected = [
            "combat.find_enemy",
            "combat.attack",
            "combat.use_skill",
            "combat.dodge",
            "combat.target_select",
        ]
        for key in expected:
            assert node_registry.has(key), f"{key} 未注册"

        for key in expected:
            desc_cls = node_registry.get(key)
            assert issubclass(desc_cls, NodeDescriptor)
