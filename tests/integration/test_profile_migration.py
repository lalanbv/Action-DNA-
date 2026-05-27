"""Profile 迁移集成测试 — v1 → v2 → v3 全迁移链。

验证:
- v1 (ActionChain) 配置正确加载为 FlowGraph
- v2 配置（无 v3 字段）正确加载，新字段使用默认值
- v3 配置完整序列化/反序列化往返
- v2 → v3 自动迁移：缺失字段填充默认值
- error_config / breakpoint / fsm_transitions / fsm_global_transitions 正确持久化
"""

from __future__ import annotations

import json
import os

import pytest

from src.core.action import ActionType
from src.core.step_types import BaseStep, STEP_CLASSES
from src.core.engine.fsm_engine import GlobalTransition, Transition
from src.core.error.error_config import ErrorConfig, ErrorStrategy, RetryPolicy
from src.core.flow import FlowEdge, FlowGraph, FlowNode, NodeType
from src.core.monitor import MonitorConfig
from src.core.serialization import (
    dict_to_flow_node,
    flow_node_to_dict,
)
from src.panel.profile_manager import ProfileManager


# ---- Fixtures ----


@pytest.fixture
def pm(tmp_path):
    """创建 root 指向临时目录的 ProfileManager。"""
    manager = ProfileManager()
    manager.root = str(tmp_path)
    return manager


# ---- 辅助 ----


def _v1_profile_data() -> dict:
    """构造 v1 ActionChain 格式的 profile.json 数据"""
    return {
        "version": 1,
        "name": "test_v1",
        "chain": {
            "name": "v1_chain",
            "loop": False,
            "loop_count": 0,
            "steps": [
                {"action_type": "WAIT", "wait_seconds": 0.5},
                {"action_type": "CLICK_POS", "pos_x": 100, "pos_y": 200},
            ],
        },
    }


def _v2_profile_data() -> dict:
    """构造 v2 FlowGraph 格式的 profile.json 数据（无 v3 字段）"""
    return {
        "version": 2,
        "name": "test_v2",
        "flow": {
            "name": "v2_graph",
            "start_node_id": "start",
            "loop": True,
            "loop_count": 5,
            "nodes": [
                {"node_id": "start", "node_type": "START", "comment": "", "enabled": True, "loop_count": 0, "pos_x": 0, "pos_y": 0},
                {"node_id": "a1", "node_type": "ACTION", "comment": "wait step", "enabled": True, "loop_count": 0, "pos_x": 100, "pos_y": 100,
                 "action": {"action_type": "WAIT", "wait_seconds": 0.1, "detect_mode": "WAIT_UNTIL_FOUND", "found_action": "LEFT_CLICK"}},
                {"node_id": "end", "node_type": "END", "comment": "", "enabled": True, "loop_count": 0, "pos_x": 200, "pos_y": 200},
            ],
            "edges": [
                {"edge_id": "e1", "from_node": "start", "to_node": "a1", "label": "default", "priority": 0},
                {"edge_id": "e2", "from_node": "a1", "to_node": "end", "label": "default", "priority": 0},
            ],
            "monitors": [],
        },
    }


def _v3_profile_data() -> dict:
    """构造 v3 FlowGraph 格式的 profile.json 数据（含完整 v3 字段）"""
    return {
        "version": 3,
        "name": "test_v3",
        "flow": {
            "name": "v3_graph",
            "start_node_id": "start",
            "loop": False,
            "loop_count": 0,
            "nodes": [
                {"node_id": "start", "node_type": "START", "comment": "", "enabled": True, "loop_count": 0, "pos_x": 0, "pos_y": 0},
                {"node_id": "a1", "node_type": "ACTION", "comment": "action with v3", "enabled": True, "loop_count": 0, "pos_x": 50, "pos_y": 50,
                 "action": {"action_type": "WAIT", "wait_seconds": 0.01, "detect_mode": "WAIT_UNTIL_FOUND", "found_action": "LEFT_CLICK"},
                 "error_config": {"strategy": "retry", "retry_policy": {"max_retries": 3, "base_delay": 1.0, "max_delay": 30.0, "jitter_factor": 0.5}},
                 "breakpoint": True,
                 "fsm_transitions": [
                     {"source_state": "IDLE", "target_state": "RUNNING", "trigger_event": "start"},
                     {"source_state": "RUNNING", "target_state": "IDLE", "trigger_event": "stop"},
                 ],
                 "fsm_global_transitions": [
                     {"trigger_event": "emergency", "target_state": "HANDLER", "priority": 100},
                 ]},
                {"node_id": "end", "node_type": "END", "comment": "", "enabled": True, "loop_count": 0, "pos_x": 200, "pos_y": 200},
            ],
            "edges": [
                {"edge_id": "e1", "from_node": "start", "to_node": "a1", "label": "default", "priority": 0},
                {"edge_id": "e2", "from_node": "a1", "to_node": "end", "label": "default", "priority": 0},
            ],
            "monitors": [],
        },
    }


def _write_profile(tmp_path: str, name: str, data: dict) -> str:
    """写入 profile.json 到临时目录"""
    profile_dir = os.path.join(tmp_path, name)
    os.makedirs(profile_dir, exist_ok=True)
    config_path = os.path.join(profile_dir, "profile.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return profile_dir


# ---- v1 加载测试 ----


class TestV1Migration:
    """v1 ActionChain → FlowGraph 自动转换。"""

    def test_v1_loads_as_flowgraph(self, tmp_path, pm) -> None:

        _write_profile(str(tmp_path), "test_v1", _v1_profile_data())

        graph = pm.load("test_v1")
        assert isinstance(graph, FlowGraph)
        assert graph.loop is False

    def test_v1_steps_become_action_nodes(self, tmp_path, pm) -> None:

        _write_profile(str(tmp_path), "test_v1", _v1_profile_data())

        graph = pm.load("test_v1")
        action_nodes = [n for n in graph.nodes.values() if n.node_type == NodeType.ACTION]
        assert len(action_nodes) == 2

    def test_v1_new_fields_default(self, tmp_path, pm) -> None:
        """v1 转换后 FlowNode 的 v3 字段应为默认值。"""

        _write_profile(str(tmp_path), "test_v1", _v1_profile_data())

        graph = pm.load("test_v1")
        for node in graph.nodes.values():
            assert node.error_config is None
            assert node.breakpoint is False
            assert node.fsm_transitions == []
            assert node.fsm_global_transitions == []


# ---- v2 加载测试 ----


class TestV2Migration:
    """v2 FlowGraph 加载 — v3 新字段缺失时使用默认值。"""

    def test_v2_loads_successfully(self, tmp_path, pm) -> None:

        _write_profile(str(tmp_path), "test_v2", _v2_profile_data())

        graph = pm.load("test_v2")
        assert graph.name == "v2_graph"
        assert graph.loop is True
        assert graph.loop_count == 5

    def test_v2_nodes_loaded(self, tmp_path, pm) -> None:

        _write_profile(str(tmp_path), "test_v2", _v2_profile_data())

        graph = pm.load("test_v2")
        assert len(graph.nodes) == 3
        a1 = graph.nodes["a1"]
        assert a1.comment == "wait step"
        assert a1.action is not None
        assert a1.action.action_type == ActionType.WAIT

    def test_v2_v3_fields_default(self, tmp_path, pm) -> None:
        """v2 数据加载后，v3 新字段应为默认值。"""

        _write_profile(str(tmp_path), "test_v2", _v2_profile_data())

        graph = pm.load("test_v2")
        for node in graph.nodes.values():
            assert node.error_config is None
            assert node.breakpoint is False
            assert node.fsm_transitions == []
            assert node.fsm_global_transitions == []

    def test_v2_to_v3_resave(self, tmp_path, pm) -> None:
        """v2 加载后重新保存为 v3，版本号应升级。"""

        _write_profile(str(tmp_path), "test_v2", _v2_profile_data())

        graph = pm.load("test_v2")
        pm.save("test_v2_migrated", graph)

        config_path = os.path.join(str(tmp_path), "test_v2_migrated", "profile.json")
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["version"] == 3

    def test_v2_resave_load_roundtrip(self, tmp_path, pm) -> None:
        """v2 → save → load 往返后图结构不变。"""

        _write_profile(str(tmp_path), "test_v2", _v2_profile_data())

        graph = pm.load("test_v2")
        pm.save("roundtrip", graph)
        loaded = pm.load("roundtrip")

        assert loaded.name == graph.name
        assert loaded.loop == graph.loop
        assert loaded.loop_count == graph.loop_count
        assert len(loaded.nodes) == len(graph.nodes)
        assert len(loaded.edges) == len(graph.edges)


# ---- v3 完整序列化测试 ----


class TestV3Serialization:
    """v3 格式的完整序列化/反序列化。"""

    def test_v3_loads_all_fields(self, tmp_path, pm) -> None:

        _write_profile(str(tmp_path), "test_v3", _v3_profile_data())

        graph = pm.load("test_v3")
        a1 = graph.nodes["a1"]

        assert a1.error_config is not None
        assert a1.error_config.strategy == ErrorStrategy.RETRY
        assert a1.error_config.retry_policy is not None
        assert a1.error_config.retry_policy.max_retries == 3

        assert a1.breakpoint is True

        assert len(a1.fsm_transitions) == 2
        assert a1.fsm_transitions[0].source_state == "IDLE"
        assert a1.fsm_transitions[0].target_state == "RUNNING"
        assert a1.fsm_transitions[1].source_state == "RUNNING"

        assert len(a1.fsm_global_transitions) == 1
        assert a1.fsm_global_transitions[0].trigger_event == "emergency"
        assert a1.fsm_global_transitions[0].priority == 100

    def test_v3_save_load_roundtrip(self, tmp_path, pm) -> None:
        """v3 完整往返：构造 FlowGraph → save → load → 验证所有字段。"""
        graph = FlowGraph(name="v3_full", start_node_id="start", loop=False)
        graph.add_node(FlowNode(node_id="start", node_type=NodeType.START))
        graph.add_node(FlowNode(
            node_id="a1",
            node_type=NodeType.ACTION,
            action=STEP_CLASSES[ActionType.CLICK_POS](pos_x=42, pos_y=84),
            error_config=ErrorConfig.retry(max_retries=5, base_delay=2.0, exhausted_strategy=ErrorStrategy.SKIP),
            breakpoint=True,
            fsm_transitions=[
                Transition("A", "B", "go", priority=10),
                Transition("B", "C", "next"),
            ],
            fsm_global_transitions=[
                GlobalTransition("panic", "SAFE", priority=999),
            ],
        ))
        graph.add_node(FlowNode(node_id="end", node_type=NodeType.END))
        graph.add_edge(FlowEdge(edge_id="e1", from_node="start", to_node="a1"))
        graph.add_edge(FlowEdge(edge_id="e2", from_node="a1", to_node="end"))


        pm.save("v3_full", graph)
        loaded = pm.load("v3_full")

        assert loaded.name == "v3_full"
        a1 = loaded.nodes["a1"]

        assert a1.error_config is not None
        assert a1.error_config.strategy == ErrorStrategy.RETRY
        assert a1.error_config.retry_policy is not None
        assert a1.error_config.retry_policy.max_retries == 5
        assert a1.error_config.retry_policy.base_delay == 2.0
        assert a1.error_config.exhausted_strategy == ErrorStrategy.SKIP

        assert a1.breakpoint is True

        assert len(a1.fsm_transitions) == 2
        assert a1.fsm_transitions[0].source_state == "A"
        assert a1.fsm_transitions[0].target_state == "B"
        assert a1.fsm_transitions[0].trigger_event == "go"
        assert a1.fsm_transitions[0].priority == 10
        assert a1.fsm_transitions[1].source_state == "B"

        assert len(a1.fsm_global_transitions) == 1
        assert a1.fsm_global_transitions[0].trigger_event == "panic"
        assert a1.fsm_global_transitions[0].target_state == "SAFE"
        assert a1.fsm_global_transitions[0].priority == 999

    def test_v3_version_written(self, tmp_path, pm) -> None:
        """save 应写入 version 3。"""
        graph = FlowGraph(name="ver_check", start_node_id="start")
        graph.add_node(FlowNode(node_id="start", node_type=NodeType.START))
        graph.add_node(FlowNode(node_id="end", node_type=NodeType.END))
        graph.add_edge(FlowEdge(edge_id="e1", from_node="start", to_node="end"))


        pm.save("ver_test", graph)

        with open(os.path.join(str(tmp_path), "ver_test", "profile.json"), "r") as f:
            data = json.load(f)
        assert data["version"] == 3

    def test_v3_node_without_v3_fields_omits_keys(self, tmp_path, pm) -> None:
        """无 v3 字段的节点不应在 JSON 中出现空键。"""
        node = FlowNode(node_id="plain", node_type=NodeType.ACTION, action=STEP_CLASSES[ActionType.WAIT](wait_seconds=1.0))
        d = flow_node_to_dict(node)

        assert "error_config" not in d
        assert "breakpoint" not in d
        assert "fsm_transitions" not in d
        assert "fsm_global_transitions" not in d

    def test_v3_node_with_all_fields(self) -> None:
        """所有 v3 字段存在时正确序列化。"""
        node = FlowNode(
            node_id="full",
            node_type=NodeType.ACTION,
            action=STEP_CLASSES[ActionType.WAIT](wait_seconds=0.5),
            error_config=ErrorConfig.fail_fast("boom"),
            breakpoint=True,
            fsm_transitions=[Transition("X", "Y", "ev")],
            fsm_global_transitions=[GlobalTransition("g", "Z", priority=5)],
        )
        d = flow_node_to_dict(node)

        assert d["error_config"]["strategy"] == "fail_fast"
        assert d["error_config"]["error_message"] == "boom"
        assert d["breakpoint"] is True
        assert len(d["fsm_transitions"]) == 1
        assert d["fsm_transitions"][0]["source_state"] == "X"
        assert len(d["fsm_global_transitions"]) == 1
        assert d["fsm_global_transitions"][0]["priority"] == 5


# ---- 全迁移链: v1 → v2 → v3 ----


class TestFullMigrationChain:
    """完整的迁移链验证: v1 → load → save → load (v3)。"""

    def test_v1_to_v3_chain(self, tmp_path, pm) -> None:
        """v1 加载后重新保存为 v3，再加载验证完整性。"""

        _write_profile(str(tmp_path), "chain_v1", _v1_profile_data())

        graph_v1 = pm.load("chain_v1")
        assert isinstance(graph_v1, FlowGraph)

        pm.save("chain_v3", graph_v1)

        with open(os.path.join(str(tmp_path), "chain_v3", "profile.json"), "r") as f:
            data = json.load(f)
        assert data["version"] == 3

        graph_v3 = pm.load("chain_v3")
        assert graph_v3.name == graph_v1.name
        assert len(graph_v3.nodes) == len(graph_v1.nodes)
        assert len(graph_v3.edges) == len(graph_v1.edges)

        for node in graph_v3.nodes.values():
            assert node.error_config is None
            assert node.breakpoint is False
            assert node.fsm_transitions == []
            assert node.fsm_global_transitions == []

    def test_v2_to_v3_chain(self, tmp_path, pm) -> None:
        """v2 → load → save(v3) → load 验证。"""

        _write_profile(str(tmp_path), "chain_v2", _v2_profile_data())

        graph = pm.load("chain_v2")
        pm.save("chain_v3", graph)

        loaded = pm.load("chain_v3")
        assert loaded.name == "v2_graph"
        assert loaded.loop is True
        assert loaded.loop_count == 5
        assert len(loaded.nodes) == 3
        assert len(loaded.edges) == 2

    def test_migration_preserves_edges(self, tmp_path, pm) -> None:
        """迁移后边结构完整。"""

        _write_profile(str(tmp_path), "edge_v2", _v2_profile_data())

        graph = pm.load("edge_v2")
        pm.save("edge_v3", graph)
        loaded = pm.load("edge_v3")

        edge_pairs = [(e.from_node, e.to_node) for e in loaded.edges]
        assert ("start", "a1") in edge_pairs
        assert ("a1", "end") in edge_pairs


# ---- 错误配置迁移精确验证 ----


class TestErrorConfigMigration:
    """error_config 各策略在迁移中的序列化正确性。"""

    @pytest.mark.parametrize("strategy", [s for s in ErrorStrategy])
    def test_each_strategy_survives_roundtrip(self, strategy: ErrorStrategy) -> None:
        """每种 ErrorStrategy 通过 save/load 后保留。"""
        config = ErrorConfig(strategy=strategy)
        node = FlowNode(
            node_id="s",
            node_type=NodeType.ACTION,
            action=STEP_CLASSES[ActionType.WAIT](wait_seconds=1.0),
            error_config=config,
        )
        d = flow_node_to_dict(node)
        restored = dict_to_flow_node(d, "/tmp")

        assert restored.error_config is not None
        assert restored.error_config.strategy == strategy

    def test_retry_with_full_policy(self) -> None:
        """RETRY 策略含完整 RetryPolicy 往返。"""
        config = ErrorConfig.retry(
            max_retries=7,
            base_delay=3.0,
            max_delay=120.0,
            exhausted_strategy=ErrorStrategy.FAIL_FAST,
        )
        node = FlowNode(
            node_id="retry_full",
            node_type=NodeType.ACTION,
            action=STEP_CLASSES[ActionType.WAIT](wait_seconds=0.1),
            error_config=config,
        )
        d = flow_node_to_dict(node)
        restored = dict_to_flow_node(d, "/tmp")

        ec = restored.error_config
        assert ec is not None
        assert ec.strategy == ErrorStrategy.RETRY
        assert ec.retry_policy is not None
        assert ec.retry_policy.max_retries == 7
        assert ec.retry_policy.base_delay == 3.0
        assert ec.retry_policy.max_delay == 120.0
        assert ec.exhausted_strategy == ErrorStrategy.FAIL_FAST


# ---- FSM 字段迁移精确验证 ----


class TestFSMMigration:
    """fsm_transitions / fsm_global_transitions 迁移验证。"""

    def test_transition_with_all_fields(self) -> None:
        """Transition 含 condition/priority/label 正确序列化。"""
        node = FlowNode(
            node_id="fsm",
            node_type=NodeType.ACTION,
            action=STEP_CLASSES[ActionType.WAIT](wait_seconds=0.1),
            fsm_transitions=[
                Transition("S1", "S2", "ev", condition="var > 0", priority=5, label="my_label"),
            ],
        )
        d = flow_node_to_dict(node)
        restored = dict_to_flow_node(d, "/tmp")

        t = restored.fsm_transitions[0]
        assert t.source_state == "S1"
        assert t.target_state == "S2"
        assert t.trigger_event == "ev"
        assert t.condition == "var > 0"
        assert t.priority == 5
        assert t.label == "my_label"

    def test_global_transition_with_all_fields(self) -> None:
        """GlobalTransition 含 condition/priority/label 正确序列化。"""
        node = FlowNode(
            node_id="gfsm",
            node_type=NodeType.ACTION,
            action=STEP_CLASSES[ActionType.WAIT](wait_seconds=0.1),
            fsm_global_transitions=[
                GlobalTransition("alert", "SAFE", condition="status == 'error'", priority=50, label="emergency"),
            ],
        )
        d = flow_node_to_dict(node)
        restored = dict_to_flow_node(d, "/tmp")

        g = restored.fsm_global_transitions[0]
        assert g.trigger_event == "alert"
        assert g.target_state == "SAFE"
        assert g.condition == "status == 'error'"
        assert g.priority == 50
        assert g.label == "emergency"

    def test_multiple_transitions_order_preserved(self) -> None:
        """多个 Transition 保持顺序。"""
        transitions = [
            Transition(f"S{i}", f"S{i+1}", f"ev{i}")
            for i in range(5)
        ]
        node = FlowNode(
            node_id="multi",
            node_type=NodeType.ACTION,
            action=STEP_CLASSES[ActionType.WAIT](wait_seconds=0.1),
            fsm_transitions=transitions,
        )
        d = flow_node_to_dict(node)
        restored = dict_to_flow_node(d, "/tmp")

        assert len(restored.fsm_transitions) == 5
        for i, t in enumerate(restored.fsm_transitions):
            assert t.source_state == f"S{i}"
            assert t.target_state == f"S{i+1}"
