"""ClickImageDescriptor — 模板匹配 + 点击，最复杂的内置描述符。

截屏 → 模板匹配 → 计算点击位置 → 执行动作（点击/双击/长按/拖拽/仅移动）。
支持重试、未找到跳过/停止、坐标输出。
"""

from __future__ import annotations

import logging
import os
import random
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from src.core.action import DetectMode, FoundAction
from src.core.step_types import ClickImageStep
from src.core.engine.execution_blocker import ExecutionBlocker
from src.core.engine.node_descriptor import NodeDescriptor, PortDef
from src.core.engine.node_registry import auto_register
from src.core.engine.node_result import NodeResult
from src.core.vision.capture import MultiMatchResult
from src.core.vision.match_config import resolve_find_any_params
from src.utils.i18n import t

if TYPE_CHECKING:
    from src.core.engine.execution_context import ExecutionContext

logger = logging.getLogger(__name__)

__all__ = ["ClickImageDescriptor"]


@dataclass(frozen=True)
class _ClickParams:
    """匹配成功后的动作参数 — 减少 _execute_found_action / _wait_until_found 的参数量。"""

    found_action: FoundAction
    offset_x: int
    offset_y: int
    save_coord_name: str
    hold_duration: float
    drag_offset_x: int
    drag_offset_y: int


@dataclass(frozen=True)
class _MatchAttempt:
    """单次模板匹配结果。"""

    rect: tuple[int, int, int, int] | None
    had_error: bool
    error_msg: str = ""


@auto_register
class ClickImageDescriptor(NodeDescriptor):
    """模板匹配 + 点击描述符。

    流程：截屏 → find() 模板匹配 → 计算逻辑坐标 → 执行 found_action。
    匹配失败时根据 detect_mode 决定跳过（ExecutionBlocker）或报错。
    """

    JITTER_RANGE: int = 3
    _MAX_WAIT_SECONDS: float = 3600.0
    _ACTION_RETRIES: int = 3

    # ---- 元数据 ----

    @classmethod
    def action_type(cls) -> str:
        return "CLICK_IMAGE"

    @classmethod
    def display_name(cls) -> str:
        return "点击图片"

    @classmethod
    def category(cls) -> str:
        return "基础动作"

    @classmethod
    def input_types(cls) -> dict[str, PortDef]:
        return {
            "image_path": PortDef("image", "模板图片路径", required=True),
            "threshold": PortDef(
                "number", "匹配置信度阈值 (0.0~1.0)", required=False, default=0.8,
            ),
            "detect_mode": PortDef(
                "string", "检测模式: SKIP_IF_NOT_FOUND | FAIL_IF_NOT_FOUND | WAIT_UNTIL_FOUND",
                required=False, default="SKIP_IF_NOT_FOUND",
            ),
            "retry_count": PortDef(
                "number", "重试次数", required=False, default=3,
            ),
            "retry_wait_min": PortDef(
                "number", "重试最小间隔（秒）", required=False, default=0.5,
            ),
            "retry_wait_max": PortDef(
                "number", "重试最大间隔（秒）", required=False, default=1.5,
            ),
            "found_action": PortDef(
                "string", "检测到后的操作", required=False, default="LEFT_CLICK",
            ),
            "offset_x": PortDef(
                "number", "点击 X 偏移", required=False, default=0,
            ),
            "offset_y": PortDef(
                "number", "点击 Y 偏移", required=False, default=0,
            ),
            "save_coord_name": PortDef(
                "string", "保存坐标到变量名（空=不保存）", required=False, default="",
            ),
        }

    @classmethod
    def output_types(cls) -> dict[str, PortDef]:
        return {
            "match_pos": PortDef("coord", "匹配位置 (x, y)"),
        }

    # ---- 执行 ----

    def execute(self, ctx: ExecutionContext) -> NodeResult | ExecutionBlocker:
        action = ctx.current_node.action
        if action is None:
            return NodeResult.fail(t("engine.node_fail.missing_step_config", node_type="CLICK_IMAGE"))

        if not isinstance(action, ClickImageStep):
            return NodeResult.fail(t("engine.node_fail.click_image_step_type_error", type_name=type(action).__name__))

        params = _ClickParams(
            found_action=action.found_action,
            offset_x=action.offset_x,
            offset_y=action.offset_y,
            save_coord_name=action.save_coord_name,
            hold_duration=action.hold_duration,
            drag_offset_x=action.drag_offset_x,
            drag_offset_y=action.drag_offset_y,
        )

        if action.detect_mode == DetectMode.WAIT_UNTIL_FOUND:
            return self._wait_until_found(
                ctx, action, params,
            )

        match_rect = self._find_with_retries(
            ctx, action, action.retry_count,
            action.retry_wait_min, action.retry_wait_max,
        )

        if match_rect is None:
            return self._handle_not_found(action.detect_mode, action.image_path)

        if ctx.stop_event.is_set():
            return NodeResult.fail(t("engine.node_fail.stop_signal_match_interrupt"))

        return self._execute_found_action(ctx, match_rect, params)

    # ---- 内部方法 ----

    def _try_single_match(
        self,
        ctx: ExecutionContext,
        action: ClickImageStep,
    ) -> _MatchAttempt:
        """执行单次截图 + 多模板匹配,返回 _MatchAttempt(rect 取自命中模板)。"""
        try:
            screenshot = ctx.capture.grab(force=False)
            paths, per_thr, strategy = resolve_find_any_params(
                primary_path=action.image_path,
                alt_paths=action.alt_image_paths,
                base_threshold=action.threshold,
                alt_thresholds=action.alt_thresholds,
                threshold_mode=action.threshold_mode,
                match_strategy=action.match_strategy,
            )
            if not paths:
                return _MatchAttempt(rect=None, had_error=False, error_msg="无可匹配模板")
            result: MultiMatchResult | None = ctx.matcher.find_any(
                screenshot,
                paths,
                threshold=action.threshold,
                strategy=strategy,
                per_template_thresholds=per_thr,
            )
            rect = result.rect if result is not None else None
            return _MatchAttempt(rect=rect, had_error=False)
        except Exception as exc:
            logger.warning(t("engine.log.multi_match_exception", image_path=action.image_path, error=exc))
            return _MatchAttempt(rect=None, had_error=True, error_msg=str(exc))

    def _find_with_retries(
        self,
        ctx: ExecutionContext,
        action: ClickImageStep,
        retry_count: int,
        retry_wait_min: float,
        retry_wait_max: float,
    ) -> tuple[int, int, int, int] | None:
        """带重试的多模板匹配,返回 (x, y, w, h) 或 None。

        首次截图前等待短暂稳定时间，让上一步触发的 UI 动画完成。
        retry 作用于整个模板集合；重试日志聚合为一条汇总输出。
        """
        # 首次截图前稳定延迟：让屏幕动画/过渡完成（仅首轮）
        if ctx.gen == 0:
            ctx.stop_event.wait(timeout=random.uniform(0.08, 0.20))
        if ctx.stop_event.is_set():
            return None

        attempts = max(1, retry_count + 1)
        miss_count = 0
        error_count = 0
        last_error: str | None = None
        basename = os.path.basename(action.image_path)

        for attempt in range(attempts):
            if ctx.stop_event.is_set():
                return None

            result = self._try_single_match(ctx, action)
            if result.had_error:
                error_count += 1
                last_error = result.error_msg

            if result.rect is not None:
                parts = [f"{miss_count}次未匹配"]
                if error_count > 0:
                    parts.append(f"{error_count}次异常")
                summary = ", ".join(parts)
                logger.info(
                    t(
                        "engine.log.click_image_hit",
                        basename=basename,
                        attempt=attempt + 1,
                        summary=summary,
                        hit=attempt + 1,
                        x=result.rect[0],
                        y=result.rect[1],
                    )
                )
                return result.rect

            miss_count += 1

            if attempt < attempts - 1:
                # 逐步加长重试间隔，减少前期频繁重试的 CPU 消耗
                base = random.uniform(retry_wait_min, retry_wait_max)
                wait = base * (1 + 0.5 * attempt)
                ctx.stop_event.wait(timeout=wait)

        parts = [f"{miss_count}次未匹配"]
        if error_count > 0:
            parts.append(f"{error_count}次异常")
            if last_error:
                parts.append(f"最后错误: {last_error[:80]}")
        summary = ", ".join(parts)
        logger.info(t("engine.log.click_image_failed", basename=basename, attempts=attempts, summary=summary))
        return None

    def _wait_until_found(
        self,
        ctx: ExecutionContext,
        action: ClickImageStep,
        params: _ClickParams,
    ) -> NodeResult:
        """WAIT_UNTIL_FOUND 模式：持续匹配直到找到或收到停止信号。

        注意：此方法不会返回 ExecutionBlocker，只能成功或失败。
        安全阀：超过 _MAX_WAIT_SECONDS 后自动终止，防止引擎未设置 stop_event 时无限循环。
        """
        start = time.monotonic()
        check_count = 0
        miss_count = 0
        error_count = 0
        progress_interval = 10
        basename = os.path.basename(action.image_path)

        while not ctx.stop_event.is_set():
            if time.monotonic() - start > self._MAX_WAIT_SECONDS:
                logger.warning(
                    t(
                        "engine.log.click_image_wait_timeout",
                        basename=basename,
                        max_seconds=self._MAX_WAIT_SECONDS,
                        checks=check_count,
                        misses=miss_count,
                        errors=error_count,
                    )
                )
                return NodeResult.fail(
                    t("engine.node_fail.wait_until_found_timeout", max_seconds=self._MAX_WAIT_SECONDS, image_path=action.image_path),
                )

            if ctx.pause_event.is_set():
                ctx.stop_event.wait(timeout=0.1)
                if ctx.stop_event.is_set():
                    return NodeResult.fail(t("engine.node_fail.stop_signal_template_wait_interrupt"))
                continue

            check_count += 1
            result = self._try_single_match(ctx, action)
            if result.had_error:
                error_count += 1
                logger.warning(t("engine.log.wait_match_exception", image_path=action.image_path))
                wait = random.uniform(action.retry_wait_min, action.retry_wait_max)
                ctx.stop_event.wait(timeout=wait)
                continue

            if result.rect is not None:
                elapsed = time.monotonic() - start
                logger.info(
                    t(
                        "engine.log.click_image_wait_success",
                        basename=basename,
                        checks=check_count,
                        elapsed=elapsed,
                        x=result.rect[0],
                        y=result.rect[1],
                    )
                )
                if ctx.stop_event.is_set():
                    return NodeResult.fail(t("engine.node_fail.stop_signal_match_interrupt"))
                return self._execute_found_action(ctx, result.rect, params)

            miss_count += 1
            if check_count % progress_interval == 0:
                elapsed = time.monotonic() - start
                logger.info(
                    t(
                        "engine.log.click_image_wait_progress",
                        basename=basename,
                        checks=check_count,
                        elapsed=elapsed,
                    )
                )

            wait = random.uniform(action.retry_wait_min, action.retry_wait_max)
            ctx.stop_event.wait(timeout=wait)

        return NodeResult.fail(t("engine.node_fail.stop_signal_template_wait_interrupt"))

    def _handle_not_found(
        self,
        detect_mode: DetectMode,
        template_path: str,
    ) -> NodeResult | ExecutionBlocker:
        """处理未找到模板的情况。"""
        match detect_mode:
            case DetectMode.FAIL_IF_NOT_FOUND:
                return NodeResult.fail(t("engine.node_fail.template_match_failed", template_path=template_path))
            case DetectMode.SKIP_IF_NOT_FOUND:
                return ExecutionBlocker(reason=f"未找到模板: {template_path}")
            case _:
                logger.warning(t("engine.log.unknown_detect_mode", detect_mode=detect_mode))
                return ExecutionBlocker(reason=f"未找到模板: {template_path}")

    def _execute_found_action(
        self,
        ctx: ExecutionContext,
        match_rect: tuple[int, int, int, int],
        params: _ClickParams,
    ) -> NodeResult:
        """根据 found_action 执行对应操作。

        检测成功后动作执行失败时，仅重试动作本身（不重新检测），
        防止瞬态后端异常导致整个节点被 transient retry 重跑检测流程。
        """
        x, y, w, h = match_rect

        logical_x, logical_y = ctx.capture.to_logical(
            x + w // 2, y + h // 2,
        )

        # 按钮边界（逻辑像素），约束漂移不超出按钮区域
        btn_lx, btn_ly = ctx.capture.to_logical(x, y)
        btn_rx, btn_ry = ctx.capture.to_logical(x + w, y + h)
        clamp = (btn_lx, btn_ly, btn_rx, btn_ry)

        jitter_x = random.randint(-self.JITTER_RANGE, self.JITTER_RANGE)
        jitter_y = random.randint(-self.JITTER_RANGE, self.JITTER_RANGE)
        target_x = max(0, logical_x + params.offset_x + jitter_x)
        target_y = max(0, logical_y + params.offset_y + jitter_y)

        for attempt in range(self._ACTION_RETRIES):
            if ctx.stop_event.is_set():
                return NodeResult.fail(t("engine.node_fail.stop_signal_action_interrupt"))
            try:
                self._perform_action(ctx, params, target_x, target_y, clamp)
                break
            except Exception as exc:
                if attempt < self._ACTION_RETRIES - 1:
                    logger.warning(
                        t(
                            "engine.log.click_image_action_exception_retry",
                            attempt=attempt + 1,
                            retries=self._ACTION_RETRIES,
                            error=exc,
                        )
                    )
                    ctx.stop_event.wait(
                        timeout=random.uniform(0.1, 0.25),
                    )
                else:
                    logger.error(
                        t(
                            "engine.log.click_image_action_exhausted",
                            retries=self._ACTION_RETRIES,
                            found_action=params.found_action.value,
                            x=target_x,
                            y=target_y,
                            error=exc,
                        )
                    )
                    return NodeResult.fail(
                        t("engine.node_fail.action_exec_failed", retry_count=self._ACTION_RETRIES, error=exc),
                    )

        output_vars: dict[str, Any] = {
            "match_pos": (target_x, target_y),
        }

        logger.info(
            t(
                "engine.log.click_image_match_success",
                found_action=params.found_action.value,
                x=target_x,
                y=target_y,
            )
        )

        if params.save_coord_name:
            output_vars[params.save_coord_name] = (target_x, target_y)

        return NodeResult(
            success=True,
            output_vars=output_vars,
            cooldown=random.uniform(0.05, 0.15),
        )

    def _perform_action(
        self,
        ctx: ExecutionContext,
        params: _ClickParams,
        x: int,
        y: int,
        clamp: tuple[int, int, int, int] | None,
    ) -> None:
        """根据 FoundAction 执行具体操作。clamp 约束漂移不超出按钮区域。"""
        match params.found_action:
            case FoundAction.LEFT_CLICK:
                ctx.input_ctrl.click(x, y, button="left", clamp=clamp)
            case FoundAction.RIGHT_CLICK:
                ctx.input_ctrl.click(x, y, button="right", clamp=clamp)
            case FoundAction.LEFT_DOUBLE_CLICK:
                ctx.input_ctrl.click(x, y, button="left", clicks=2, clamp=clamp)
            case FoundAction.RIGHT_DOUBLE_CLICK:
                ctx.input_ctrl.click(x, y, button="right", clicks=2, clamp=clamp)
            case FoundAction.LONG_PRESS:
                ctx.input_ctrl.long_press(x, y, duration=params.hold_duration, clamp=clamp)
            case FoundAction.DRAG_TO:
                ctx.input_ctrl.drag_to(
                    x, y,
                    x + params.drag_offset_x, y + params.drag_offset_y,
                )
            case FoundAction.ONLY_MOVE:
                ctx.input_ctrl.move_to(x, y)
            case FoundAction.OUTPUT_COORD:
                pass  # 仅输出坐标，不执行操作
            case _:
                logger.warning(t("engine.log.unhandled_found_action", found_action=params.found_action))
                ctx.input_ctrl.click(x, y, button="left", clamp=clamp)

