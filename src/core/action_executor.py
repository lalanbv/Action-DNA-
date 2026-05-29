"""动作链执行器 — Facade 外观类，委托给 GraphEngine 执行。

保持旧公共接口不变（start/stop/pause/resume/is_running 等），
内部委托给 GraphEngine + NodeDescriptor 管道。
线程管理、暂停/停止、事件桥接、监控器、防休眠留在 Facade 层。
"""

import random
import threading
import time
import types

from src.core.step_types import (
    HoldKeyStep,
    IdleBehaviorStep,
    KeyComboStep,
    MultiKeySequenceStep,
    MouseMoveStep,
    StartTimerStep,
)
from src.core.condition import ConditionEvaluator
from src.core.engine.execution_context import ExecutionContext
from src.core.engine.graph_engine import GraphEngine, GraphEngineConfig
from src.core.events import TypedEventBus
from src.core.events.event_names import EventName
from src.core.flow import FlowGraph, FlowNode, NodeType
from src.core.layers.debug_screenshot_layer import DebugScreenshotLayer
from src.core.layers.event_bridge_layer import EventBridgeLayer
from src.core.layers.pause_layer import PauseLayer
from src.core.logger import LOG_DIR, log
from src.core.monitor import MonitorConfig
from src.core.monitor_manager import MonitorManager
from src.core.screen_guard import DisplaySleepPreventer
from src.core.fail_safe import FailSafeMonitor, FailSafeTriggered
from src.core.variables.pool import VariablePool
from src.core.vision import ScreenCapture, TemplateMatcher
from src.utils.timing import human_like_duration


def _parse_comma_keys(value: str) -> list[str]:
    return [k.strip() for k in value.split(",") if k.strip()]


class ActionExecutor:
    """动作链执行器 Facade（后台线程），通过 EventBus 推送状态。

    使用 threading.Event 保证线程安全：
    - _stop_event: 控制线程退出
    - _pause_event: 控制暂停/恢复
    - _gen 代际计数器 + lock: 防止旧线程覆盖新线程状态
    所有事件通过 _schedule_main 桥接到主线程，避免 tkinter 跨线程崩溃。
    """

    def __init__(
        self,
        capture: ScreenCapture,
        matcher: TemplateMatcher,
        input_ctrl,
        event_bus: TypedEventBus | None = None,
        max_consecutive_failures: int = 5,
    ):
        self.capture = capture
        self.matcher = matcher
        self.input = input_ctrl
        self._event_bus = event_bus
        self._thread: threading.Thread | None = None
        self._evaluator: ConditionEvaluator | None = None
        self._monitor_manager: MonitorManager | None = None

        # 线程安全控制
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._gen = 0
        self._current_step_idx = -1
        self._loop_iteration = 0
        self._running = False

        # 主线程调度器（由 PanelApp 注入 frame.after）
        self._schedule_main = None

        # 屏幕防休眠
        self._sleep_guard = DisplaySleepPreventer()

        # GraphEngine + Layers
        self._last_graph: FlowGraph | None = None

        self._graph_engine = GraphEngine(GraphEngineConfig())
        self._event_bridge = EventBridgeLayer(
            publish_fn=self._emit,
            on_step_enter=self._on_step_enter,
        )
        self._debug_layer = DebugScreenshotLayer(capture=capture, log_dir=LOG_DIR)
        self._pause_layer = PauseLayer()
        self._graph_engine.add_layer(self._pause_layer)
        self._graph_engine.add_layer(self._event_bridge)
        self._graph_engine.add_layer(self._debug_layer)

        # FAIL-SAFE + 连续失败追踪
        self._fail_safe = FailSafeMonitor(enabled=True)
        self._consecutive_failures: int = 0
        self._max_consecutive_failures: int = max_consecutive_failures
        self._profile_root: str = "profiles"

        # FailSafeLayer — 每个节点入口检查鼠标角落
        from src.core.layers.failsafe_layer import FailSafeLayer
        self._failsafe_layer = FailSafeLayer(self._fail_safe, input_ctrl, capture)
        self._graph_engine.add_layer(self._failsafe_layer)

        # MonitorCoordinationLayer — handler 活跃时阻塞主流程
        # 延迟绑定：_start_monitors 时通过 set_manager 更新
        from src.core.layers.monitor_coordination_layer import MonitorCoordinationLayer
        self._coordination_layer = MonitorCoordinationLayer(None)
        self._graph_engine.add_layer(self._coordination_layer)

    def set_main_scheduler(self, scheduler) -> None:
        """设置主线程调度器（frame.after），用于将后台事件桥接到主线程"""
        self._schedule_main = scheduler

    # ── 属性 ──────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._running

    @property
    def is_paused(self) -> bool:
        return self._pause_event.is_set()

    @property
    def current_step_index(self) -> int:
        with self._lock:
            return self._current_step_idx

    @property
    def loop_iteration(self) -> int:
        with self._lock:
            return self._loop_iteration

    @property
    def last_graph(self) -> FlowGraph | None:
        return self._last_graph

    @property
    def monitor_manager(self) -> MonitorManager | None:
        return self._monitor_manager

    # ── 控制 ──────────────────────────────────────────────

    def start(self, source) -> None:
        """启动执行，接受 FlowGraph"""
        self._ensure_stopped()

        graph = source

        with self._lock:
            self._gen += 1
            gen = self._gen
            self._stop_event.clear()
            self._pause_event.clear()
            self._current_step_idx = -1
            self._loop_iteration = 0
            self._running = True

        self._evaluator = ConditionEvaluator(self.capture, self.matcher)

        self._last_graph = graph

        self._start_monitors(graph.monitors, gen)

        # 确保描述符已注册（触发 import + @auto_register）
        import src.core.engine.descriptors  # noqa: F401  # pylint: disable=unused-import

        self._thread = threading.Thread(
            target=self._run_with_engine, args=(graph, gen), daemon=True
        )
        self._thread.start()
        self._sleep_guard.start()
        log.info("启动流程图: %s", graph.describe())
        self._emit(EventName.EXECUTOR_STARTED)

    def stop(self) -> None:
        self._stop_event.set()
        self._pause_event.clear()
        with self._lock:
            self._gen += 1
            self._running = False
        self._last_graph = None
        self._stop_monitors()
        self._sleep_guard.stop()
        log.info("动作链已停止")
        self._emit(EventName.EXECUTOR_STOPPED)

    def shutdown(self) -> None:
        """完全关闭执行器（等待线程退出），用于应用退出时释放资源"""
        self.stop()
        self._ensure_stopped()

    def pause(self) -> None:
        self._pause_event.set()
        log.info("动作链已暂停")
        self._emit(EventName.EXECUTOR_PAUSED)

    def resume(self) -> None:
        self._pause_event.clear()
        self._pause_layer.resume()
        log.info("动作链已恢复")
        self._emit(EventName.EXECUTOR_RESUMED)

    # ── 内部：Facade 核心 ──────────────────────────────────────

    def _run_with_engine(self, graph: FlowGraph, gen: int) -> None:
        """外层循环：反复调用 GraphEngine.run() 直到停止或达到循环上限"""
        iteration = 0
        self._consecutive_failures = 0
        try:
            while self._alive(gen):
                with self._lock:
                    self._loop_iteration = iteration
                log.info("--- 第 %d 轮 ---", iteration + 1)

                if iteration > 0:
                    self._emit(EventName.EXECUTOR_ROUND_STARTED, iteration=iteration)

                ctx = self._build_context(graph, gen)

                self._graph_engine.run(graph, ctx)

                # 轮次成功 → 重置连续失败计数
                with self._lock:
                    self._consecutive_failures = 0

                iteration += 1

                if not graph.loop:
                    break
                if graph.loop_count > 0 and iteration >= graph.loop_count:
                    log.info("达到循环次数上限 (%d)", graph.loop_count)
                    break

        except FailSafeTriggered:
            log.warning("FAIL-SAFE 触发: 鼠标在屏幕角落，紧急停止")
            self._emit(EventName.EXECUTOR_FAILSAFE)
        except Exception:  # noqa: BLE001 — 顶层兜底，防止崩溃
            log.exception("流程图执行异常")
        finally:
            self._stop_monitors()
            with self._lock:
                if self._gen == gen:
                    self._current_step_idx = -1
                    self._running = False
            log.info("流程图执行结束 (共 %d 轮)", iteration)
            self._emit(EventName.EXECUTOR_FINISHED)

    def record_failure(self) -> None:
        """记录一次节点失败，超过阈值时自动停止。"""
        with self._lock:
            self._consecutive_failures += 1
            count = self._consecutive_failures
        if count >= self._max_consecutive_failures:
            log.warning(
                "连续 %d 次失败，自动停止", count
            )
            self.stop()

    def reset_failures(self) -> None:
        """节点成功时重置连续失败计数。"""
        with self._lock:
            self._consecutive_failures = 0

    def _build_context(self, graph: FlowGraph, gen: int) -> ExecutionContext:
        """构建不可变 ExecutionContext"""
        variables = VariablePool()

        # 找到起始节点作为 current_node
        start_node = graph.find_by_type("START")
        if start_node is None:
            start_node = FlowNode(node_id="start", node_type=NodeType.START)

        # TypedEventBus 兼容：传 None，事件通过 EventBridgeLayer 发布
        return ExecutionContext(
            graph=graph,
            current_node=start_node,
            variables=variables,
            capture=self.capture,
            matcher=self.matcher,
            input_ctrl=self.input,
            event_bus=None,
            gen=gen,
            stop_event=self._stop_event,
            pause_event=self._pause_event,
            evaluator=self._evaluator,
            extra=types.MappingProxyType({
                "_executor": self,
                "_graph_engine": self._graph_engine,
                "profile_root": self._profile_root,
            }),
        )

    def _on_step_enter(self, step_index: int, _iteration: int, _node_id: str | None) -> None:
        """EventBridgeLayer 回调：更新当前步骤索引"""
        with self._lock:
            self._current_step_idx = step_index

    # ── 内部：线程管理 ──────────────────────────────────────

    def _ensure_stopped(self) -> None:
        """等待执行线程完全退出，防止新旧线程并发访问 capture/matcher/input"""
        if self._thread is not None and self._thread.is_alive():
            self._stop_event.set()
            self._thread.join(timeout=5.0)
            if self._thread.is_alive():
                log.warning("旧执行线程未在5秒内退出（可能存在非中断的长按/等待操作）")
        self._thread = None

    def _alive(self, gen: int) -> bool:
        """当前线程是否仍是最新代际且未被停止"""
        return not self._stop_event.is_set() and self._gen == gen

    # ── 内部：事件发布 ──────────────────────────────────────

    def _emit(self, event: str, **kwargs) -> None:
        """发布事件：始终桥接到主线程执行，避免 tkinter 跨线程崩溃"""
        if event == EventName.EXECUTOR_STEP_CHANGED:
            with self._lock:
                kwargs = {**kwargs, "iteration": self._loop_iteration}
        frozen = dict(kwargs)
        if self._schedule_main:
            self._schedule_main(0, lambda e=event, k=frozen: self._event_bus.emit(e, **k))
        elif self._event_bus:
            self._event_bus.emit(event, **frozen)

    # ── 内部：监控器 ──────────────────────────────────────

    def _start_monitors(self, configs: list[MonitorConfig], _gen: int) -> None:
        self._stop_monitors()
        if not configs:
            return
        typed_bus = self._event_bus
        self._monitor_manager = MonitorManager(
            capture=self.capture,
            matcher=self.matcher,
            input_ctrl=self.input,
            event_bus=typed_bus,
        )
        from src.core.shared_frame_provider import SharedFrameProvider
        self._monitor_manager.set_frame_provider(
            SharedFrameProvider(self.capture)
        )
        for cfg in configs:
            self._monitor_manager.register(cfg)
        self._monitor_manager.start_all()
        # 绑定协调层到新的 MonitorManager
        self._coordination_layer.set_manager(self._monitor_manager)

    def _stop_monitors(self) -> None:
        if self._monitor_manager is not None:
            self._monitor_manager.stop_all()
            self._monitor_manager = None
        self._coordination_layer.set_manager(None)

    # ── 保留的私有方法（供占位描述符回调）──────────────────────

    def _do_hold_key(self, step: HoldKeyStep, gen: int) -> None:
        """HOLD_KEY: 长按一个或多个按键"""
        if step.keys_hold:
            keys = _parse_comma_keys(step.keys_hold)
        elif step.key:
            keys = [step.key]
        else:
            log.warning("长按按键: 未设置按键，跳过")
            return

        if step.recorded_duration > 0:
            duration = human_like_duration(step.recorded_duration)
        else:
            duration = step.hold_duration * random.uniform(0.9, 1.1)

        def should_stop():
            return not self._alive(gen)

        if len(keys) == 1:
            interrupted = self.input.key_hold_interruptible(
                keys[0], duration, stop_check=should_stop
            )
            if interrupted:
                log.info("  长按按键被中断")
            else:
                log.info("  长按 %s %.2fs", keys[0], duration)
            return

        def _key_down(k: str) -> None:
            self.input.key_down(k)

        def _key_up(k: str) -> None:
            self.input.key_up(k)

        try:
            pressed_keys: list[str] = []
            for i, key in enumerate(keys):
                _key_down(key)
                pressed_keys.append(key)
                if i < len(keys) - 1:
                    time.sleep(random.uniform(0.03, 0.08))

            deadline = time.monotonic() + duration
            while time.monotonic() < deadline:
                if not self._alive(gen):
                    break
                time.sleep(0.05)
        finally:
            alive = self._alive(gen)
            for key in reversed(pressed_keys):
                _key_up(key)
                if alive:
                    time.sleep(random.uniform(0.02, 0.06))

        log.info("  长按 %s %.2fs", keys, duration)

    def _do_mouse_move(self, step: MouseMoveStep, gen: int) -> None:
        """MOUSE_MOVE: 鼠标相对移动（支持按住按键拖拽）

        优先使用 path_points 精确回放录制轨迹，
        无路径点时退回到 Bezier 曲线偏移。
        """
        if not self._alive(gen):
            return

        dx = step.offset_x
        dy = step.offset_y

        if dx == 0 and dy == 0 and not step.path_points:
            log.info("  鼠标移动: 偏移为0且无路径点，跳过")
            return

        # 有录制路径时，沿真实轨迹精确回放
        if step.path_points and len(step.path_points) >= 2:
            self._replay_recorded_path(step, gen)
            return

        # fallback: 无路径点时使用 Bezier 偏移
        jittered_dx = int(dx * random.uniform(0.93, 1.07))
        jittered_dy = int(dy * random.uniform(0.93, 1.07))

        if step.recorded_duration > 0:
            jittered_duration = human_like_duration(step.recorded_duration)
        else:
            jittered_duration = human_like_duration(step.move_speed)

        self.input.move_relative_bezier(
            dx=jittered_dx,
            dy=jittered_dy,
            duration=jittered_duration,
            curve_intensity=step.curve_amount,
        )

        log.info("  鼠标移动: (%d,%d)→(%d,%d) %.2fs", dx, dy, jittered_dx, jittered_dy, jittered_duration)
        time.sleep(random.uniform(0.02, 0.08))

    def _replay_recorded_path(self, step: MouseMoveStep, gen: int) -> None:
        """沿录制的真实路径回放鼠标移动，保留轨迹形状和速度。"""
        path_points = step.path_points
        origin_x, origin_y, _ = path_points[0]

        cur_x, cur_y = self.input.get_mouse_position()

        off_x = cur_x - origin_x
        off_y = cur_y - origin_y
        adjusted = [(px + off_x, py + off_y, pt) for px, py, pt in path_points]

        click_num = None
        path_ok = True
        try:
            if step.button:
                click_num = self.input.mouse_down(cur_x, cur_y, step.button)

            final_x, final_y = self.input.replay_path(
                path_points=adjusted,
                jitter_px=1,
            )
        except Exception:
            final_x, final_y = cur_x, cur_y
            path_ok = False
            log.exception("  路径回放异常")
        finally:
            if step.button:
                try:
                    self.input.mouse_up(final_x, final_y, step.button, click_num)
                except Exception:
                    log.exception("  mouse_up 失败")

        if not self._alive(gen):
            return

        if path_ok:
            log.info(
                "  精确路径回放: %d点 (%d,%d)→(%d,%d) %.2fs",
                len(path_points), cur_x, cur_y, final_x, final_y,
                step.recorded_duration,
            )
        time.sleep(random.uniform(0.02, 0.08))

    def _do_key_combo(self, step: KeyComboStep, gen: int) -> None:
        """KEY_COMBO: 组合按键（hold_tap/sequence/all_hold）"""
        if not self._alive(gen):
            return

        if not step.combo_keys:
            log.warning("组合按键: 未设置按键，跳过")
            return

        keys = _parse_comma_keys(step.combo_keys)

        if len(keys) == 1:
            self.input.press_key(keys[0])
            return

        mode = step.combo_mode

        if mode == "hold_tap":
            self.input.key_combo_staggered(
                keys_hold=keys[:-1],
                keys_tap=[keys[-1]],
                hold_duration=0.1,
                stop_check=lambda: not self._alive(gen),
            )
        elif mode == "sequence":
            for i, key in enumerate(keys):
                if not self._alive(gen):
                    return
                self.input.press_key(key)
                if i < len(keys) - 1:
                    time.sleep(random.uniform(0.05, 0.15))
        elif mode == "all_hold":
            self.input.key_combo_staggered(
                keys_hold=keys,
                keys_tap=[],
                hold_duration=step.hold_duration,
                stop_check=lambda: not self._alive(gen),
            )

        log.info("  组合按键: %s 模式=%s", keys, mode)

    def _do_multi_key_sequence(self, step: MultiKeySequenceStep, gen: int) -> None:
        """MULTI_KEY_SEQUENCE: 按顺序执行多个按键"""
        if not step.key_sequence:
            log.warning("多键序列: 未设置按键序列，跳过")
            return

        keys = _parse_comma_keys(step.key_sequence)
        if not keys:
            return

        for i, key in enumerate(keys):
            if not self._alive(gen):
                log.info("  多键序列被中断")
                return

            time.sleep(random.uniform(0.01, 0.05))
            self.input.press_key(key)

            if i < len(keys) - 1:
                interval = random.uniform(step.key_interval_min, step.key_interval_max)
                time.sleep(interval)

        log.info("  多键序列完成: %d 个按键", len(keys))

    def _do_idle_behavior(self, step: IdleBehaviorStep, gen: int) -> None:
        """IDLE_BEHAVIOR: 随机 idle 微行为"""
        duration = step.idle_duration * random.uniform(0.9, 1.1)
        deadline = time.monotonic() + duration

        idle_keys = []
        if step.idle_actions:
            idle_keys = _parse_comma_keys(step.idle_actions)

        count = 0
        while True:
            if not self._alive(gen):
                return

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break

            sub_wait = random.uniform(0.3, 0.8)
            time.sleep(min(sub_wait, remaining))

            cx, cy = self.input.get_mouse_position()
            jitter = max(0, step.jitter_intensity)
            ox = random.randint(-jitter, jitter)
            oy = random.randint(-jitter, jitter)
            self.input.move_to(cx + ox, cy + oy, duration=random.uniform(0.05, 0.12))

            if idle_keys and random.random() < step.idle_action_chance:
                key = random.choice(idle_keys)
                self.input.press_key(key)
                log.debug("  idle 随机按键: %s", key)

            count += 1
            if count % 5 == 0:
                log.debug("  idle 进行中, 剩余 %.1fs", max(0, deadline - time.monotonic()))

        log.info("  随机idle完成: %.1fs, %d 次微操作", duration, count)

    def _do_start_timer(self, step: StartTimerStep) -> None:
        """START_TIMER: 启动命名计时器"""
        if not step.timer_name:
            log.warning("启动计时器: 未设置计时器名称，跳过")
            return
        if self._evaluator:
            self._evaluator.start_timer(step.timer_name)
            timeout_info = f", 超时 {step.timer_timeout}s" if step.timer_timeout > 0 else ""
            log.info("  启动计时器: %s%s", step.timer_name, timeout_info)
        else:
            log.warning("  求值器未初始化，无法启动计时器")
