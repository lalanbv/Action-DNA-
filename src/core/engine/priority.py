"""统一优先级枚举 — 参考 Cocos4 SystemPriority。

为 Layer 中间件提供标准化的优先级常量，确保执行顺序一致且可预测。
数字越小越先执行 on_node_enter（正序），越后执行 on_node_exit（LIFO 逆序）。

现有层优先级映射：
    FailSafeLayer:              SAFETY_CHECK (-400)
    MonitorCoordinationLayer:   PRE_PROCESS   (-300)
    PauseLayer:                 FLOW_CONTROL  (-200)
    EventBridgeLayer:           BRIDGE        (-100)
    LoggingLayer:               OBSERVE       (-100)
    TimingLayer:                MEASURE       (-50)
    RetryLayer:                 CORE          (0)
    BreakpointLayer:            DEBUG         (50)
    DebugScreenshotLayer:       POST_PROCESS  (50)
"""

from enum import IntEnum

__all__ = ["SystemPriority"]


class SystemPriority(IntEnum):
    """系统级优先级常量。"""

    # 安全检查 — 最先执行，阻止不安全操作
    SAFETY_CHECK = -400

    # 前置处理 — 协调、资源准备
    PRE_PROCESS = -300

    # 流程控制 — 暂停/恢复、分支
    FLOW_CONTROL = -200

    # 桥接/通知 — 事件转发、UI 通知
    BRIDGE = -100

    # 观察 — 日志、审计（与 BRIDGE 同级，保证可观测性）
    OBSERVE = -100

    # 测量 — 计时、性能统计
    MEASURE = -50

    # 核心 — 核心业务逻辑（默认）
    CORE = 0

    # 后处理 — 结果处理、转换
    POST_PROCESS = 50

    # 调试 — 断点、截图（最后执行）
    DEBUG = 50

    # 低优先级 — 仅在所有其他层之后
    LOW = 200

    # 最低 — 系统级调度器
    SCHEDULER = 2**31
