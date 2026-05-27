"""ProfileManager 单元测试 — 配置文件保存/加载/删除。

验证 v1/v2/v3 格式兼容、路径安全校验、图片复制。
所有文件操作在 tempfile 隔离目录中进行。
"""

from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import patch

import pytest

from src.core.action import ActionType
from src.core.step_types import BaseStep, STEP_CLASSES
from src.core.flow import FlowEdge, FlowGraph, FlowNode, NodeType
from src.core.monitor import MonitorConfig
from src.core.action import FoundAction
from src.core.step_types import BaseStep, STEP_CLASSES
from src.panel.profile_manager import (
    ProfileManager,
    _validate_profile_name,
    sanitize_profile_name,
)


@pytest.fixture
def tmp_root(tmp_path):
    """创建临时 profiles 根目录。"""
    return str(tmp_path / "profiles")


@pytest.fixture
def pm(tmp_root: str) -> ProfileManager:
    with patch("src.panel.profile_manager.get_profiles_dir", return_value=tmp_root):
        return ProfileManager()


def _make_flow(name: str = "test") -> FlowGraph:
    """创建简单的 START -> ACTION -> END 流程图。"""
    g = FlowGraph(name=name, start_node_id="start")
    g.add_node(FlowNode(node_id="start", node_type=NodeType.START))
    g.add_node(FlowNode(
        node_id="a1",
        node_type=NodeType.ACTION,
        action=STEP_CLASSES[ActionType.WAIT](wait_seconds=1.0),
    ))
    g.add_node(FlowNode(node_id="end", node_type=NodeType.END))
    g.add_edge(FlowEdge(edge_id="e1", from_node="start", to_node="a1", label="default"))
    g.add_edge(FlowEdge(edge_id="e2", from_node="a1", to_node="end", label="default"))
    g.add_edge(FlowEdge(edge_id="e_loop", from_node="end", to_node="start", label="loop"))
    return g


def _make_v1_data() -> dict:
    """创建 v1 格式配置数据。"""
    return {
        "version": 1,
        "chain": {
            "name": "v1_chain",
            "loop": True,
            "loop_count": 0,
            "steps": [
                {"action_type": "WAIT", "wait_seconds": 2.0},
            ],
        },
    }


def _make_v2_data() -> dict:
    """创建 v2/v3 格式配置数据。"""
    return {
        "version": 2,
        "flow": {
            "name": "v2_flow",
            "start_node_id": "start",
            "loop": True,
            "loop_count": 0,
            "nodes": [
                {"node_id": "start", "node_type": "START"},
                {"node_id": "a1", "node_type": "ACTION", "action": {"action_type": "WAIT", "wait_seconds": 1.0}},
                {"node_id": "end", "node_type": "END"},
            ],
            "edges": [
                {"edge_id": "e1", "from_node": "start", "to_node": "a1", "label": "default"},
                {"edge_id": "e2", "from_node": "a1", "to_node": "end", "label": "default"},
            ],
            "monitors": [],
        },
    }


# ---- sanitize / validate ----


class TestSanitize:
    def test_strips_unsafe_chars(self) -> None:
        assert sanitize_profile_name('a/b:c*d?e"f<g>h|i') == "a_b_c_d_e_f_g_h_i"

    def test_strips_whitespace(self) -> None:
        assert sanitize_profile_name("  hello  ") == "hello"


class TestValidateProfileName:
    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="不能为空"):
            _validate_profile_name("")

    def test_whitespace_only_raises(self) -> None:
        with pytest.raises(ValueError, match="不能为空"):
            _validate_profile_name("   ")

    def test_path_sep_raises(self) -> None:
        with pytest.raises(ValueError, match="路径分隔符"):
            _validate_profile_name("a/b")

    def test_dotdot_raises(self) -> None:
        with pytest.raises(ValueError):
            _validate_profile_name("hello..world")

    def test_valid_name_passes(self) -> None:
        _validate_profile_name("my_config")


# ---- list_profiles ----


class TestListProfiles:
    def test_empty(self, pm: ProfileManager) -> None:
        assert pm.list_profiles() == []

    def test_lists_valid_dirs(self, pm: ProfileManager) -> None:
        for name in ("b_profile", "a_profile"):
            d = os.path.join(pm.root, name)
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "profile.json"), "w") as f:
                json.dump({"version": 1}, f)

        assert pm.list_profiles() == ["a_profile", "b_profile"]

    def test_skips_non_dirs(self, pm: ProfileManager) -> None:
        os.makedirs(pm.root, exist_ok=True)
        with open(os.path.join(pm.root, "file.json"), "w") as f:
            f.write("not a dir")

        assert pm.list_profiles() == []

    def test_skips_missing_json(self, pm: ProfileManager) -> None:
        os.makedirs(os.path.join(pm.root, "empty_dir"), exist_ok=True)

        assert pm.list_profiles() == []

    def test_nonexistent_root(self, pm: ProfileManager) -> None:
        pm.root = "/nonexistent/path"
        assert pm.list_profiles() == []


# ---- save ----


class TestSave:
    def test_creates_profile_dir(self, pm: ProfileManager) -> None:
        graph = _make_flow()
        result = pm.save("test_save", graph)

        assert os.path.isdir(result)
        assert os.path.exists(os.path.join(result, "profile.json"))

    def test_saves_v3_format(self, pm: ProfileManager) -> None:
        graph = _make_flow("my_graph")
        pm.save("test_v3", graph)

        with open(os.path.join(pm.root, "test_v3", "profile.json")) as f:
            data = json.load(f)

        assert data["version"] == 3
        assert data["flow"]["name"] == "my_graph"
        assert len(data["flow"]["nodes"]) == 3

    def test_sanitizes_name(self, pm: ProfileManager) -> None:
        graph = _make_flow()
        result = pm.save("bad/name", graph)

        assert "bad_name" in result

    def test_creates_images_dir(self, pm: ProfileManager) -> None:
        graph = _make_flow()
        result = pm.save("test_img_dir", graph)

        assert os.path.isdir(os.path.join(result, "images"))

    def test_save_with_monitor(self, pm: ProfileManager) -> None:
        graph = _make_flow()
        graph.monitors.append(MonitorConfig(name="test_mon"))
        pm.save("test_mon", graph)

        with open(os.path.join(pm.root, "test_mon", "profile.json")) as f:
            data = json.load(f)

        assert len(data["flow"]["monitors"]) == 1
        assert data["flow"]["monitors"][0]["name"] == "test_mon"


# ---- load ----


class TestLoad:
    def test_load_v1(self, pm: ProfileManager) -> None:
        v1_data = _make_v1_data()
        d = os.path.join(pm.root, "v1_test")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "profile.json"), "w") as f:
            json.dump(v1_data, f)

        graph = pm.load("v1_test")

        assert graph.name == "v1_chain"
        assert len(graph.nodes) > 0

    def test_load_v2(self, pm: ProfileManager) -> None:
        v2_data = _make_v2_data()
        d = os.path.join(pm.root, "v2_test")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "profile.json"), "w") as f:
            json.dump(v2_data, f)

        graph = pm.load("v2_test")

        assert graph.name == "v2_flow"
        assert "start" in graph.nodes
        assert "end" in graph.nodes

    def test_load_v3_roundtrip(self, pm: ProfileManager) -> None:
        graph = _make_flow("roundtrip")
        pm.save("rt_test", graph)

        loaded = pm.load("rt_test")

        assert loaded.name == "roundtrip"
        assert len(loaded.nodes) == 3
        assert len(loaded.edges) == 3

    def test_load_missing_raises(self, pm: ProfileManager) -> None:
        with pytest.raises(FileNotFoundError, match="配置文件不存在"):
            pm.load("nonexistent")

    def test_load_bad_json_raises(self, pm: ProfileManager) -> None:
        d = os.path.join(pm.root, "bad_json")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "profile.json"), "w") as f:
            f.write("{invalid json")

        with pytest.raises(ValueError, match="配置文件格式错误"):
            pm.load("bad_json")

    def test_load_unsupported_version_raises(self, pm: ProfileManager) -> None:
        d = os.path.join(pm.root, "bad_ver")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "profile.json"), "w") as f:
            json.dump({"version": 99}, f)

        with pytest.raises(ValueError, match="不支持的配置版本"):
            pm.load("bad_ver")

    def test_load_v1_missing_chain_raises(self, pm: ProfileManager) -> None:
        d = os.path.join(pm.root, "bad_v1")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "profile.json"), "w") as f:
            json.dump({"version": 1, "chain": None}, f)

        with pytest.raises(ValueError, match="缺少 'chain' 字段"):
            pm.load("bad_v1")


# ---- delete ----


class TestDelete:
    def test_delete_existing(self, pm: ProfileManager) -> None:
        graph = _make_flow()
        pm.save("to_delete", graph)
        assert pm.exists("to_delete")

        pm.delete("to_delete")

        assert not pm.exists("to_delete")

    def test_delete_nonexistent_noop(self, pm: ProfileManager) -> None:
        pm.delete("ghost")


# ---- exists ----


class TestExists:
    def test_exists_false(self, pm: ProfileManager) -> None:
        assert pm.exists("nope") is False

    def test_exists_true(self, pm: ProfileManager) -> None:
        graph = _make_flow()
        pm.save("exists_test", graph)

        assert pm.exists("exists_test") is True


# ---- _copy_image ----


class TestCopyImage:
    def test_copy_external_image(self, pm: ProfileManager, tmp_path) -> None:
        src = tmp_path / "source.png"
        src.write_bytes(b"\x89PNG")

        profile_dir = os.path.join(pm.root, "img_test")
        images_dir = os.path.join(profile_dir, "images")
        os.makedirs(images_dir, exist_ok=True)

        rel = pm._copy_image(str(src), profile_dir, images_dir)

        assert rel == "images/source.png"
        assert os.path.exists(os.path.join(profile_dir, rel))

    def test_skip_nonexistent(self, pm: ProfileManager) -> None:
        profile_dir = os.path.join(pm.root, "skip_test")
        images_dir = os.path.join(profile_dir, "images")
        os.makedirs(images_dir, exist_ok=True)

        rel = pm._copy_image("/nonexistent/img.png", profile_dir, images_dir)

        assert rel == "/nonexistent/img.png"

    def test_already_in_profile_returns_relative(self, pm: ProfileManager) -> None:
        profile_dir = os.path.join(pm.root, "already_test")
        images_dir = os.path.join(profile_dir, "images")
        os.makedirs(images_dir, exist_ok=True)
        img_path = os.path.join(profile_dir, "images", "local.png")
        with open(img_path, "w") as f:
            f.write("img")

        rel = pm._copy_image(img_path, profile_dir, images_dir)

        assert "local.png" in rel

    def test_conflict_renames(self, pm: ProfileManager, tmp_path) -> None:
        src = tmp_path / "dup.png"
        src.write_bytes(b"\x89PNG")

        profile_dir = os.path.join(pm.root, "conflict_test")
        images_dir = os.path.join(profile_dir, "images")
        os.makedirs(images_dir, exist_ok=True)
        existing = os.path.join(images_dir, "dup.png")
        with open(existing, "w") as f:
            f.write("old")

        rel = pm._copy_image(str(src), profile_dir, images_dir)

        assert "dup_1.png" in rel

    def test_same_path_no_copy(self, pm: ProfileManager, tmp_path) -> None:
        profile_dir = os.path.join(pm.root, "same_test")
        images_dir = os.path.join(profile_dir, "images")
        os.makedirs(images_dir, exist_ok=True)
        img_path = os.path.join(images_dir, "same.png")
        with open(img_path, "w") as f:
            f.write("data")

        rel = pm._copy_image(img_path, profile_dir, images_dir)

        assert "same.png" in rel
