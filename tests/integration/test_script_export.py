"""集成测试 — 验证导出脚本的编译、结构和语法正确性"""

import base64
import textwrap
from pathlib import Path

import pytest

from src.core.action import ActionType
from src.core.step_types import BaseStep, STEP_CLASSES
from src.core.flow import FlowEdge, FlowGraph, FlowNode, NodeType
from src.core.io.script_exporter import GraphComplexity, ScriptExporter


def _make_linear_graph(
    actions: list[BaseStep],
    name: str = "integration_test",
) -> FlowGraph:
    graph = FlowGraph(name=name, loop=True, loop_count=0)

    start = FlowNode(node_id="start", node_type=NodeType.START)
    graph.add_node(start)
    graph.start_node_id = "start"

    prev_id = "start"
    for i, action in enumerate(actions):
        nid = f"a_{i}"
        node = FlowNode(
            node_id=nid,
            node_type=NodeType.ACTION,
            action=action,
        )
        graph.add_node(node)
        graph.add_edge(FlowEdge(
            edge_id=f"e_{i}", from_node=prev_id, to_node=nid, label="default",
        ))
        prev_id = nid

    end = FlowNode(node_id="end", node_type=NodeType.END)
    graph.add_node(end)
    graph.add_edge(FlowEdge(
        edge_id="e_end", from_node=prev_id, to_node="end", label="default",
    ))

    return graph


def _create_dummy_png(path: Path) -> bytes:
    png_header = b"\x89PNG\r\n\x1a\n"
    ihdr_data = b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    ihdr_crc = b"\x90wS\xde"
    ihdr = b"\x00\x00\x00\r" + b"IHDR" + ihdr_data + ihdr_crc
    idat_data = b"\x08\xd7c\xf8\x0f\x00\x00\x01\x00\x01"
    idat_crc = b"\xe7\xb4\x81h"
    idat = b"\x00\x00\x00\n" + b"IDAT" + idat_data + idat_crc
    iend = b"\x00\x00\x00\x00" + b"IEND" + b"\xaeB`\x82"
    content = png_header + ihdr + idat + iend
    path.write_bytes(content)
    return content


@pytest.fixture
def tmp_output(tmp_path: Path) -> Path:
    return tmp_path / "exported.py"


@pytest.fixture
def tmp_templates(tmp_path: Path) -> Path:
    img_dir = tmp_path / "images"
    img_dir.mkdir()
    return img_dir


# ── 编译验证 ──────────────────────────────────────────────


class TestExportedScriptCompilation:
    """导出脚本必须是有效 Python 代码（可编译）"""

    def test_linear_graph_compiles(self, tmp_output: Path) -> None:
        actions = [
            STEP_CLASSES[ActionType.CLICK_POS](pos_x=100, pos_y=200),
            STEP_CLASSES[ActionType.WAIT](wait_seconds=1.0),
            STEP_CLASSES[ActionType.PRESS_KEY](key="enter"),
        ]
        graph = _make_linear_graph(actions)
        exporter = ScriptExporter()
        exporter.export(graph, tmp_output)

        script = tmp_output.read_text(encoding="utf-8")
        compile(script, str(tmp_output), "exec")

    def test_all_action_types_compile(self, tmp_output: Path) -> None:
        actions = [
            STEP_CLASSES[ActionType.CLICK_POS](pos_x=10, pos_y=20),
            STEP_CLASSES[ActionType.WAIT](wait_seconds=0.5),
            STEP_CLASSES[ActionType.WAIT_RANDOM](wait_min=0.1, wait_max=0.5),
            STEP_CLASSES[ActionType.PRESS_KEY](key="space"),
            STEP_CLASSES[ActionType.MOUSE_SCROLL](scroll_clicks=3),
            STEP_CLASSES[ActionType.HOLD_KEY](key="shift", hold_duration=1.0),
        ]
        graph = _make_linear_graph(actions)
        exporter = ScriptExporter()
        exporter.export(graph, tmp_output)

        script = tmp_output.read_text(encoding="utf-8")
        compile(script, str(tmp_output), "exec")

    def test_with_template_compiles(
        self, tmp_output: Path, tmp_templates: Path,
    ) -> None:
        _create_dummy_png(tmp_templates / "btn.png")

        actions = [
            STEP_CLASSES[ActionType.CLICK_IMAGE](image_path="btn.png"),
        ]
        graph = _make_linear_graph(actions)
        exporter = ScriptExporter(template_dir=tmp_templates)
        exporter.export(graph, tmp_output)

        script = tmp_output.read_text(encoding="utf-8")
        compile(script, str(tmp_output), "exec")

    def test_empty_action_list_compiles(self, tmp_output: Path) -> None:
        graph = _make_linear_graph([])
        exporter = ScriptExporter()
        exporter.export(graph, tmp_output)

        script = tmp_output.read_text(encoding="utf-8")
        compile(script, str(tmp_output), "exec")


# ── 结构验证 ──────────────────────────────────────────────


class TestExportedScriptStructure:
    """导出脚本必须包含完整的结构组件"""

    def test_has_shebang_and_encoding(self, tmp_output: Path) -> None:
        graph = _make_linear_graph([
            STEP_CLASSES[ActionType.CLICK_POS](pos_x=0, pos_y=0),
        ])
        exporter = ScriptExporter()
        exporter.export(graph, tmp_output)

        script = tmp_output.read_text(encoding="utf-8")
        assert script.startswith("#!/usr/bin/env python3")
        assert "# -*- coding: utf-8 -*-" in script

    def test_has_argparse_section(self, tmp_output: Path) -> None:
        graph = _make_linear_graph([
            STEP_CLASSES[ActionType.CLICK_POS](pos_x=0, pos_y=0),
        ])
        exporter = ScriptExporter()
        exporter.export(graph, tmp_output)

        script = tmp_output.read_text(encoding="utf-8")
        assert "argparse" in script
        assert "--loop" in script
        assert "--region" in script

    def test_has_main_guard(self, tmp_output: Path) -> None:
        graph = _make_linear_graph([
            STEP_CLASSES[ActionType.CLICK_POS](pos_x=0, pos_y=0),
        ])
        exporter = ScriptExporter()
        exporter.export(graph, tmp_output)

        script = tmp_output.read_text(encoding="utf-8")
        assert 'if __name__ == "__main__":' in script

    def test_template_base64_roundtrip(
        self, tmp_output: Path, tmp_templates: Path,
    ) -> None:
        img_data = _create_dummy_png(tmp_templates / "icon.png")

        actions = [
            STEP_CLASSES[ActionType.CLICK_IMAGE](image_path="icon.png"),
        ]
        graph = _make_linear_graph(actions)
        exporter = ScriptExporter(template_dir=tmp_templates)
        exporter.export(graph, tmp_output)

        script = tmp_output.read_text(encoding="utf-8")
        expected_b64 = base64.b64encode(img_data).decode("ascii")
        assert expected_b64 in script

    def test_profile_name_in_header(self, tmp_output: Path) -> None:
        graph = _make_linear_graph([
            STEP_CLASSES[ActionType.CLICK_POS](pos_x=0, pos_y=0),
        ])
        exporter = ScriptExporter()
        exporter.export(graph, tmp_output, profile_name="my_profile")

        script = tmp_output.read_text(encoding="utf-8")
        assert "my_profile" in script


# ── py_compile 验证 ───────────────────────────────────────


class TestExportedScriptSyntaxCheck:
    """使用 py_compile 进行语法检查"""

    def test_py_compile_valid(self, tmp_output: Path) -> None:
        import py_compile

        actions = [
            STEP_CLASSES[ActionType.CLICK_POS](pos_x=50, pos_y=75),
            STEP_CLASSES[ActionType.WAIT](wait_seconds=2.0),
            STEP_CLASSES[ActionType.PRESS_KEY](key="a"),
            STEP_CLASSES[ActionType.MOUSE_SCROLL](scroll_clicks=-2),
            STEP_CLASSES[ActionType.HOLD_KEY](key="ctrl", hold_duration=0.5),
        ]
        graph = _make_linear_graph(actions)
        exporter = ScriptExporter()
        exporter.export(graph, tmp_output)

        py_compile.compile(str(tmp_output), doraise=True)
