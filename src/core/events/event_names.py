"""EventName — 事件总线名称常量。

集中定义 EventBus 使用的所有事件名字符串，
避免裸字符串散布在各模块中。
"""

from __future__ import annotations


class EventName:
    """事件总线名称常量集合。"""

    # ---- 执行器生命周期 ----
    EXECUTOR_STARTED = "executor.started"
    EXECUTOR_STOPPED = "executor.stopped"
    EXECUTOR_PAUSED = "executor.paused"
    EXECUTOR_RESUMED = "executor.resumed"
    EXECUTOR_FINISHED = "executor.finished"
    EXECUTOR_FAILSAFE = "executor.failsafe"
    EXECUTOR_ROUND_STARTED = "executor.round_started"
    EXECUTOR_STEP_CHANGED = "executor.step_changed"
    EXECUTOR_STEP_ERROR = "executor.step_error"
    EXECUTOR_STATE_CHANGED = "executor.state_changed"

    # ---- 动作链 ----
    CHAIN_STEPS_CHANGED = "chain.steps_changed"
    CHAIN_LOADED = "chain.loaded"
    CHAIN_MONITORS_CHANGED = "chain.monitors_changed"

    # ---- UI 高亮 ----
    UI_STEP_HIGHLIGHT = "ui.step_highlight"
    UI_ROUND_STARTED = "ui.round_started"
    UI_NODE_HIGHLIGHT = "ui.node_highlight"

    # ---- 区域 ----
    REGION_CHANGED = "region.changed"
