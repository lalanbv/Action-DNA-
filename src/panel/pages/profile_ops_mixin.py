"""ProfileOpsMixin — 配置文件 CRUD + 执行器状态恢复 共享逻辑。

将 4 个页面（tkinter + Qt, action chain + workflow）的 profile 增删改查
和执行器状态恢复统一到此 mixin，宿主类只需提供薄适配层。
"""

from __future__ import annotations

import copy
from typing import NamedTuple

from src.panel.models.chain_model import ExecutorState
from src.utils.i18n import t


class RestoredState(NamedTuple):
    """_restore_executor_state 的返回值。"""
    state: ExecutorState
    graph_copied: bool


class ProfileOpsMixin:
    """配置文件 CRUD 共享逻辑。

    要求宿主类提供:
      - self._controller: ActionChainController | WorkflowController
      - self._model 或 self.model: ChainModel 实例
      - self._append_log(msg: str)
      - self._refresh_profiles()  (tkinter workflow 也命名为 _refresh_profile_list)
      - _get_selected_profile_name() -> str | None
      - _ask_string(title, prompt) -> tuple[str, bool]  (text, ok)
      - self._show_info(title, message)
      - self._show_error(title, message)
      - _ask_yes_no(title, message) -> bool
      - _pre_save_hook()  (可选, 保存前回调如 sync_loop_config)

    类属性:
      - profile_i18n_prefix: str  "chain" 或 "workflow"
    """

    profile_i18n_prefix: str = "chain"

    @property
    def _profile_model(self):
        return getattr(self, "_model", None) or getattr(self, "model", None)

    @property
    def _profile_controller(self):
        return getattr(self, "_controller", None) or getattr(self, "controller", None)

    def _pt(self, key: str, **kwargs) -> str:
        return t(f"{self.profile_i18n_prefix}.msg.{key}", **kwargs)

    def _pre_save_hook(self) -> None:
        """保存前钩子，子类可覆盖（如同步循环配置）。"""

    def _on_load_profile(self) -> None:
        name = self._get_selected_profile_name()
        if not name:
            self._show_info(t("common.hint"), self._pt("select_profile"))
            return
        try:
            self._profile_controller.load_profile(name)
            self._append_log(self._pt("profile_loaded", name=name))
        except Exception as e:
            self._show_error(t("common.load_failed"), str(e))

    def _on_save_profile(self) -> None:
        self._pre_save_hook()
        model = self._profile_model
        name = model.current_profile_name if model else None
        if not name:
            self._on_save_as_profile()
            return
        try:
            self._profile_controller.save_profile(name)
            self._refresh_profiles()
            self._append_log(self._pt("profile_saved", name=name))
        except Exception as e:
            self._show_error(t("common.save_failed"), str(e))

    def _on_save_as_profile(self) -> None:
        self._pre_save_hook()
        name, ok = self._ask_string(
            t("common.save_as"), self._pt("save_as_prompt"),
        )
        if not ok or not name:
            return
        name = name.strip()
        try:
            result = self._profile_controller.save_profile(name)
            if result:
                self._refresh_profiles()
                self._append_log(self._pt("profile_saved_as", name=name))
        except Exception as e:
            self._show_error(t("common.save_failed"), str(e))

    def _on_delete_profile(self) -> None:
        name = self._get_selected_profile_name()
        if not name:
            return
        if not self._ask_yes_no(
            self._pt("confirm_delete"),
            self._pt("confirm_delete_profile", name=name),
        ):
            return
        try:
            self._profile_controller.delete_profile(name)
            self._refresh_profiles()
            self._append_log(self._pt("profile_deleted", name=name))
        except Exception as e:
            self._show_error(self._pt("delete_failed"), str(e))

    # ── 执行器状态恢复（共享逻辑）──────────────────────────────

    def _restore_executor_state(self) -> RestoredState:
        """从执行器恢复图数据和执行状态。

        4 个页面（tk/Qt × chain/workflow）共享的核心逻辑：
        1. 推断 ExecutorState（RUNNING / PAUSED / IDLE）
        2. 如果执行中且有 last_graph，deepcopy 到 model
        3. 设置 model.executor_state

        Returns:
            RestoredState(state, graph_copied) — 宿主类根据返回值
            执行后端特定的 UI 同步（渲染画布、刷新列表等）。

        要求宿主类提供:
          - self.app.executor — 执行器实例
          - self._model 或 self.model — ChainModel 实例
        """
        executor = getattr(self, "app", None)
        executor = getattr(executor, "executor", None) if executor else None
        if executor is None:
            return RestoredState(ExecutorState.IDLE, False)

        model = self._profile_model
        if executor.is_running:
            state = ExecutorState.PAUSED if executor.is_paused else ExecutorState.RUNNING
            graph_copied = False
            if executor.last_graph and model:
                model.graph = copy.deepcopy(executor.last_graph)
                graph_copied = True
            if model:
                model.executor_state = state
            return RestoredState(state, graph_copied)

        if model:
            model.executor_state = ExecutorState.IDLE
        return RestoredState(ExecutorState.IDLE, False)
