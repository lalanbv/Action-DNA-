"""共享测试夹具 — _FakeFlowNode 和 _make_ctx 统一定义。

所有描述符测试文件共用，消除重复的 FlowNode 替身和上下文构建代码。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

import numpy as np

_NO_CAPTURE = object()


@dataclass
class _FakeFlowNode:
    """最小化 FlowNode 替身 — 覆盖所有描述符测试所需的字段超集。"""

    action: object | None = None
    node_id: str = "test_node"
    node_type: Any = None
    condition: Any = None
    comment: str = ""
    enabled: bool = True
    loop_count: int = 0


def _make_ctx(
    *,
    action: object | None = None,
    node_id: str = "test_node",
    node_type: Any = None,
    condition: Any = None,
    loop_count: int = 0,
    match_result: Any = _NO_CAPTURE,
    stop: bool = False,
    pause: bool = False,
    gen: int = 0,
    evaluator: Any = None,
    input_ctrl: MagicMock | None = None,
    extra: dict[str, Any] | None = None,
) -> MagicMock:
    """构建模拟 ExecutionContext。

    参数说明:
    - action: 节点的步骤对象，传入 _FakeFlowNode.action
    - node_id/node_type/condition/loop_count: 传入 _FakeFlowNode 对应字段
    - match_result: 控制 capture/matcher 设置
        - _NO_CAPTURE (默认): 不设置 capture/matcher
        - tuple: 设置 capture.grab → 假截图, matcher.find → 返回该 tuple
        - None: 设置 capture/matcher 但 find 返回 None
    - stop/pause: stop_event/pause_event 的 is_set 初始值
    - gen: 上下文的 gen 值
    - evaluator: ConditionEvaluator mock
    - input_ctrl: InputController mock (不传时由 match_result 驱动)
    - extra: extra 字典
    """
    ctx = MagicMock()
    ctx.current_node = _FakeFlowNode(
        action=action,
        node_id=node_id,
        node_type=node_type,
        condition=condition,
        loop_count=loop_count,
    )
    ctx.gen = gen

    # stop/pause 事件
    stop_event = MagicMock(spec=threading.Event)
    stop_event.is_set.return_value = stop
    stop_event.wait.return_value = stop
    ctx.stop_event = stop_event

    pause_event = MagicMock(spec=threading.Event)
    pause_event.is_set.return_value = pause
    pause_event.wait.return_value = pause
    ctx.pause_event = pause_event

    # capture/matcher — 仅当 match_result 不是哨兵时设置
    if match_result is not _NO_CAPTURE:
        ctx.capture = MagicMock()
        ctx.capture.grab.return_value = np.zeros((600, 800, 3), dtype=np.uint8)
        ctx.capture.to_logical.side_effect = lambda x, y: (x, y)

        ctx.matcher = MagicMock()
        ctx.matcher.find.return_value = match_result

        # find_any 代理到 find:描述符现调用 find_any,但既有测试 mock 的是 find。
        # 通过委托保持 find 的 side_effect/return_value/call_count 语义全部有效。
        def _find_any_proxy(screen, template_paths, threshold=0.8, **kwargs):
            primary = template_paths[0] if template_paths else ""
            rect = ctx.matcher.find(screen, primary, threshold)
            if rect is None:
                return None
            from src.core.vision.capture import MultiMatchResult
            return MultiMatchResult(
                path=primary, rect=rect, confidence=0.95, strategy_used="mock",
            )

        ctx.matcher.find_any.side_effect = _find_any_proxy

        ctx.input_ctrl = MagicMock() if input_ctrl is None else input_ctrl

    # 可选依赖 — 显式设置以覆盖 MagicMock 自动属性
    ctx.evaluator = evaluator
    ctx.extra = extra

    return ctx
