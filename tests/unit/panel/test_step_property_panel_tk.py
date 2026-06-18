"""tk 步骤详情面板渲染冒烟测试（规格与 Qt 端一致）。

注意：macOS Tk9+Py3.14 多 Tk root 不稳，用 module-scoped 单 root；须逐文件跑。
"""

from __future__ import annotations

import tkinter as tk

import pytest

from src.core.action import ActionType
from src.core.step_types import STEP_CLASSES
from src.panel.components.step_property_panel import StepPropertyPanel


@pytest.fixture(scope="module")
def tk_root():
    root = tk.Tk()
    root.withdraw()
    yield root
    root.destroy()


def _collect_texts(widget) -> list[str]:
    out: list[str] = []
    for child in widget.winfo_children():
        if isinstance(child, (tk.Label, tk.Button)):
            out.append(str(child.cget("text")))
        out.extend(_collect_texts(child))
    return out


def _make_panel(root, **extra) -> StepPropertyPanel:
    base = dict(
        on_move_up=lambda: None, on_move_down=lambda: None,
        on_edit=lambda: None, on_delete=lambda: None,
        on_enabled_change=lambda: None,
    )
    base.update(extra)
    return StepPropertyPanel(root, **base)


def test_renders_summary_key_params_all_fields(tk_root) -> None:
    panel = _make_panel(
        tk_root, on_duplicate=lambda: None, on_move_to_index=lambda t: None,
    )
    step = STEP_CLASSES[ActionType.CLICK_IMAGE]()
    step.image_path = "/x/y/btn.png"
    panel.show_step(step, 0, 2)
    texts = _collect_texts(panel)
    assert any("关键参数" in tx for tx in texts)
    assert any("全部字段" in tx for tx in texts)
    assert any("btn.png" in tx for tx in texts)


def test_move_to_and_duplicate_when_multi(tk_root) -> None:
    panel = _make_panel(
        tk_root, on_duplicate=lambda: None, on_move_to_index=lambda t: None,
    )
    panel.show_step(STEP_CLASSES[ActionType.WAIT](), 0, 3)
    texts = _collect_texts(panel)
    assert any("移动到序号" in tx for tx in texts)
    assert any("复制" in tx for tx in texts)


def test_move_to_hidden_when_single(tk_root) -> None:
    panel = _make_panel(tk_root)
    panel.show_step(STEP_CLASSES[ActionType.WAIT](), 0, 1)
    texts = _collect_texts(panel)
    assert not any("移动到序号" in tx for tx in texts)
