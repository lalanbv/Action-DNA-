"""ScriptExporter 单元测试 — 导出 FlowGraph 为独立 Python 脚本"""

import base64
import os
import tempfile
import textwrap
from pathlib import Path

import pytest

from src.core.action import ActionType, DetectMode, FoundAction
from src.core.step_types import BaseStep, STEP_CLASSES
from src.core.flow import FlowEdge, FlowGraph, FlowNode, NodeType
from src.core.io.script_exporter import (
    ExportResult,
    GraphComplexity,
    ScriptExporter,
)


# ── Fixtures ──────────────────────────────────────────────


def _make_linear_graph(
    actions: list[BaseStep],
    name: str = "test_chain",
    loop: bool = True,
    loop_count: int = 0,
) -> FlowGraph:
    """创建线性 FlowGraph: START -> action* -> END"""
    graph = FlowGraph(name=name, loop=loop, loop_count=loop_count)

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
            comment=action.comment,
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

    if loop:
        graph.add_edge(FlowEdge(
            edge_id="e_loop", from_node="end", to_node="start", label="loop",
        ))

    return graph


def _make_branching_graph() -> FlowGraph:
    """创建带分支的复杂图（CONDITION 节点有两条出边）"""
    graph = FlowGraph(name="branching")

    start = FlowNode(node_id="start", node_type=NodeType.START)
    graph.add_node(start)
    graph.start_node_id = "start"

    cond = FlowNode(node_id="cond", node_type=NodeType.CONDITION)
    graph.add_node(cond)

    act_a = FlowNode(
        node_id="a_0",
        node_type=NodeType.ACTION,
        action=STEP_CLASSES[ActionType.PRESS_KEY](key="a"),
    )
    graph.add_node(act_a)

    act_b = FlowNode(
        node_id="a_1",
        node_type=NodeType.ACTION,
        action=STEP_CLASSES[ActionType.PRESS_KEY](key="b"),
    )
    graph.add_node(act_b)

    end = FlowNode(node_id="end", node_type=NodeType.END)
    graph.add_node(end)

    graph.add_edge(FlowEdge(edge_id="e1", from_node="start", to_node="cond"))
    graph.add_edge(FlowEdge(edge_id="e2", from_node="cond", to_node="a_0", label="true"))
    graph.add_edge(FlowEdge(edge_id="e3", from_node="cond", to_node="a_1", label="false"))
    graph.add_edge(FlowEdge(edge_id="e4", from_node="a_0", to_node="end"))
    graph.add_edge(FlowEdge(edge_id="e5", from_node="a_1", to_node="end"))

    return graph


def _make_loop_graph() -> FlowGraph:
    """创建带 LOOP 节点的图"""
    graph = FlowGraph(name="with_loop")

    start = FlowNode(node_id="start", node_type=NodeType.START)
    graph.add_node(start)
    graph.start_node_id = "start"

    loop_node = FlowNode(node_id="loop_0", node_type=NodeType.LOOP, loop_count=5)
    graph.add_node(loop_node)

    act = FlowNode(
        node_id="a_0",
        node_type=NodeType.ACTION,
        action=STEP_CLASSES[ActionType.PRESS_KEY](key="x"),
    )
    graph.add_node(act)

    end = FlowNode(node_id="end", node_type=NodeType.END)
    graph.add_node(end)

    graph.add_edge(FlowEdge(edge_id="e1", from_node="start", to_node="loop_0"))
    graph.add_edge(FlowEdge(edge_id="e2", from_node="loop_0", to_node="a_0"))
    graph.add_edge(FlowEdge(edge_id="e3", from_node="a_0", to_node="end"))

    return graph


@pytest.fixture
def tmp_output(tmp_path):
    """导出输出路径"""
    return tmp_path / "exported_script.py"


@pytest.fixture
def tmp_templates(tmp_path):
    """模板图片目录"""
    img_dir = tmp_path / "images"
    img_dir.mkdir()
    return img_dir


def _create_dummy_png(path: Path) -> bytes:
    """创建最小的有效 PNG 文件"""
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


# ── D15: 线性图导出 ───────────────────────────────────────


class TestLinearGraphExport:
    """D15: 线性图完整导出"""

    def test_empty_graph_raises(self, tmp_output):
        """空图（无节点）应抛出 ValueError"""
        graph = FlowGraph(name="empty")
        exporter = ScriptExporter()
        with pytest.raises(ValueError, match="START"):
            exporter.export(graph, tmp_output)

    def test_graph_without_start_raises(self, tmp_output):
        """只有 ACTION 节点无 START 应抛出 ValueError"""
        graph = FlowGraph(name="no_start")
        node = FlowNode(node_id="a_0", node_type=NodeType.ACTION)
        graph.add_node(node)
        graph.start_node_id = ""

        exporter = ScriptExporter()
        with pytest.raises(ValueError, match="START"):
            exporter.export(graph, tmp_output)

    def test_single_click_pos(self, tmp_output):
        """单个 CLICK_POS 步骤导出完整脚本"""
        actions = [
            STEP_CLASSES[ActionType.CLICK_POS](pos_x=100, pos_y=200),
        ]
        graph = _make_linear_graph(actions)
        exporter = ScriptExporter()
        result = exporter.export(graph, tmp_output)

        assert tmp_output.exists()
        script = tmp_output.read_text(encoding="utf-8")
        assert "#!/usr/bin/env python3" in script
        assert "100, 200" in script
        assert "safe_click" in script
        assert "run_loop" in script
        assert "if __name__" in script
        assert result.complexity == GraphComplexity.LINEAR

    def test_mixed_action_types(self, tmp_output):
        """混合动作类型导出"""
        actions = [
            STEP_CLASSES[ActionType.CLICK_POS](pos_x=50, pos_y=60),
            STEP_CLASSES[ActionType.WAIT](wait_seconds=2.0),
            STEP_CLASSES[ActionType.PRESS_KEY](key="enter"),
            STEP_CLASSES[ActionType.WAIT_RANDOM](wait_min=1.0, wait_max=3.0),
        ]
        graph = _make_linear_graph(actions)
        exporter = ScriptExporter()
        result = exporter.export(graph, tmp_output)

        script = tmp_output.read_text(encoding="utf-8")
        assert "step_1_click_pos" in script
        assert "step_2_wait" in script
        assert "step_3_press_key" in script
        assert "step_4_wait" in script
        assert result.node_count == 4

    def test_wait_random_export(self, tmp_output):
        """WAIT_RANDOM 导出为随机等待范围"""
        actions = [
            STEP_CLASSES[ActionType.WAIT_RANDOM](wait_min=0.5, wait_max=2.0),
        ]
        graph = _make_linear_graph(actions)
        exporter = ScriptExporter()
        exporter.export(graph, tmp_output)

        script = tmp_output.read_text(encoding="utf-8")
        assert "random_wait(0.5, 2.0)" in script

    def test_exports_valid_python(self, tmp_output):
        """导出的脚本应是有效 Python 语法"""
        actions = [
            STEP_CLASSES[ActionType.CLICK_POS](pos_x=0, pos_y=0),
            STEP_CLASSES[ActionType.WAIT](wait_seconds=1.0),
        ]
        graph = _make_linear_graph(actions)
        exporter = ScriptExporter()
        exporter.export(graph, tmp_output)

        script = tmp_output.read_text(encoding="utf-8")
        compile(script, str(tmp_output), "exec")

    def test_creates_output_directory(self, tmp_path):
        """输出目录不存在时自动创建"""
        output = tmp_path / "subdir" / "deep" / "script.py"
        actions = [
            STEP_CLASSES[ActionType.CLICK_POS](pos_x=0, pos_y=0),
        ]
        graph = _make_linear_graph(actions)
        exporter = ScriptExporter()
        exporter.export(graph, output)
        assert output.exists()

    def test_disabled_nodes_excluded(self, tmp_output):
        """disabled 节点不出现在导出脚本中"""
        actions = [
            STEP_CLASSES[ActionType.CLICK_POS](pos_x=10, pos_y=20, enabled=True),
            STEP_CLASSES[ActionType.PRESS_KEY](key="a", enabled=False),
            STEP_CLASSES[ActionType.CLICK_POS](pos_x=30, pos_y=40, enabled=True),
        ]
        graph = _make_linear_graph(actions)
        exporter = ScriptExporter()
        result = exporter.export(graph, tmp_output)

        script = tmp_output.read_text(encoding="utf-8")
        assert "step_1_click_pos" in script
        assert "step_2_click_pos" in script
        assert result.node_count == 2


# ── D16: 模板图片嵌入 ──────────────────────────────────────


class TestTemplateImageEmbedding:
    """D16: 图片打包到脚本"""

    def test_click_image_with_template(self, tmp_output, tmp_templates):
        """CLICK_IMAGE 步骤的模板图片以 base64 嵌入"""
        img_path = tmp_templates / "button.png"
        img_data = _create_dummy_png(img_path)

        actions = [
            STEP_CLASSES[ActionType.CLICK_IMAGE](
                image_path="button.png",
                threshold=0.85,
            ),
        ]
        graph = _make_linear_graph(actions)
        exporter = ScriptExporter(template_dir=tmp_templates)
        exporter.export(graph, tmp_output)

        script = tmp_output.read_text(encoding="utf-8")
        assert "TEMPLATES" in script
        assert "button.png" in script
        assert "base64.b64decode" in script

        expected_b64 = base64.b64encode(img_data).decode("ascii")
        assert expected_b64 in script

    def test_click_image_missing_template(self, tmp_output, tmp_templates):
        """模板图片不存在时仍能导出（图片字段为空）"""
        actions = [
            STEP_CLASSES[ActionType.CLICK_IMAGE](
                image_path="nonexistent.png",
            ),
        ]
        graph = _make_linear_graph(actions)
        exporter = ScriptExporter(template_dir=tmp_templates)
        exporter.export(graph, tmp_output)

        script = tmp_output.read_text(encoding="utf-8")
        assert "TEMPLATES" in script

    def test_multiple_templates(self, tmp_output, tmp_templates):
        """多个模板图片全部嵌入"""
        for name in ["btn1.png", "btn2.png", "btn3.png"]:
            _create_dummy_png(tmp_templates / name)

        actions = [
            STEP_CLASSES[ActionType.CLICK_IMAGE](image_path="btn1.png"),
            STEP_CLASSES[ActionType.WAIT](wait_seconds=0.5),
            STEP_CLASSES[ActionType.CLICK_IMAGE](image_path="btn2.png"),
            STEP_CLASSES[ActionType.CLICK_IMAGE](image_path="btn3.png"),
        ]
        graph = _make_linear_graph(actions)
        exporter = ScriptExporter(template_dir=tmp_templates)
        exporter.export(graph, tmp_output)

        script = tmp_output.read_text(encoding="utf-8")
        assert "btn1.png" in script
        assert "btn2.png" in script
        assert "btn3.png" in script

    def test_no_template_dir(self, tmp_output):
        """无模板目录时，CLICK_IMAGE 步骤跳过图片嵌入"""
        actions = [
            STEP_CLASSES[ActionType.CLICK_IMAGE](image_path="img.png"),
        ]
        graph = _make_linear_graph(actions)
        exporter = ScriptExporter(template_dir=None)
        exporter.export(graph, tmp_output)

        script = tmp_output.read_text(encoding="utf-8")
        assert "TEMPLATES" in script
        assert 'TEMPLATES["img.png"]' not in script


# ── D17: 复杂图警告 ────────────────────────────────────────


class TestComplexGraphWarning:
    """D17: 分支/循环图提示不支持"""

    def test_branching_graph_returns_warning(self, tmp_output):
        """分支图导出返回 BRANCHING 复杂度 + 警告消息"""
        graph = _make_branching_graph()
        exporter = ScriptExporter()
        result = exporter.export(graph, tmp_output)

        assert result.complexity == GraphComplexity.BRANCHING
        assert len(result.warnings) > 0
        assert any("分支" in w or "branch" in w.lower() for w in result.warnings)

    def test_loop_graph_returns_warning(self, tmp_output):
        """LOOP 节点图导出返回 COMPLEX 复杂度 + 警告"""
        graph = _make_loop_graph()
        exporter = ScriptExporter()
        result = exporter.export(graph, tmp_output)

        assert result.complexity in (GraphComplexity.COMPLEX, GraphComplexity.BRANCHING)
        assert len(result.warnings) > 0

    def test_linear_graph_no_warnings(self, tmp_output):
        """线性图导出无警告"""
        actions = [
            STEP_CLASSES[ActionType.CLICK_POS](pos_x=0, pos_y=0),
        ]
        graph = _make_linear_graph(actions)
        exporter = ScriptExporter()
        result = exporter.export(graph, tmp_output)

        assert result.complexity == GraphComplexity.LINEAR
        assert len(result.warnings) == 0

    def test_branching_graph_still_exports(self, tmp_output):
        """分支图仍能导出脚本（取第一条路径）"""
        graph = _make_branching_graph()
        exporter = ScriptExporter()
        result = exporter.export(graph, tmp_output)

        assert tmp_output.exists()
        script = tmp_output.read_text(encoding="utf-8")
        assert "#!/usr/bin/env python3" in script

    def test_analyze_complexity_before_export(self, tmp_output):
        """可以在导出前分析图复杂度"""
        graph = _make_branching_graph()
        exporter = ScriptExporter()
        complexity = exporter.analyze_complexity(graph)

        assert complexity != GraphComplexity.LINEAR

    def test_condition_node_detected(self, tmp_output):
        """CONDITION 节点被检测为复杂图"""
        graph = _make_branching_graph()
        exporter = ScriptExporter()
        complexity = exporter.analyze_complexity(graph)
        assert complexity == GraphComplexity.BRANCHING


# ── ExportResult ──────────────────────────────────────────


class TestExportResult:
    """导出结果数据类"""

    def test_result_fields(self, tmp_output):
        """ExportResult 包含所有必要字段"""
        actions = [
            STEP_CLASSES[ActionType.CLICK_POS](pos_x=0, pos_y=0),
        ]
        graph = _make_linear_graph(actions)
        exporter = ScriptExporter()
        result = exporter.export(graph, tmp_output)

        assert isinstance(result, ExportResult)
        assert isinstance(result.output_path, Path)
        assert isinstance(result.complexity, GraphComplexity)
        assert isinstance(result.warnings, list)
        assert isinstance(result.node_count, int)
        assert isinstance(result.template_count, int)

    def test_result_counts(self, tmp_output, tmp_templates):
        """ExportResult 正确计数节点和模板"""
        _create_dummy_png(tmp_templates / "img.png")

        actions = [
            STEP_CLASSES[ActionType.CLICK_IMAGE](image_path="img.png"),
            STEP_CLASSES[ActionType.WAIT](wait_seconds=1.0),
            STEP_CLASSES[ActionType.PRESS_KEY](key="enter"),
        ]
        graph = _make_linear_graph(actions)
        exporter = ScriptExporter(template_dir=tmp_templates)
        result = exporter.export(graph, tmp_output)

        assert result.node_count == 3
        assert result.template_count == 1


class TestJsonExport:
    """JSON 宏脚本导出测试。"""

    def test_export_json_basic(self):
        """基本 JSON 导出包含版本和元数据。"""
        import json
        steps = [
            STEP_CLASSES[ActionType.PRESS_KEY](key="a"),
            STEP_CLASSES[ActionType.WAIT](wait_seconds=1.0),
        ]
        exporter = ScriptExporter()
        result = exporter.export_json(steps)
        data = json.loads(result)
        assert data["version"] == "2.0"
        assert "meta" in data
        assert len(data["steps"]) == 2

    def test_export_json_with_text(self):
        """文本输入步骤导出 text 字段。"""
        import json
        steps = [
            STEP_CLASSES[ActionType.PRESS_KEY](text="hello"),
        ]
        exporter = ScriptExporter()
        result = exporter.export_json(steps)
        data = json.loads(result)
        assert data["steps"][0]["text"] == "hello"
        assert "key" not in data["steps"][0]

    def test_export_json_scroll_bidirectional(self):
        """滚动步骤导出双向数据。"""
        import json
        steps = [
            STEP_CLASSES[ActionType.MOUSE_SCROLL](
                scroll_clicks=3,
                scroll_delta_x=-2,
            ),
        ]
        exporter = ScriptExporter()
        result = exporter.export_json(steps)
        data = json.loads(result)
        assert data["steps"][0]["clicks"] == 3
        assert data["steps"][0]["horizontal"] == -2

    def test_json_round_trip(self):
        """JSON 导出 → 导入往返。"""
        from src.core.io.importer import MacroImporter
        steps = [
            STEP_CLASSES[ActionType.PRESS_KEY](text="hello"),
            STEP_CLASSES[ActionType.MOUSE_SCROLL](scroll_clicks=3, scroll_delta_x=-2),
            STEP_CLASSES[ActionType.CLICK_POS](pos_x=100, pos_y=200, clicks=2),
            STEP_CLASSES[ActionType.WAIT](wait_seconds=1.5),
        ]
        exporter = ScriptExporter()
        json_str = exporter.export_json(steps)
        importer = MacroImporter()
        imported = importer.import_json(json_str)
        assert len(imported) == 4
        assert imported[0].text == "hello"
        assert imported[1].scroll_clicks == 3
        assert imported[1].scroll_delta_x == -2
        assert imported[2].pos_x == 100
        assert imported[2].clicks == 2
        assert imported[3].wait_seconds == 1.5

    def test_import_rejects_bad_version(self):
        """导入拒绝不支持的版本。"""
        from src.core.io.importer import MacroImporter
        importer = MacroImporter()
        with pytest.raises(ValueError, match="不支持的宏脚本版本"):
            importer.import_json('{"version": "1.0", "steps": []}')
