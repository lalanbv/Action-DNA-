"""ActionChainController — 动作链业务逻辑层"""

from collections.abc import Callable

from src.core.events.event_names import EventName
from src.panel.components.step_param_view import build_move_order
from src.panel.controllers.base_controller import BaseController
from src.utils.i18n import t


class ActionChainController(BaseController):
    """处理动作链用户操作，协调 Model / Executor / Capture / Profile"""

    def _event_subscriptions(self) -> list[tuple[str, Callable]]:
        return [
            (EventName.EXECUTOR_STEP_CHANGED, self._on_step_changed),
            (EventName.EXECUTOR_ROUND_STARTED, self._on_round_started),
            (EventName.EXECUTOR_FINISHED, self._on_finished),
            (EventName.EXECUTOR_STARTED, self._on_started),
            (EventName.EXECUTOR_STOPPED, self._on_stopped),
            (EventName.EXECUTOR_PAUSED, self._on_paused),
            (EventName.EXECUTOR_RESUMED, self._on_resumed),
        ]

    # ── 步骤管理 ──────────────────────────────────────────

    def add_step(self, step) -> None:
        self._require_idle()
        self.model.add_step(step)

    def update_step(self, index: int, step) -> None:
        self._require_idle()
        self.model.update_step(index, step)

    def remove_step(self, index: int) -> None:
        self._require_idle()
        self.model.remove_step(index)

    def move_step(self, from_idx: int, to_idx: int) -> None:
        self._require_idle()
        self.model.move_step(from_idx, to_idx)

    def clear_steps(self) -> None:
        self._require_idle()
        self.model.clear_steps()

    def reorder_steps(self, new_order: list[int]) -> None:
        """insert 语义批量重排（拖拽 / 置顶置底 / 批量移动的统一入口）。"""
        self._require_idle()
        self.model.reorder_steps(new_order)

    def duplicate_step(self, index: int) -> int:
        """复制步骤，副本插入到 index 之后，返回副本新索引。"""
        self._require_idle()
        return self.model.duplicate_step(index)

    def move_to_index(self, index: int, target: int) -> None:
        """把 index 处步骤 insert 移动到 target，其余顺延（非交换语义）。"""
        self._require_idle()
        n = len(self.model.get_steps())
        if not (0 <= index < n and 0 <= target < n) or index == target:
            return  # 越界/同位：显式守卫，避免 build_move_order 静默 no-op emit
        self.model.reorder_steps(build_move_order(n, index, target))

    def clear_matcher_cache(self) -> None:
        self._matcher.clear_cache()

    # ── 执行控制 ──────────────────────────────────────────

    def start_chain(self) -> None:
        self._require_executor()
        if self._executor.is_running:
            return
        steps = self.model.get_steps()
        if not steps:
            raise ValueError(t("panel.exc.add_at_least_one_step"))
        self._executor.start(self.model.graph)

    # ── 配置文件（扩展）──────────────────────────────────────

    def save_profile_to_dir(self, name: str, graph) -> str:
        return self._profile_mgr.save(name, graph)

    # ── 执行器事件回调（特有）─────────────────────────────────

    def _on_step_changed(self, step_index=None, iteration=None, **kwargs):
        self._bus.emit(EventName.UI_STEP_HIGHLIGHT, step_index=step_index, iteration=iteration)

    def _on_round_started(self, iteration=None, **kwargs):
        self._bus.emit(EventName.UI_ROUND_STARTED, iteration=iteration)
