"""ProfileImporter 迁移链集成测试 — v1 直达 v3 验证。

验证 src/core/io/importer.py 的 ProfileImporter:
- v1 → v2 → v3 链式迁移（两步）
- v2 → v3 单步迁移
- v3 直达（无迁移）
- 跳过迁移正确（已有字段不被覆盖）
- MigrationReport 准确性
"""

from __future__ import annotations

import json
import os

import pytest

from src.core.action import ActionType
from src.core.error.error_config import ErrorStrategy
from src.core.flow import NodeType
from src.core.io.importer import MigrationReport, ProfileImporter
from _helpers import ActionChain


# ---- Fixtures ----


@pytest.fixture
def importer() -> ProfileImporter:
    return ProfileImporter()


@pytest.fixture
def tmp_profile_dir(tmp_path) -> str:
    return str(tmp_path)


def _write_profile(tmp_path: str, name: str, data: dict) -> str:
    profile_dir = os.path.join(tmp_path, name)
    os.makedirs(profile_dir, exist_ok=True)
    config_path = os.path.join(profile_dir, "profile.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return config_path


# ---- v1 测试数据 ----


def _v1_data() -> dict:
    return {
        "version": 1,
        "name": "v1_test",
        "chain": {
            "name": "v1_chain",
            "loop": True,
            "loop_count": 0,
            "steps": [
                {"action_type": "PRESS_KEY", "key": "a"},
                {"action_type": "WAIT", "wait_seconds": 0.5},
                {"action_type": "CLICK_POS", "pos_x": 100, "pos_y": 200},
            ],
        },
    }


# ---- v2 测试数据 ----


def _v2_data() -> dict:
    return {
        "version": 2,
        "name": "v2_test",
        "flow": {
            "name": "v2_graph",
            "start_node_id": "start",
            "loop": False,
            "loop_count": 3,
            "nodes": [
                {"node_id": "start", "node_type": "START", "comment": "", "enabled": True, "loop_count": 0, "pos_x": 0, "pos_y": 0},
                {"node_id": "a1", "node_type": "ACTION", "comment": "step1", "enabled": True, "loop_count": 0, "pos_x": 100, "pos_y": 100,
                 "action": {"action_type": "PRESS_KEY", "key": "x", "detect_mode": "WAIT_UNTIL_FOUND", "found_action": "LEFT_CLICK"}},
                {"node_id": "end", "node_type": "END", "comment": "", "enabled": True, "loop_count": 0, "pos_x": 200, "pos_y": 200},
            ],
            "edges": [
                {"edge_id": "e1", "from_node": "start", "to_node": "a1", "label": "default", "priority": 0},
                {"edge_id": "e2", "from_node": "a1", "to_node": "end", "label": "default", "priority": 0},
            ],
            "monitors": [],
        },
    }


# ---- v3 测试数据（已有 v3 字段）----


def _v3_data() -> dict:
    return {
        "version": 3,
        "name": "v3_test",
        "flow": {
            "name": "v3_graph",
            "start_node_id": "start",
            "loop": True,
            "loop_count": 0,
            "nodes": [
                {"node_id": "start", "node_type": "START", "comment": "", "enabled": True, "loop_count": 0, "pos_x": 0, "pos_y": 0},
                {"node_id": "a1", "node_type": "ACTION", "comment": "v3_node", "enabled": True, "loop_count": 0, "pos_x": 50, "pos_y": 50,
                 "action": {"action_type": "WAIT", "wait_seconds": 0.1, "detect_mode": "WAIT_UNTIL_FOUND", "found_action": "LEFT_CLICK"},
                 "error_config": {"strategy": "retry", "max_retries": 5, "retry_delay": 0.5},
                 "breakpoint": True,
                 "fsm_transitions": [
                     {"source_state": "IDLE", "target_state": "RUNNING", "trigger_event": "go"},
                 ],
                 "fsm_global_transitions": [
                     {"trigger_event": "panic", "target_state": "SAFE", "priority": 100},
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


# ---- v1 → v3 全链迁移 ----


class TestV1ToV3Chain:
    """v1 ActionChain 直达 v3 FlowGraph — 两步迁移。"""

    def test_v1_produces_flowgraph(self, importer: ProfileImporter) -> None:
        graph, report = importer.import_profile(_v1_data())

        assert report.original_version == 1
        assert report.final_version == 3
        assert report.migrated is True
        assert len(report.steps) == 2

    def test_v1_nodes_become_action_nodes(self, importer: ProfileImporter) -> None:
        graph, _ = importer.import_profile(_v1_data())

        action_nodes = [n for n in graph.nodes.values() if n.node_type == NodeType.ACTION]
        assert len(action_nodes) == 3

    def test_v1_has_start_and_end(self, importer: ProfileImporter) -> None:
        graph, _ = importer.import_profile(_v1_data())

        types = {n.node_type for n in graph.nodes.values()}
        assert NodeType.START in types
        assert NodeType.END in types

    def test_v1_edges_form_linear_chain(self, importer: ProfileImporter) -> None:
        graph, _ = importer.import_profile(_v1_data())

        # start->a0->a1->a2->end + loop edge end->start
        assert len(graph.edges) == 5

    def test_v1_loop_preserved(self, importer: ProfileImporter) -> None:
        graph, _ = importer.import_profile(_v1_data())
        assert graph.loop is True

    def test_v1_nodes_get_error_config_defaults(self, importer: ProfileImporter) -> None:
        graph, _ = importer.import_profile(_v1_data())

        for node in graph.nodes.values():
            assert node.error_config is not None
            assert node.error_config.strategy == ErrorStrategy.IGNORE
            assert node.breakpoint is False
            assert node.fsm_transitions == []
            assert node.fsm_global_transitions == []

    def test_v1_migration_report_describe(self, importer: ProfileImporter) -> None:
        _, report = importer.import_profile(_v1_data())

        desc = report.describe()
        assert "v1" in desc
        assert "v3" in desc
        assert "v1→v2" in desc
        assert "v2→v3" in desc


# ---- v2 → v3 单步迁移 ----


class TestV2ToV3Migration:
    """v2 FlowGraph → v3（添加默认字段）。"""

    def test_v2_migrates_to_v3(self, importer: ProfileImporter) -> None:
        graph, report = importer.import_profile(_v2_data())

        assert report.original_version == 2
        assert report.final_version == 3
        assert report.migrated is True
        assert len(report.steps) == 1
        assert "v2→v3" in report.steps[0]

    def test_v2_preserves_graph_structure(self, importer: ProfileImporter) -> None:
        graph, _ = importer.import_profile(_v2_data())

        assert graph.name == "v2_graph"
        assert graph.loop is False
        assert graph.loop_count == 3
        assert len(graph.nodes) == 3
        assert len(graph.edges) == 2

    def test_v2_nodes_get_defaults(self, importer: ProfileImporter) -> None:
        graph, _ = importer.import_profile(_v2_data())

        for node in graph.nodes.values():
            assert node.error_config is not None
            assert node.error_config.strategy == ErrorStrategy.IGNORE
            assert node.breakpoint is False

    def test_v2_action_node_preserved(self, importer: ProfileImporter) -> None:
        graph, _ = importer.import_profile(_v2_data())

        a1 = graph.nodes["a1"]
        assert a1.action is not None
        assert a1.action.action_type == ActionType.PRESS_KEY
        assert a1.comment == "step1"


# ---- v3 直达（无迁移）----


class TestV3Passthrough:
    """v3 数据不触发迁移。"""

    def test_v3_no_migration(self, importer: ProfileImporter) -> None:
        _, report = importer.import_profile(_v3_data())

        assert report.original_version == 3
        assert report.final_version == 3
        assert report.migrated is False
        assert report.steps == []

    def test_v3_preserves_custom_fields(self, importer: ProfileImporter) -> None:
        graph, _ = importer.import_profile(_v3_data())

        a1 = graph.nodes["a1"]
        assert a1.error_config is not None
        assert a1.error_config.strategy == ErrorStrategy.RETRY
        assert a1.breakpoint is True
        assert len(a1.fsm_transitions) == 1
        assert a1.fsm_transitions[0].source_state == "IDLE"
        assert len(a1.fsm_global_transitions) == 1
        assert a1.fsm_global_transitions[0].trigger_event == "panic"

    def test_v3_skip_migration_no_overwrite(self, importer: ProfileImporter) -> None:
        """已有 retry 策略不应被默认 ignore 覆盖。"""
        graph, _ = importer.import_profile(_v3_data())

        a1 = graph.nodes["a1"]
        assert a1.error_config.strategy == ErrorStrategy.RETRY
        assert a1.error_config.strategy != ErrorStrategy.IGNORE


# ---- 文件导入 ----


class TestFileImport:
    """import_from_file 从 profile.json 文件导入。"""

    def test_import_v1_from_file(self, importer: ProfileImporter, tmp_profile_dir: str) -> None:
        config_path = _write_profile(tmp_profile_dir, "from_file_v1", _v1_data())

        graph, report = importer.import_from_file(config_path)
        assert report.original_version == 1
        assert report.final_version == 3
        assert len(graph.nodes) >= 3

    def test_import_v2_from_file(self, importer: ProfileImporter, tmp_profile_dir: str) -> None:
        config_path = _write_profile(tmp_profile_dir, "from_file_v2", _v2_data())

        graph, report = importer.import_from_file(config_path)
        assert report.original_version == 2
        assert report.final_version == 3

    def test_import_v3_from_file(self, importer: ProfileImporter, tmp_profile_dir: str) -> None:
        config_path = _write_profile(tmp_profile_dir, "from_file_v3", _v3_data())

        graph, report = importer.import_from_file(config_path)
        assert report.migrated is False

    def test_import_file_not_found(self, importer: ProfileImporter) -> None:
        with pytest.raises(FileNotFoundError):
            importer.import_from_file("/nonexistent/profile.json")


# ---- 错误处理 ----


class TestMigrationErrors:
    """迁移链错误处理。"""

    def test_unsupported_version_raises(self, importer: ProfileImporter) -> None:
        with pytest.raises(ValueError, match="不支持的配置版本"):
            importer.import_profile({"version": 99, "flow": {}})

    def test_v1_missing_chain_raises(self, importer: ProfileImporter) -> None:
        with pytest.raises(ValueError, match="v1 配置缺少 'chain' 字段"):
            importer.import_profile({"version": 1, "name": "bad"})

    def test_missing_version_defaults_to_v1(self, importer: ProfileImporter) -> None:
        data = {
            "chain": {
                "name": "no_ver",
                "steps": [{"action_type": "WAIT", "wait_seconds": 0.1}],
                "loop": False,
            }
        }
        graph, report = importer.import_profile(data)
        assert report.original_version == 1
        assert report.final_version == 3
