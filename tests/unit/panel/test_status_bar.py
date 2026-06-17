"""StatusBar 组件测试 — insert_segment 按位置插入段。"""

from __future__ import annotations

import pytest

tk = pytest.importorskip("tkinter")


@pytest.fixture
def tk_root():
    root = tk.Tk()
    root.withdraw()
    yield root
    root.destroy()


def test_default_segments(tk_root) -> None:
    from src.panel.components.status_bar import StatusBar

    bar = StatusBar(tk_root)
    # 默认段: [dot, left, center, right]
    assert len(bar._segments) == 4


def test_insert_segment_places_at_index(tk_root) -> None:
    from src.panel.components.status_bar import StatusBar

    bar = StatusBar(tk_root)
    lbl = bar.insert_segment(1, "exec_loop", "循环次数: 0/∞")
    assert bar._segment_labels["exec_loop"] is lbl
    # dot 仍在 0, 新段在 1
    assert bar._segments[0][0] == "dot"
    assert bar._segments[1] == ("label", lbl)
    assert lbl.cget("text") == "循环次数: 0/∞"


def test_set_segment_updates_text(tk_root) -> None:
    from src.panel.components.status_bar import StatusBar

    bar = StatusBar(tk_root)
    bar.insert_segment(1, "exec_step", "当前步骤: 1/3")
    bar.set_segment("exec_step", "当前步骤: 2/3")
    assert bar._segment_labels["exec_step"].cget("text") == "当前步骤: 2/3"


def test_insert_multiple_preserves_order(tk_root) -> None:
    from src.panel.components.status_bar import StatusBar

    bar = StatusBar(tk_root)
    loop_lbl = bar.insert_segment(1, "exec_loop", "")
    step_lbl = bar.insert_segment(2, "exec_step", "")
    time_lbl = bar.insert_segment(3, "exec_time", "")
    # [dot, loop, step, time, left, center, right]
    assert len(bar._segments) == 7
    assert bar._segments[1] == ("label", loop_lbl)
    assert bar._segments[2] == ("label", step_lbl)
    assert bar._segments[3] == ("label", time_lbl)
