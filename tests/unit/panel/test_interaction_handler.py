"""InteractionHandler 单元测试 — 多选拖拽、框选、Shift点击、右键菜单、中键平移。

验证交互状态机的选中/取消选中/多选拖拽/框选/右键菜单/中键平移行为。
Canvas 通过 mock 隔离，无需真实 GUI。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.core.flow import FlowGraph, FlowNode, NodeType
from src.panel.canvas.interaction_handler import (
    InteractionHandler,
    InteractionMode,
    _SELECT_MODIFY_MASK,
    _SHIFT_MASK,
)


# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture
def graph() -> FlowGraph:
    g = FlowGraph()
    g.add_node(FlowNode(node_id="start", node_type=NodeType.START, pos_x=100, pos_y=100))
    g.add_node(FlowNode(node_id="a1", node_type=NodeType.ACTION, pos_x=300, pos_y=200))
    g.add_node(FlowNode(node_id="a2", node_type=NodeType.ACTION, pos_x=300, pos_y=350))
    g.add_node(FlowNode(node_id="a3", node_type=NodeType.ACTION, pos_x=500, pos_y=200))
    g.add_node(FlowNode(node_id="end", node_type=NodeType.END, pos_x=300, pos_y=500))
    return g


@pytest.fixture
def mock_canvas() -> MagicMock:
    canvas = MagicMock()
    canvas.find_overlapping.return_value = []
    canvas.find_closest.return_value = None
    canvas.gettags.return_value = ()
    canvas.bbox.return_value = None
    canvas.winfo_width.return_value = 800
    canvas.winfo_height.return_value = 600
    # 坐标变换: screen = (world - 0) * 1.0
    canvas.screen_to_world.side_effect = lambda sx, sy: (float(sx), float(sy))
    canvas.world_to_screen.side_effect = lambda wx, wy: (float(wx), float(wy))
    return canvas


@pytest.fixture
def handler(mock_canvas: MagicMock, graph: FlowGraph) -> InteractionHandler:
    cb = MagicMock()
    h = InteractionHandler(
        canvas=mock_canvas,
        get_graph=lambda: graph,
        get_viewport=lambda: (0.0, 0.0, 1.0),
        event_callback=cb,
        snap_to_grid=False,
    )
    return h


def _make_event(x: int = 0, y: int = 0, state: int = 0, **kw):
    """创建一个模拟的 tkinter Event"""
    evt = MagicMock()
    evt.x = x
    evt.y = y
    evt.state = state
    evt.x_root = x
    evt.y_root = y
    evt.delta = 0
    for k, v in kw.items():
        setattr(evt, k, v)
    return evt


def _hit_node(canvas: MagicMock, node_id: str):
    """让 hit_test 返回 node 命中"""
    tag = f"node:{node_id}"

    def find_overlapping(x1, y1, x2, y2):
        return [1]

    canvas.find_overlapping.side_effect = find_overlapping
    canvas.gettags.side_effect = lambda item_id: (tag,)
    canvas.find_closest.return_value = None


def _hit_canvas(canvas: MagicMock):
    """让 hit_test 返回空画布"""
    canvas.find_overlapping.return_value = []
    canvas.find_closest.return_value = None
    canvas.gettags.return_value = ()
    canvas.bbox.return_value = None


# ── 选中状态 ──────────────────────────────────────────────


class TestSelection:
    def test_click_node_selects_single(self, handler: InteractionHandler, mock_canvas: MagicMock):
        _hit_node(mock_canvas, "a1")
        handler._on_press(_make_event(x=300, y=200))
        assert handler.get_selected_nodes() == {"a1"}
        handler._callback.assert_called_with("node_selected", node_id="a1")

    def test_click_empty_deselects(self, handler: InteractionHandler, mock_canvas: MagicMock):
        handler._selected_node_ids = {"a1"}
        _hit_canvas(mock_canvas)
        handler._start_selecting(_make_event(x=10, y=10))
        handler._end_select(_make_event(x=12, y=12))  # < 5px = click
        assert handler.get_selected_nodes() == set()
        handler._callback.assert_called_with("canvas_deselected")


class TestShiftClickToggle:
    def test_shift_click_adds_to_selection(self, handler: InteractionHandler, mock_canvas: MagicMock):
        handler._selected_node_ids = {"a1"}
        _hit_node(mock_canvas, "a2")
        handler._on_press(_make_event(x=300, y=350, state=_SHIFT_MASK))
        assert handler.get_selected_nodes() == {"a1", "a2"}
        call_kwargs = handler._callback.call_args
        assert call_kwargs.args[0] == "nodes_selected"
        assert set(call_kwargs.kwargs["node_ids"]) == {"a1", "a2"}

    def test_shift_click_removes_from_selection(self, handler: InteractionHandler, mock_canvas: MagicMock):
        handler._selected_node_ids = {"a1", "a2"}
        _hit_node(mock_canvas, "a1")
        handler._on_press(_make_event(x=300, y=200, state=_SHIFT_MASK))
        assert handler.get_selected_nodes() == {"a2"}
        handler._callback.assert_called_with("node_selected", node_id="a2")

    def test_shift_click_toggle_to_empty(self, handler: InteractionHandler, mock_canvas: MagicMock):
        handler._selected_node_ids = {"a1"}
        _hit_node(mock_canvas, "a1")
        handler._on_press(_make_event(x=300, y=200, state=_SHIFT_MASK))
        assert handler.get_selected_nodes() == set()
        handler._callback.assert_called_with("canvas_deselected")

    def test_ctrl_click_also_toggles(self, handler: InteractionHandler, mock_canvas: MagicMock):
        handler._selected_node_ids = {"a1"}
        _hit_node(mock_canvas, "a2")
        handler._on_press(_make_event(x=300, y=350, state=_SELECT_MODIFY_MASK))
        assert handler.get_selected_nodes() == {"a1", "a2"}


class TestRubberBandSelection:
    def test_drag_selects_nodes_in_rect(self, handler: InteractionHandler, mock_canvas: MagicMock):
        _hit_canvas(mock_canvas)
        handler._start_selecting(_make_event(x=100, y=100))
        # 模拟拖拽覆盖 a1 和 a2 区域
        handler._end_select(_make_event(x=400, y=400))
        assert "a1" in handler.get_selected_nodes()
        assert "a2" in handler.get_selected_nodes()
        handler._callback.assert_called_with("nodes_selected", node_ids=list(handler.get_selected_nodes()))

    def test_drag_without_shift_replaces_selection(self, handler: InteractionHandler, mock_canvas: MagicMock):
        handler._selected_node_ids = {"a3"}
        _hit_canvas(mock_canvas)
        handler._start_selecting(_make_event(x=100, y=100))
        handler._end_select(_make_event(x=400, y=400))
        assert "a3" not in handler.get_selected_nodes()
        assert "a1" in handler.get_selected_nodes()

    def test_drag_with_shift_adds_to_selection(self, handler: InteractionHandler, mock_canvas: MagicMock):
        handler._selected_node_ids = {"a3"}
        _hit_canvas(mock_canvas)
        handler._start_selecting(_make_event(x=100, y=100, state=_SHIFT_MASK))
        handler._end_select(_make_event(x=400, y=400))
        assert "a3" in handler.get_selected_nodes()
        assert "a1" in handler.get_selected_nodes()


class TestMultiDrag:
    def test_drag_selected_node_keeps_multi(self, handler: InteractionHandler, mock_canvas: MagicMock):
        handler._selected_node_ids = {"a1", "a2"}
        _hit_node(mock_canvas, "a1")
        handler._on_press(_make_event(x=300, y=200))
        assert handler._mode == InteractionMode.DRAGGING_NODE
        assert handler.get_selected_nodes() == {"a1", "a2"}

    def test_click_unselected_node_replaces(self, handler: InteractionHandler, mock_canvas: MagicMock):
        handler._selected_node_ids = {"a1", "a2"}
        _hit_node(mock_canvas, "a3")
        handler._on_press(_make_event(x=500, y=200))
        assert handler.get_selected_nodes() == {"a3"}


class TestSelectAll:
    def test_select_all(self, handler: InteractionHandler):
        result = handler.select_all()
        assert result == {"start", "a1", "a2", "a3", "end"}
        handler._callback.assert_called_with(
            "nodes_selected", node_ids=list(result)
        )


class TestContextMenuAndMiddlePan:
    def test_right_click_shows_context_menu(self, handler: InteractionHandler, mock_canvas: MagicMock):
        # Click at (50, 50) — away from all nodes — to get canvas_context_menu
        handler._on_right_click(_make_event(x=50, y=50))
        handler._do_show_context_menu()
        handler._callback.assert_called_once()
        call_args = handler._callback.call_args
        assert call_args.args[0] == "canvas_context_menu"
        assert handler._mode == InteractionMode.IDLE

    def test_middle_click_starts_pan(self, handler: InteractionHandler, mock_canvas: MagicMock):
        handler._on_middle_press(_make_event(x=100, y=100))
        assert handler._mode == InteractionMode.PANNING
        handler._on_middle_motion(_make_event(x=120, y=110))
        handler._callback.assert_called_with("pan_request", dx=20, dy=10)


class TestEscapeKey:
    def test_escape_clears_selection(self, handler: InteractionHandler, mock_canvas: MagicMock):
        handler._selected_node_ids = {"a1", "a2"}
        handler._on_key_escape(_make_event())
        assert handler.get_selected_nodes() == set()
        # Should call both canvas_deselected and escape
        call_types = [c.args[0] for c in handler._callback.call_args_list]
        assert "canvas_deselected" in call_types
        assert "escape" in call_types


class TestDeleteKey:
    def test_delete_selected_nodes(self, handler: InteractionHandler, mock_canvas: MagicMock):
        handler._selected_node_ids = {"a1", "a2"}
        handler._on_key_delete(_make_event())
        call_kwargs = handler._callback.call_args
        assert call_kwargs.args[0] == "delete_selected"
        assert set(call_kwargs.kwargs["node_ids"]) == {"a1", "a2"}


class TestRightClickMultiSelect:
    def test_right_click_keeps_multi_selection(self, handler: InteractionHandler, mock_canvas: MagicMock):
        handler._selected_node_ids = {"a1", "a2", "a3"}
        _hit_node(mock_canvas, "a1")
        # Simulate _show_context_menu flow
        handler._show_context_menu(300, 200, 300, 200)
        # Multi-selection should be preserved
        assert handler.get_selected_nodes() == {"a1", "a2", "a3"}

    def test_right_click_single_selects_node(self, handler: InteractionHandler, mock_canvas: MagicMock):
        handler._selected_node_ids = {"a1"}
        _hit_node(mock_canvas, "a2")
        handler._show_context_menu(300, 350, 300, 350)
        assert handler.get_selected_nodes() == {"a2"}


class TestEdgeSelection:
    def test_select_edge_twice_stays_selected(self, handler: InteractionHandler, mock_canvas: MagicMock):
        """Re-clicking a selected edge should keep it selected (no toggle-deselect)."""
        handler._select_edge("e1")
        assert handler.get_selected_edge() == "e1"
        handler._callback.assert_called_with("edge_selected", edge_id="e1")
        handler._callback.reset_mock()
        # Click same edge again — should stay selected
        handler._select_edge("e1")
        assert handler.get_selected_edge() == "e1"
        handler._callback.assert_not_called()

    def test_select_different_edge_replaces(self, handler: InteractionHandler, mock_canvas: MagicMock):
        handler._select_edge("e1")
        handler._select_edge("e2")
        assert handler.get_selected_edge() == "e2"
        calls = [c.args[0] for c in handler._callback.call_args_list]
        assert calls == ["edge_selected", "edge_deselected", "edge_selected"]


class TestSamplePolyline:
    def test_two_segment_polyline_start(self):
        from src.panel.canvas._interaction_hit_test import _sample_polyline
        pts = (0, 0, 50, 0, 50, 100)
        x, y = _sample_polyline(pts, 0.0)
        assert abs(x - 0) < 0.01 and abs(y - 0) < 0.01

    def test_two_segment_polyline_end(self):
        from src.panel.canvas._interaction_hit_test import _sample_polyline
        pts = (0, 0, 50, 0, 50, 100)
        x, y = _sample_polyline(pts, 1.0)
        assert abs(x - 50) < 0.01 and abs(y - 100) < 0.01

    def test_two_segment_polyline_midpoint(self):
        from src.panel.canvas._interaction_hit_test import _sample_polyline
        pts = (0, 0, 50, 0, 50, 100)
        x, y = _sample_polyline(pts, 0.5)
        # t=0.5 is at the corner (50, 0)
        assert abs(x - 50) < 0.01 and abs(y - 0) < 0.01

    def test_single_segment(self):
        from src.panel.canvas._interaction_hit_test import _sample_polyline
        pts = (0, 0, 100, 200)
        x, y = _sample_polyline(pts, 0.5)
        assert abs(x - 50) < 0.01 and abs(y - 100) < 0.01
