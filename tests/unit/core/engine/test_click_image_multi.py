"""ClickImageDescriptor 多模板行为:改用 find_any,主图 miss 备用图 hit 仍成功。"""

from unittest.mock import MagicMock

from src.core.action import DetectMode, FoundAction, MatchStrategy, ThresholdMode
from src.core.engine.descriptors.click_image_descriptor import ClickImageDescriptor
from src.core.engine.execution_blocker import ExecutionBlocker
from src.core.step_types import ClickImageStep
from src.core.vision.capture import MultiMatchResult


def _make_ctx(find_any_results):
    """构造假 ExecutionContext。find_any_results 按 find_any 调用顺序返回。"""
    ctx = MagicMock()
    ctx.capture.grab.return_value = MagicMock()
    ctx.capture.to_logical.side_effect = lambda x, y: (x, y)
    ctx.matcher.find_any.side_effect = find_any_results
    ctx.stop_event.is_set.return_value = False
    ctx.stop_event.wait = MagicMock()
    ctx.gen = 0
    ctx.input_ctrl = MagicMock()
    ctx.current_node.action = None
    return ctx


def _step(alt_paths=None, threshold_mode=ThresholdMode.GLOBAL, strategy=MatchStrategy.ADAPTIVE):
    return ClickImageStep(
        image_path="primary.png",
        alt_image_paths=alt_paths or [],
        alt_thresholds=[],
        threshold_mode=threshold_mode,
        match_strategy=strategy,
        detect_mode=DetectMode.SKIP_IF_NOT_FOUND,
        found_action=FoundAction.LEFT_CLICK,
        threshold=0.8,
        retry_count=0,
    )


def test_primary_miss_alt_hit_succeeds():
    """find_any 返回命中(内部已处理多模板),应成功点击。"""
    hit = MultiMatchResult(
        path="alt.png", rect=(50, 60, 40, 40), confidence=0.9, strategy_used="early_exit",
    )
    ctx = _make_ctx([hit])
    ctx.current_node.action = _step(alt_paths=["alt.png"])
    result = ClickImageDescriptor().execute(ctx)
    assert result.success is True
    assert ctx.matcher.find_any.called  # 改用 find_any 而非旧 find


def test_all_miss_returns_blocker_when_skip_mode():
    """整个模板集合都未命中 + SKIP 模式 → ExecutionBlocker。"""
    ctx = _make_ctx([None])
    ctx.current_node.action = _step(alt_paths=["alt.png"])
    result = ClickImageDescriptor().execute(ctx)
    assert isinstance(result, ExecutionBlocker)


def test_find_any_called_with_resolved_params():
    """resolve_find_any_params 产出的 paths/per_thresholds/strategy 传给 find_any。"""
    hit = MultiMatchResult(
        path="primary.png", rect=(50, 60, 40, 40), confidence=0.95, strategy_used="early_exit",
    )
    ctx = _make_ctx([hit])
    ctx.current_node.action = _step(alt_paths=["alt.png"], threshold_mode=ThresholdMode.PER_TEMPLATE)
    ClickImageDescriptor().execute(ctx)
    call = ctx.matcher.find_any.call_args
    paths = call.args[1]  # 第二个位置参数 = template_paths
    assert "primary.png" in paths and "alt.png" in paths
    assert call.kwargs.get("strategy") == MatchStrategy.ADAPTIVE
