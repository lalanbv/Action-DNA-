"""Phase 5 向后兼容回归测试 — 视觉检测描述符 + 录制桥接。

验证：
- 新描述符注册不影响已有描述符
- 旧配置正常执行
- RecordBridge 事件→步骤转换正确
"""

import threading
from unittest.mock import MagicMock

import numpy as np

from src.core.action import ActionType
from src.core.step_types import BaseStep, STEP_CLASSES
from src.core.engine.descriptors import (
    PixelSearchDescriptor,
    OCRDescriptor,
)
from src.core.engine.descriptors.record_descriptor import RecordBridge
from src.core.engine.execution_context import ExecutionContext
from src.core.engine.node_registry import NodeRegistry
from src.core.flow import FlowEdge, FlowGraph, FlowNode, NodeType
from src.core.variables.pool import VariablePool


# ── 辅助 ──────────────────────────────────────────────────


def _make_ctx(
    graph: FlowGraph,
    node: FlowNode,
    extra: dict | None = None,
) -> ExecutionContext:
    capture = MagicMock()
    capture.capture.return_value = np.zeros((100, 100, 3), dtype=np.uint8)
    pool = VariablePool()
    stop_evt = threading.Event()
    pause_evt = threading.Event()
    return ExecutionContext(
        graph=graph,
        current_node=node,
        variables=pool,
        capture=capture,
        matcher=MagicMock(),
        input_ctrl=MagicMock(),
        gen=0,
        stop_event=stop_evt,
        pause_event=pause_evt,
        extra=extra or {},
    )


def _make_graph(
    action: BaseStep,
    node_id: str = "action",
) -> tuple[FlowGraph, FlowNode]:
    """构造 start → action → end 的简单图，返回 (graph, action_node)。"""
    start = FlowNode(node_id="start", node_type=NodeType.START)
    action_node = FlowNode(node_id=node_id, node_type=NodeType.ACTION, action=action)
    end = FlowNode(node_id="end", node_type=NodeType.END)

    graph = FlowGraph(
        name="test",
        nodes={n.node_id: n for n in [start, action_node, end]},
        edges=[
            FlowEdge(edge_id="e1", from_node="start", to_node=node_id),
            FlowEdge(edge_id="e2", from_node=node_id, to_node="end"),
        ],
        start_node_id="start",
    )
    return graph, action_node


# ============================================================
# 描述符注册兼容性
# ============================================================


class TestDescriptorRegistrationCompat:
    def test_pixel_search_registered(self) -> None:
        desc = NodeRegistry.get("PIXEL_SEARCH")
        assert desc is not None
        assert desc.action_type() == "PIXEL_SEARCH"

    def test_ocr_registered(self) -> None:
        desc = NodeRegistry.get("OCR_CHECK")
        assert desc is not None
        assert desc.action_type() == "OCR_CHECK"

    def test_existing_descriptors_still_work(self) -> None:
        """Phase 5 描述符注册不影响已有描述符"""
        for action_type in ("START", "END", "WAIT", "WAIT_RANDOM",
                            "PRESS_KEY", "CLICK_POS", "CLICK_IMAGE"):
            desc = NodeRegistry.get(action_type)
            assert desc is not None, f"{action_type} 描述符丢失"


# ============================================================
# PixelSearchDescriptor 执行
# ============================================================


class TestPixelSearchDescriptorCompat:
    def test_execute_returns_result(self) -> None:
        pixel_searcher = MagicMock()
        from src.core.vision.pixel_result import PixelSearchResult
        pixel_searcher.search.return_value = PixelSearchResult.found_pixels(
            [(50, 60)]
        )

        action = STEP_CLASSES[ActionType.PIXEL_SEARCH](
            target_color=(0, 0, 255),
            color_tolerance=10,
            color_mode="hsv",
        )

        graph, node = _make_graph(action, "px1")
        ctx = _make_ctx(graph, node, extra={"pixel_searcher": pixel_searcher})

        desc = PixelSearchDescriptor()
        result = desc.execute(ctx)
        assert result.success is True
        assert result.output_vars["found"] is True
        assert result.output_vars["position"] == (50, 60)

    def test_execute_missing_searcher(self) -> None:
        action = STEP_CLASSES[ActionType.PIXEL_SEARCH](
            target_color=(0, 0, 255),
            color_mode="hsv",
        )

        graph, node = _make_graph(action, "px2")
        ctx = _make_ctx(graph, node, extra={})

        desc = PixelSearchDescriptor()
        result = desc.execute(ctx)
        assert result.success is False


# ============================================================
# OCRDescriptor 执行
# ============================================================


class TestOCRDescriptorCompat:
    def test_execute_with_text_search(self) -> None:
        from src.core.vision.ocr_result import OCRResult

        ocr_recognizer = MagicMock()
        ocr_recognizer.find_text.return_value = OCRResult(
            text="开始游戏", confidence=0.95, bounding_box=(10, 20, 80, 30),
        )

        action = STEP_CLASSES[ActionType.OCR_CHECK](
            target_text="开始",
            ocr_fuzzy=True,
        )

        graph, node = _make_graph(action, "ocr1")
        ctx = _make_ctx(graph, node, extra={"ocr_recognizer": ocr_recognizer})

        desc = OCRDescriptor()
        result = desc.execute(ctx)
        assert result.success is True
        assert result.output_vars["found"] is True
        assert "开始" in result.output_vars["text"]

    def test_execute_missing_recognizer_graceful(self) -> None:
        """OCR recognizer 未注入时优雅降级"""
        action = STEP_CLASSES[ActionType.OCR_CHECK](
            target_text="测试",
            ocr_fuzzy=True,
        )

        graph, node = _make_graph(action, "ocr2")
        ctx = _make_ctx(graph, node, extra={})

        desc = OCRDescriptor()
        result = desc.execute(ctx)
        assert result.success is True
        assert result.output_vars["found"] is False


# ============================================================
# RecordBridge 兼容性
# ============================================================


class TestRecordBridgeCompat:
    def test_convert_click_events_to_steps(self) -> None:
        from src.recorder.recorder import RecordedEvent

        events = [
            RecordedEvent(event_type="mouse_down", x=100, y=200, button="left", timestamp=0.0),
            RecordedEvent(event_type="mouse_up", x=100, y=200, button="left", timestamp=0.05),
        ]

        bridge = RecordBridge()
        steps = bridge.convert_events(events)
        assert len(steps) == 1
        assert steps[0].action_type == ActionType.CLICK_POS
        assert steps[0].pos_x == 100
        assert steps[0].pos_y == 200

    def test_convert_key_events_to_steps(self) -> None:
        from src.recorder.recorder import RecordedEvent

        events = [
            RecordedEvent(event_type="key_down", key="a", timestamp=0.0),
            RecordedEvent(event_type="key_up", key="a", timestamp=0.05),
        ]

        bridge = RecordBridge()
        steps = bridge.convert_events(events)
        assert len(steps) == 1
        assert steps[0].action_type == ActionType.PRESS_KEY
        assert steps[0].key == "a"

    def test_initial_state(self) -> None:
        bridge = RecordBridge()
        assert bridge.is_recording is False
        assert bridge.event_count == 0
        assert bridge.duration == 0.0


# ============================================================
# FlowGraph 序列化兼容性（含新节点类型）
# ============================================================


class TestFlowGraphSerializationCompat:
    def test_export_import_with_pixel_search(self, tmp_path: str) -> None:
        from src.core.serialization import (
            dict_to_flow_edge,
            dict_to_flow_node,
            flow_edge_to_dict,
            flow_node_to_dict,
        )

        action = STEP_CLASSES[ActionType.PIXEL_SEARCH](
            target_color=(0, 0, 255),
            color_tolerance=10,
            color_mode="hsv",
        )

        graph, _ = _make_graph(action, "px")

        # 直接用 serialization 函数做 round-trip
        profile_dir = str(tmp_path)
        node_dicts = [flow_node_to_dict(n) for n in graph.nodes.values()]
        edge_dicts = [flow_edge_to_dict(e) for e in graph.edges]

        restored_nodes = {nd["node_id"]: dict_to_flow_node(nd, profile_dir) for nd in node_dicts}
        restored_edges = [dict_to_flow_edge(ed) for ed in edge_dicts]

        restored = FlowGraph(
            name=graph.name,
            nodes=restored_nodes,
            edges=restored_edges,
            start_node_id=graph.start_node_id,
        )

        px_node = restored.nodes.get("px")
        assert px_node is not None
        assert px_node.action is not None
        assert px_node.action.action_type == ActionType.PIXEL_SEARCH

    def test_export_import_with_ocr(self, tmp_path: str) -> None:
        from src.core.serialization import (
            dict_to_flow_edge,
            dict_to_flow_node,
            flow_edge_to_dict,
            flow_node_to_dict,
        )

        action = STEP_CLASSES[ActionType.OCR_CHECK](
            target_text="HP",
            ocr_fuzzy=True,
        )

        graph, _ = _make_graph(action, "ocr")

        profile_dir = str(tmp_path)
        node_dicts = [flow_node_to_dict(n) for n in graph.nodes.values()]
        edge_dicts = [flow_edge_to_dict(e) for e in graph.edges]

        restored_nodes = {nd["node_id"]: dict_to_flow_node(nd, profile_dir) for nd in node_dicts}
        restored_edges = [dict_to_flow_edge(ed) for ed in edge_dicts]

        restored = FlowGraph(
            name=graph.name,
            nodes=restored_nodes,
            edges=restored_edges,
            start_node_id=graph.start_node_id,
        )

        ocr_node = restored.nodes.get("ocr")
        assert ocr_node is not None
        assert ocr_node.action.action_type == ActionType.OCR_CHECK
        assert ocr_node.action.target_text == "HP"
