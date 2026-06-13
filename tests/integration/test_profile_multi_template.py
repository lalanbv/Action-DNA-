"""多模板备用图的导出(abs→rel)与 profile 保存(拷贝)测试。"""

import os

import pytest

from src.core.action import ActionType
from src.core.flow import FlowEdge, FlowGraph, FlowNode, NodeType
from src.core.io.importer import _graph_to_v2_dict
from src.core.step_types import STEP_CLASSES


def _make_img(tmp_path, name: str) -> str:
    """在 tmp_path 下创建一个假图片文件,返回绝对路径。"""
    p = tmp_path / name
    p.write_bytes(b"\x89PNG\r\n\x1a\n")  # PNG 头占位
    return str(p)


def test_graph_to_v2_dict_converts_alt_abs_to_rel(tmp_path):
    """importer 导出时 alt 绝对路径 → 相对 profile_dir。"""
    profile_dir = str(tmp_path)
    abs_a = _make_img(tmp_path, "a.png")
    abs_b = _make_img(tmp_path, "b.png")
    step = STEP_CLASSES[ActionType.CLICK_IMAGE](
        image_path=abs_a,
        alt_image_paths=[abs_b],
    )
    graph = FlowGraph(name="g")
    graph.add_node(FlowNode(node_id="start", node_type=NodeType.START))
    graph.add_node(FlowNode(node_id="c1", node_type=NodeType.ACTION, action=step))
    graph.add_node(FlowNode(node_id="end", node_type=NodeType.END))
    graph.add_edge(FlowEdge(edge_id="e1", from_node="start", to_node="c1"))
    graph.add_edge(FlowEdge(edge_id="e2", from_node="c1", to_node="end"))

    data = _graph_to_v2_dict(graph, profile_dir)

    click_node = next(n for n in data["nodes"] if n["node_id"] == "c1")
    # 主图转相对
    assert click_node["action"]["image_path"] == "a.png"
    # 备用图也转相对
    assert click_node["action"]["alt_image_paths"] == ["b.png"]


@pytest.fixture
def pm(tmp_path, monkeypatch):
    """创建使用临时目录的 ProfileManager。"""
    from src.panel.profile_manager import ProfileManager
    monkeypatch.setattr("src.panel.profile_manager.get_profiles_dir", lambda: str(tmp_path))
    return ProfileManager()


def test_profile_save_copies_alt_images_and_stores_relative(pm, tmp_path):
    """profile 保存时拷贝备用图到 images/,并存相对路径;加载后转回绝对。"""
    # 在 profile 目录之外放源图片
    src_dir = tmp_path / "sources"
    src_dir.mkdir()
    abs_a = _make_img(src_dir, "a.png")
    abs_b = _make_img(src_dir, "b.png")

    step = STEP_CLASSES[ActionType.CLICK_IMAGE](
        image_path=abs_a,
        alt_image_paths=[abs_b],
    )
    graph = FlowGraph(name="multi_save")
    graph.add_node(FlowNode(node_id="start", node_type=NodeType.START))
    graph.add_node(FlowNode(node_id="c1", node_type=NodeType.ACTION, action=step))
    graph.add_node(FlowNode(node_id="end", node_type=NodeType.END))
    graph.add_edge(FlowEdge(edge_id="e1", from_node="start", to_node="c1"))
    graph.add_edge(FlowEdge(edge_id="e2", from_node="c1", to_node="end"))

    pm.save("multi_save", graph)

    # 备用图应被拷贝到 profile 的 images/ 目录
    images_dir = tmp_path / "multi_save" / "images"
    copied = {f.name for f in images_dir.iterdir()} if images_dir.exists() else set()
    assert "b.png" in copied, f"备用图未拷贝到 images/,实际: {copied}"

    # 加载后 alt 路径应转为绝对且指向拷贝后的文件
    loaded = pm.load("multi_save")
    click_node = loaded.nodes["c1"]
    assert len(click_node.action.alt_image_paths) == 1
    alt = click_node.action.alt_image_paths[0]
    assert os.path.isabs(alt)
    assert os.path.exists(alt), f"加载后的备用图路径不存在: {alt}"
