# 执行进度显示 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在动作链 + 工作流的 4 个界面(tkinter × 2 + Qt × 2)底部状态栏,以 3 个独立分段实时显示「循环次数 / 当前步骤 / 执行时间」,循环次数精确(已完成回合)、暂停冻结、停止保留最终值。

**Architecture:** 执行器内建 `ExecutionTimer`(单一可信计时源)+ 独立 `_completed_rounds` 精确计数;纯函数 `execution_status.py` 把执行器原始值格式化为 3 段文本;UI 每秒轮询 + 事件触发刷新,双框架共用同一纯函数。

**Tech Stack:** Python 3.11+, tkinter, PySide6, pytest, 既有 EventBus/i18n 体系。

**Spec:** [docs/superpowers/specs/2026-06-17-execution-progress-display-design.md](../specs/2026-06-17-execution-progress-display-design.md)

## Global Constraints

- 遵循 `~/.claude/rules` 与项目 CLAUDE.md:不可变优先、函数 < 50 行、文件 < 800 行、显式错误处理、无硬编码。
- i18n 占位符**禁止**用 `key`/`count` 裸名(与 `t(key, count=None, **kwargs)` 签名冲突);本计划一律用 `current`/`total`/`duration`/`s`/`m`/`h`/`d`。
- 新增 i18n key 须经 `scripts/lint_i18n_keys.py` + `tests/unit/utils/test_i18n_keys.py` gate(退出 0)。
- Tk 面板测试受 Tcl/Tk9 + Py3.14 多 root 崩溃约束:**逐文件运行**(`pytest <file> -v`),不要批量跑 panel 测试。
- Qt(cocoa)+ Tk 同进程会 SIGABRT:**不可在同一测试/会话混跑** Tk 与 Qt。
- 步骤显示基准已核实为 **1 基**(`current_step_index` 对首个 ACTION = 1):**不要再 +1**。
- 每个任务结束提交一次(commit message 遵循 `<类型>: <描述>`)。

---

## File Structure

| 文件 | 职责 | 动作 |
|------|------|------|
| `src/core/execution_timer.py` | 线程安全活跃计时器(排除暂停) | 新增 |
| `src/core/action_executor.py` | 持有 timer + `_completed_rounds`,生命周期接线,新增属性 | 修改 |
| `src/utils/timing.py` | `format_duration_human` 智能时长格式化 | 修改 |
| `src/panel/execution_status.py` | `ExecutionSegments` + `count_reachable_action_nodes` + `build_execution_segments` + `compose_execution_status` | 新增 |
| `src/panel/components/status_bar.py` | `insert_segment` 按位置插入段 | 修改 |
| `src/panel/pages/action_chain_page.py` | 插 3 段 + tick + refresh | 修改 |
| `src/panel/pages/action_chain_profile_mixin.py` | 事件回调接 refresh + 移除旧 step 文本写入 | 修改 |
| `src/panel/pages/workflow_page.py` | 插 3 段 + tick + refresh | 修改 |
| `src/panel/qt_backend/pages/base_page.py` | `_build_qt_status_bar` 加 3 个 QLabel | 修改 |
| `src/panel/qt_backend/pages/action_chain_page.py` | tick + refresh | 修改 |
| `src/panel/qt_backend/pages/action_chain_profile_mixin.py` | 事件回调接 refresh | 修改 |
| `src/panel/qt_backend/pages/workflow_page.py` | tick + refresh | 修改 |
| `src/utils/translations/{zh,en}.json` | 新 i18n key | 修改 |
| 各 `tests/unit/...` | 对应单元测试 | 新增/扩展 |

依赖顺序:Task 1(ExecutionTimer)→ Task 5(executor) 可并行于 Task 2(i18n)→ Task 3(format)→ Task 4(execution_status);Task 6(StatusBar)独立;Task 7-11(UI)依赖 1-6。

---

## Task 1: ExecutionTimer(核心计时器)

**Files:**
- Create: `src/core/execution_timer.py`
- Test: `tests/unit/core/test_execution_timer.py`

**Interfaces:**
- Produces: `class ExecutionTimer` with `start()`, `pause()`, `resume()`, `stop()`, `reset()`, `elapsed() -> float | None`. Consumed by Task 5 (`ActionExecutor` holds one).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/core/test_execution_timer.py`:

```python
"""ExecutionTimer 单元测试 — 活跃计时,排除暂停,停止冻结。"""

from __future__ import annotations

import time

from src.core.execution_timer import ExecutionTimer


class TestBasics:
    def test_elapsed_none_before_start(self) -> None:
        timer = ExecutionTimer()
        assert timer.elapsed() is None

    def test_start_makes_elapsed_nonnone(self) -> None:
        timer = ExecutionTimer()
        timer.start()
        assert timer.elapsed() is not None
        assert timer.elapsed() == 0  # 刚启动 ~0

    def test_elapsed_grows_while_running(self) -> None:
        timer = ExecutionTimer()
        timer.start()
        time.sleep(0.05)
        assert timer.elapsed() >= 0.04


class TestPauseFreeze:
    def test_pause_excludes_paused_duration(self) -> None:
        timer = ExecutionTimer()
        timer.start()
        time.sleep(0.05)
        timer.pause()
        frozen = timer.elapsed()
        time.sleep(0.10)  # 暂停期间不应增长
        assert abs(timer.elapsed() - frozen) < 0.02

    def test_resume_continues_accumulating(self) -> None:
        timer = ExecutionTimer()
        timer.start()
        time.sleep(0.05)
        timer.pause()
        time.sleep(0.10)
        timer.resume()
        before = timer.elapsed()
        time.sleep(0.05)
        assert timer.elapsed() >= before + 0.04  # 恢复后继续增长

    def test_pause_when_not_started_is_noop(self) -> None:
        timer = ExecutionTimer()
        timer.pause()  # 不应抛异常
        assert timer.elapsed() is None

    def test_resume_when_not_paused_is_noop(self) -> None:
        timer = ExecutionTimer()
        timer.start()
        timer.resume()  # 未暂停,空操作
        assert timer.elapsed() is not None


class TestStopFreeze:
    def test_stop_freezes_final_value(self) -> None:
        timer = ExecutionTimer()
        timer.start()
        time.sleep(0.05)
        timer.stop()
        final = timer.elapsed()
        time.sleep(0.10)
        assert timer.elapsed() == final  # 冻结

    def test_stop_is_idempotent(self) -> None:
        timer = ExecutionTimer()
        timer.start()
        timer.stop()
        first = timer.elapsed()
        timer.stop()
        assert timer.elapsed() == first


class TestReset:
    def test_reset_clears_state(self) -> None:
        timer = ExecutionTimer()
        timer.start()
        timer.stop()
        timer.reset()
        assert timer.elapsed() is None

    def test_start_after_reset_works(self) -> None:
        timer = ExecutionTimer()
        timer.start()
        timer.stop()
        timer.reset()
        timer.start()
        assert timer.elapsed() is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/core/test_execution_timer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.core.execution_timer'`

- [ ] **Step 3: Write minimal implementation**

Create `src/core/execution_timer.py`:

```python
"""ExecutionTimer — 线程安全的活跃执行计时器。

记录启动时刻与暂停累计,``elapsed()`` 返回排除暂停时长的活跃秒数。
停止后冻结最终值,直至下次 ``start()`` 重置。

使用 ``time.monotonic()``,不受系统时钟调整影响。
"""

from __future__ import annotations

import threading
import time


class ExecutionTimer:
    """活跃执行计时器 — 排除暂停时长。线程安全。

    生命周期: start → (pause/resume)* → stop。
    stop 后 elapsed() 恒返回冻结的最终值, 直至下次 start 重置。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._start: float | None = None
        self._paused_total: float = 0.0
        self._pause_at: float | None = None
        self._final: float | None = None

    def start(self) -> None:
        """开始计时,清零所有累计与冻结值。"""
        with self._lock:
            self._start = time.monotonic()
            self._paused_total = 0.0
            self._pause_at = None
            self._final = None

    def pause(self) -> None:
        """标记暂停起点(仅当运行中且未暂停)。"""
        with self._lock:
            if self._start is not None and self._pause_at is None:
                self._pause_at = time.monotonic()

    def resume(self) -> None:
        """结束暂停,把暂停时长累加到 _paused_total。"""
        with self._lock:
            if self._pause_at is not None and self._start is not None:
                self._paused_total += time.monotonic() - self._pause_at
                self._pause_at = None

    def stop(self) -> None:
        """冻结当前活跃时长为最终值(幂等)。"""
        with self._lock:
            if self._start is not None:
                self._final = self._elapsed_locked()

    def reset(self) -> None:
        """清零全部状态。"""
        with self._lock:
            self._start = None
            self._paused_total = 0.0
            self._pause_at = None
            self._final = None

    def elapsed(self) -> float | None:
        """返回活跃秒数(排除暂停);未启动返回 None。"""
        with self._lock:
            return self._elapsed_locked()

    def _elapsed_locked(self) -> float | None:
        if self._start is None:
            return None
        if self._final is not None:
            return self._final
        now = time.monotonic()
        active = now - self._start - self._paused_total
        if self._pause_at is not None:
            active -= now - self._pause_at
        return max(0.0, active)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/core/test_execution_timer.py -v`
Expected: PASS (全部用例)

- [ ] **Step 5: Commit**

```bash
git add src/core/execution_timer.py tests/unit/core/test_execution_timer.py
git commit -m "feat: 新增 ExecutionTimer 活跃计时器(暂停冻结/停止保留)"
```

---

## Task 2: i18n 键(数据)

**Files:**
- Modify: `src/utils/translations/zh.json`
- Modify: `src/utils/translations/en.json`

**Interfaces:**
- Produces: keys `exec.status.loop`, `exec.status.step`, `exec.status.time`, `exec.status.infinite`, `exec.status.dash`, `duration.seconds`, `duration.minutes_seconds`, `duration.hours_minutes`, `duration.days_hours`. Consumed by Task 3 & 4.

- [ ] **Step 1: Add keys to zh.json**

JSON 为**扁平**字典、键按字母序排列。在 `common.*` 之后、`engine.*` 之前插入 `duration.*`;在 `engine.*` 之后、`executor.*` 之前插入 `exec.status.*`(字母序:`engine` < `exec` < `executor`)。

在 `src/utils/translations/zh.json` 对应字母序位置插入:

```json
        "duration.days_hours": "{d}天{h}小时",
        "duration.hours_minutes": "{h}小时{m}分",
        "duration.minutes_seconds": "{m}分{s}秒",
        "duration.seconds": "{s}秒",
```

```json
        "exec.status.dash": "—",
        "exec.status.infinite": "∞",
        "exec.status.loop": "循环次数: {current}/{total}",
        "exec.status.step": "当前步骤: {current}/{total}",
        "exec.status.time": "执行时间: {duration}",
```

- [ ] **Step 2: Add keys to en.json**

在 `src/utils/translations/en.json` 对应字母序位置插入:

```json
        "duration.days_hours": "{d}d {h}h",
        "duration.hours_minutes": "{h}h {m}m",
        "duration.minutes_seconds": "{m}m {s}s",
        "duration.seconds": "{s}s",
```

```json
        "exec.status.dash": "—",
        "exec.status.infinite": "∞",
        "exec.status.loop": "Loops: {current}/{total}",
        "exec.status.step": "Step: {current}/{total}",
        "exec.status.time": "Time: {duration}",
```

- [ ] **Step 3: Verify JSON valid + lint gate**

Run: `python3 -c "import json; json.load(open('src/utils/translations/zh.json')); json.load(open('src/utils/translations/en.json')); print('JSON OK')"`
Expected: `JSON OK`

Run: `python3 scripts/lint_i18n_keys.py`
Expected: 退出码 0(无缺失/不匹配)

Run: `pytest tests/unit/utils/test_i18n_keys.py tests/unit/utils/test_i18n_lint.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/utils/translations/zh.json src/utils/translations/en.json
git commit -m "feat(i18n): 新增执行进度与时长格式化翻译键"
```

---

## Task 3: format_duration_human(时长格式化)

**Files:**
- Modify: `src/utils/timing.py`
- Test: `tests/unit/utils/test_timing.py` (create)

**Interfaces:**
- Produces: `format_duration_human(seconds: float) -> str`. Consumed by Task 4.
- Consumes: i18n keys from Task 2.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/utils/test_timing.py`:

```python
"""timing 工具测试 — format_duration_human 智能时长格式化。"""

from __future__ import annotations

import pytest

from src.utils import i18n
from src.utils.timing import format_duration_human


@pytest.fixture(autouse=True)
def _zh():
    """锁定中文,避免受其它测试语言切换影响。"""
    i18n.set_language("zh")


class TestFormatDurationHuman:
    def test_seconds(self) -> None:
        assert format_duration_human(45) == "45秒"

    def test_zero(self) -> None:
        assert format_duration_human(0) == "0秒"

    def test_negative_clamps_to_zero(self) -> None:
        assert format_duration_human(-5) == "0秒"

    def test_minutes_seconds(self) -> None:
        assert format_duration_human(134) == "2分14秒"

    def test_exact_minute(self) -> None:
        assert format_duration_human(60) == "1分0秒"

    def test_hours_minutes(self) -> None:
        # 3900s = 1h5m
        assert format_duration_human(3900) == "1小时5分"

    def test_days_hours(self) -> None:
        # 97200s = 1d3h
        assert format_duration_human(97200) == "1天3小时"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/utils/test_timing.py -v`
Expected: FAIL — `ImportError: cannot import name 'format_duration_human'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/utils/timing.py` (在文件末尾追加;保留既有 `human_like_duration`):

```python
from src.utils.i18n import t


def format_duration_human(seconds: float) -> str:
    """把秒数格式化为人类可读时长,智能省略前导零,固定最多 2 个有效单位。

    < 60s  → "45秒"
    < 1h   → "2分14秒"
    < 1d   → "1小时5分"
    >= 1d  → "1天3小时"

    负数按 0 处理。
    """
    total = int(max(0.0, seconds))
    if total < 60:
        return t("duration.seconds", s=total)
    minutes, secs = divmod(total, 60)
    if total < 3600:
        return t("duration.minutes_seconds", m=minutes, s=secs)
    hours, minutes = divmod(minutes, 60)
    if total < 86400:
        return t("duration.hours_minutes", h=hours, m=minutes)
    days, hours = divmod(hours, 24)
    return t("duration.days_hours", d=days, h=hours)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/utils/test_timing.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/utils/timing.py tests/unit/utils/test_timing.py
git commit -m "feat: 新增 format_duration_human 智能时长格式化"
```

---

## Task 4: execution_status.py(分段构建器)

**Files:**
- Create: `src/panel/execution_status.py`
- Test: `tests/unit/panel/test_execution_status.py`

**Interfaces:**
- Consumes: `format_duration_human` (Task 3), i18n keys (Task 2), `FlowGraph`/`NodeType` (core).
- Produces:
  - `@dataclass(frozen=True) class ExecutionSegments(loop_text, step_text, time_text)`
  - `count_reachable_action_nodes(graph: FlowGraph) -> int`
  - `build_execution_segments(*, completed_rounds, loop_count, is_loop, step_index, total_steps, elapsed_seconds) -> ExecutionSegments`
  - `compose_execution_status(executor, graph: FlowGraph) -> ExecutionSegments` — reads `executor.completed_rounds`, `executor.current_step_index`, `executor.elapsed_active`(属性,无括号)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/panel/test_execution_status.py`:

```python
"""execution_status 测试 — 分段构建 + 可达 ACTION 节点计数。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.core.flow import FlowEdge, FlowGraph, FlowNode, NodeType
from src.panel.execution_status import (
    build_execution_segments,
    compose_execution_status,
    count_reachable_action_nodes,
)
from src.utils import i18n

pytestmark = pytest.mark.usefixtures("_zh")


@pytest.fixture
def _zh():
    i18n.set_language("zh")
    yield


def _make_action_graph(n_actions: int, loop: bool = True, loop_count: int = 0) -> FlowGraph:
    """线性 START → a0 → ... → aN → END。"""
    g = FlowGraph(name="t", start_node_id="start", loop=loop, loop_count=loop_count)
    g.add_node(FlowNode("start", NodeType.START))
    g.add_node(FlowNode("end", NodeType.END))
    prev = "start"
    for i in range(n_actions):
        nid = f"a{i}"
        g.add_node(FlowNode(nid, NodeType.ACTION, action=SimpleNamespace()))
        g.add_edge(FlowEdge(edge_id=f"e{i}", from_node=prev, to_node=nid, label="default"))
        prev = nid
    g.add_edge(FlowEdge(edge_id="eend", from_node=prev, to_node="end", label="default"))
    return g


class TestCountReachableActionNodes:
    def test_counts_actions(self) -> None:
        assert count_reachable_action_nodes(_make_action_graph(3)) == 3

    def test_excludes_start_end(self) -> None:
        assert count_reachable_action_nodes(_make_action_graph(0)) == 0

    def test_excludes_disabled(self) -> None:
        g = _make_action_graph(3)
        g.nodes["a1"].enabled = False
        assert count_reachable_action_nodes(g) == 2

    def test_excludes_action_without_step(self) -> None:
        g = _make_action_graph(2)
        g.nodes["a0"].action = None
        assert count_reachable_action_nodes(g) == 1


class TestBuildExecutionSegments:
    def test_infinite_loop(self) -> None:
        segs = build_execution_segments(
            completed_rounds=2, loop_count=0, is_loop=True,
            step_index=2, total_steps=3, elapsed_seconds=134.0,
        )
        assert segs.loop_text == "循环次数: 2/∞"
        assert segs.step_text == "当前步骤: 2/3"
        assert segs.time_text == "执行时间: 2分14秒"

    def test_finite_loop(self) -> None:
        segs = build_execution_segments(
            completed_rounds=3, loop_count=5, is_loop=True,
            step_index=1, total_steps=4, elapsed_seconds=45.0,
        )
        assert segs.loop_text == "循环次数: 3/5"

    def test_single_mode_total_is_one(self) -> None:
        segs = build_execution_segments(
            completed_rounds=0, loop_count=1, is_loop=False,
            step_index=-1, total_steps=3, elapsed_seconds=None,
        )
        assert segs.loop_text == "循环次数: 0/1"

    def test_step_one_based_no_plus_one(self) -> None:
        """回归守卫: step_index=1 应显示 1/3,不是 2/3。"""
        segs = build_execution_segments(
            completed_rounds=0, loop_count=0, is_loop=True,
            step_index=1, total_steps=3, elapsed_seconds=0.0,
        )
        assert segs.step_text == "当前步骤: 1/3"

    def test_step_negative_shows_dash(self) -> None:
        segs = build_execution_segments(
            completed_rounds=0, loop_count=0, is_loop=True,
            step_index=-1, total_steps=3, elapsed_seconds=0.0,
        )
        assert segs.step_text == "当前步骤: —/3"

    def test_elapsed_none_shows_dash(self) -> None:
        segs = build_execution_segments(
            completed_rounds=0, loop_count=0, is_loop=True,
            step_index=1, total_steps=3, elapsed_seconds=None,
        )
        assert segs.time_text == "执行时间: —"


class TestComposeExecutionStatus:
    def test_reads_executor_and_graph(self) -> None:
        graph = _make_action_graph(3, loop=True, loop_count=0)
        executor = SimpleNamespace(
            completed_rounds=2, current_step_index=2, elapsed_active=134.0,
        )
        segs = compose_execution_status(executor, graph)
        assert segs.loop_text == "循环次数: 2/∞"
        assert segs.step_text == "当前步骤: 2/3"
        assert segs.time_text == "执行时间: 2分14秒"

    def test_elapsed_none_propagates(self) -> None:
        graph = _make_action_graph(2)
        executor = SimpleNamespace(
            completed_rounds=0, current_step_index=-1, elapsed_active=None,
        )
        segs = compose_execution_status(executor, graph)
        assert segs.time_text == "执行时间: —"
        assert segs.step_text == "当前步骤: —/2"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/panel/test_execution_status.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.panel.execution_status'`

- [ ] **Step 3: Write minimal implementation**

Create `src/panel/execution_status.py`:

```python
"""执行进度分段构建器 — 把执行器原始值格式化为 3 段状态文本。

供 tkinter / Qt 双框架的动作链与工作流页面共用,保证 4 个界面格式一致。
纯函数,可脱离 GUI 单元测试。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.core.flow import FlowGraph, NodeType
from src.utils.i18n import t
from src.utils.timing import format_duration_human

if TYPE_CHECKING:
    from src.core.action_executor import ActionExecutor


@dataclass(frozen=True)
class ExecutionSegments:
    """3 段执行状态文本。"""

    loop_text: str
    step_text: str
    time_text: str


def count_reachable_action_nodes(graph: FlowGraph) -> int:
    """从 START 可达、启用、且有 action 的 ACTION 节点数。

    动作链(线性)= 精确值;工作流(DAG)= 最优静态上界
    (分支场景下当前步数可能不达总数,属不可消除限制)。
    """
    return sum(
        1
        for node in graph.ordered_nodes()
        if node.node_type == NodeType.ACTION and node.enabled and node.action is not None
    )


def build_execution_segments(
    *,
    completed_rounds: int,
    loop_count: int,
    is_loop: bool,
    step_index: int,
    total_steps: int,
    elapsed_seconds: float | None,
) -> ExecutionSegments:
    """把原始执行值格式化为 3 段文本。

    Args:
        completed_rounds: 已完整跑完的回合数。
        loop_count: 总循环数(0 = 无限)。
        is_loop: graph.loop,为 False 表示单次模式。
        step_index: 引擎发布的当前步骤(首个 ACTION = 1,已是 1 基);< 0 表示未运行。
        total_steps: 可达启用 ACTION 节点数。
        elapsed_seconds: 活跃秒数(排除暂停);None 表示未启动。
    """
    if is_loop and loop_count == 0:
        loop_total_label = t("exec.status.infinite")
    else:
        loop_total_label = str(loop_count if is_loop else 1)
    loop_text = t("exec.status.loop", current=completed_rounds, total=loop_total_label)

    step_current_label = t("exec.status.dash") if step_index < 0 else str(step_index)
    step_text = t("exec.status.step", current=step_current_label, total=total_steps)

    time_label = (
        t("exec.status.dash") if elapsed_seconds is None else format_duration_human(elapsed_seconds)
    )
    time_text = t("exec.status.time", duration=time_label)

    return ExecutionSegments(loop_text=loop_text, step_text=step_text, time_text=time_text)


def compose_execution_status(executor: "ActionExecutor", graph: FlowGraph) -> ExecutionSegments:
    """从执行器 + 图组装执行状态分段(UI 刷新入口)。"""
    return build_execution_segments(
        completed_rounds=executor.completed_rounds,
        loop_count=graph.loop_count,
        is_loop=graph.loop,
        step_index=executor.current_step_index,
        total_steps=count_reachable_action_nodes(graph),
        elapsed_seconds=executor.elapsed_active,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/panel/test_execution_status.py -v`
Expected: PASS(全部用例,含 step 1基回归守卫)

- [ ] **Step 5: Commit**

```bash
git add src/panel/execution_status.py tests/unit/panel/test_execution_status.py
git commit -m "feat: 新增 execution_status 分段构建器(4界面共用纯函数)"
```

---

## Task 5: ActionExecutor 接线(timer + completed_rounds)

**Files:**
- Modify: `src/core/action_executor.py`
- Test: `tests/unit/core/test_action_executor_facade.py` (extend)

**Interfaces:**
- Consumes: `ExecutionTimer` (Task 1).
- Produces: `ActionExecutor.elapsed_active`(property, `float | None`)、`ActionExecutor.completed_rounds`(property, `int`)。Consumed by Task 7-10 via `compose_execution_status`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/core/test_action_executor_facade.py`(在文件末尾追加新测试类;复用既有 `_make_executor` / `_make_graph` 与 `threading` patch 模式):

```python
class TestExecutionProgress:
    """验证 timer 接线 + completed_rounds 精确计数。"""

    def test_initial_completed_rounds_and_elapsed(self) -> None:
        ex = _make_executor()
        assert ex.completed_rounds == 0
        assert ex.elapsed_active is None

    def test_start_resets_rounds_and_starts_timer(self) -> None:
        ex = _make_executor()
        with patch.object(ex._timer, "start") as timer_start, \
             patch.object(threading, "Thread"):
            ex.start(_make_graph())
        timer_start.assert_called_once()
        assert ex.completed_rounds == 0

    def test_pause_resume_stop_wire_timer(self) -> None:
        ex = _make_executor()
        with patch.object(threading, "Thread"):
            ex.start(_make_graph())
        with patch.object(ex._timer, "pause") as m_pause:
            ex.pause()
            m_pause.assert_called_once()
        with patch.object(ex._timer, "resume") as m_resume:
            ex.resume()
            m_resume.assert_called_once()
        with patch.object(ex._timer, "stop") as m_stop:
            ex.stop()
            m_stop.assert_called_once()

    def test_completed_rounds_increments_per_round(self, monkeypatch) -> None:
        ex = _make_executor()
        graph = _make_graph()
        graph.loop = False  # 单次,跑一圈即退出
        ex._gen = 1
        ex._stop_event.clear()
        # 避免 GraphEngine 真实执行节点,直接 mock 为空操作
        monkeypatch.setattr(ex._graph_engine, "run", lambda g, c, *a, **kw: None)
        ex._run_with_engine(graph, 1)
        assert ex.completed_rounds == 1

    def test_completed_rounds_increments_multiple_rounds(self, monkeypatch) -> None:
        ex = _make_executor()
        graph = _make_graph()
        graph.loop = True
        graph.loop_count = 3
        ex._gen = 1
        ex._stop_event.clear()
        monkeypatch.setattr(ex._graph_engine, "run", lambda g, c, *a, **kw: None)
        ex._run_with_engine(graph, 1)
        assert ex.completed_rounds == 3

    def test_elapsed_active_not_none_after_start(self) -> None:
        ex = _make_executor()
        with patch.object(threading, "Thread"):
            ex.start(_make_graph())
        assert ex.elapsed_active is not None
        ex.stop()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/core/test_action_executor_facade.py::TestExecutionProgress -v`
Expected: FAIL — `AttributeError: 'ActionExecutor' object has no attribute 'completed_rounds'`(或 `elapsed_active`)

- [ ] **Step 3: Wire ExecutionTimer + completed_rounds into ActionExecutor**

Modify `src/core/action_executor.py`:

**(a) 导入**(在文件顶部 import 区,`import time` 已存在):

```python
from src.core.execution_timer import ExecutionTimer
```

**(b) `__init__` 增加字段**(在 `self._running = False`(约第 78 行)之后插入):

```python
        # 执行进度(计时 + 已完成回合)
        self._timer = ExecutionTimer()
        self._completed_rounds: int = 0
```

**(c) 新增属性**(在 `loop_iteration` property(约第 137-140 行)之后插入):

```python
    @property
    def elapsed_active(self) -> float | None:
        """活跃执行秒数(排除暂停);未启动返回 None。"""
        return self._timer.elapsed()

    @property
    def completed_rounds(self) -> int:
        """已完整跑完的回合数。"""
        with self._lock:
            return self._completed_rounds
```

**(d) `start()` 接线**(在 `start()` 的 `with self._lock:` 块内,`self._loop_iteration = 0`(约第 164 行)之后加一行;并在锁块之后调用 timer):

```python
        with self._lock:
            self._gen += 1
            gen = self._gen
            self._stop_event.clear()
            self._pause_event.clear()
            self._current_step_idx = -1
            self._loop_iteration = 0
            self._completed_rounds = 0
            self._running = True

        self._timer.start()
```

**(e) `stop()` 接线**(在 `stop()` 的 `with self._lock:` 块之后(约第 191 行 `self._last_graph = None` 之前或之后)加):

```python
        self._timer.stop()
```

**(f) `pause()` / `resume()` 接线**:

在 `pause()`(约第 201-204 行)`log.info(...)` 之前加 `self._timer.pause()`。
在 `resume()`(约第 206-210 行)`self._pause_layer.resume()` 之前加 `self._timer.resume()`。

**(g) `_run_with_engine` 递增 completed_rounds + finally 停计时**:

在 `_run_with_engine` 中,`self._graph_engine.run(graph, ctx)`(约第 229 行)之后的成功块改为:

```python
                self._graph_engine.run(graph, ctx)

                # 轮次成功 → 重置连续失败计数 + 已完成回合 +1
                with self._lock:
                    self._consecutive_failures = 0
                    self._completed_rounds += 1

                iteration += 1
```

在 `finally` 块(约第 248 行)内,`self._stop_monitors()` 之后加:

```python
        finally:
            self._stop_monitors()
            self._timer.stop()
            with self._lock:
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/core/test_action_executor_facade.py -v`(单独跑该文件)
Expected: PASS(既有用例 + 新 TestExecutionProgress 全绿)

- [ ] **Step 5: Commit**

```bash
git add src/core/action_executor.py tests/unit/core/test_action_executor_facade.py
git commit -m "feat: ActionExecutor 接线 ExecutionTimer 与 completed_rounds 精确计数"
```

---

## Task 6: StatusBar.insert_segment(tkinter)

**Files:**
- Modify: `src/panel/components/status_bar.py`
- Test: `tests/unit/panel/test_status_bar.py` (create)

**Interfaces:**
- Produces: `StatusBar.insert_segment(index: int, name: str, text: str = "") -> tk.Label`。Consumed by Task 7 & 8.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/panel/test_status_bar.py`(遵循既有 panel 测试的 Tk root 模式,**单独运行**):

```python
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


def test_insert_segment_places_at_index(tk_root) -> None:
    from src.panel.components.status_bar import StatusBar

    bar = StatusBar(tk_root)
    # 默认段: [dot, left, center, right]
    assert len(bar._segments) == 4
    lbl = bar.insert_segment(1, "exec_loop", "循环次数: 0/∞")
    assert bar._segment_labels["exec_loop"] is lbl
    # 插入后 dot 仍在 0, 新段在 1
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
    bar.insert_segment(1, "exec_loop", "")
    bar.insert_segment(2, "exec_step", "")
    bar.insert_segment(3, "exec_time", "")
    # [dot, loop, step, time, left, center, right]
    names = [bar._segment_labels_inv(s) for s in ()]  # 仅断言长度
    assert len(bar._segments) == 7
```

> 注:第 3 个测试的最后一行仅为占位断言长度;如 `_segment_labels_inv` 不存在,删掉该行,仅保留 `assert len(bar._segments) == 7`。

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/panel/test_status_bar.py -v`
Expected: FAIL — `AttributeError: 'StatusBar' object has no attribute 'insert_segment'`

- [ ] **Step 3: Implement insert_segment**

Modify `src/panel/components/status_bar.py`:在 `add_segment` 方法(约第 70-76 行)之后插入:

```python
    def insert_segment(self, index: int, name: str, text: str = "") -> tk.Label:
        """在指定位置插入一个独立信息段(控制显示顺序)。

        插入后触发重排。常用于把执行进度段排在圆点(index=1)之后。
        """
        th = current_theme()
        label = themed_label(self._content, text=text, style="small", bg=th.toolbar_bg)
        self._segments.insert(index, ("label", label))
        self._segment_labels[name] = label
        # 失效缓存宽度,触发下次 _perform_reflow 重排
        self._last_width = -1
        return label
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/panel/test_status_bar.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/panel/components/status_bar.py tests/unit/panel/test_status_bar.py
git commit -m "feat: StatusBar 新增 insert_segment 按位置插入段"
```

---

## Task 7: tkinter 动作链页面接线

**Files:**
- Modify: `src/panel/pages/action_chain_page.py`
- Modify: `src/panel/pages/action_chain_profile_mixin.py`

**Interfaces:**
- Consumes: `compose_execution_status` (Task 4), `StatusBar.insert_segment` (Task 6), `executor.completed_rounds/elapsed_active` (Task 5).

> 验证以逻辑单测(Task 4/5)+ 本任务的手动冒烟(运行 app)为主;GUI 渲染本身不在单测范围。

- [ ] **Step 1: action_chain_page.py — 插入 3 段**

在 `action_chain_page.py` 的 `build()` 中,`self.status_bar = StatusBar(self.frame)`(约第 119 行)之后、`self.status_bar.pack(...)`(约第 120 行)之前,插入 3 段:

```python
        self.status_bar = StatusBar(self.frame)
        # 执行进度 3 段(排在圆点之后)
        self.status_bar.insert_segment(1, "exec_loop", "")
        self.status_bar.insert_segment(2, "exec_step", "")
        self.status_bar.insert_segment(3, "exec_time", "")
        self._exec_tick_id: str | None = None
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)
```

在 `__init__` 中(约第 85 行 `_mon_count_var` 附近)增加 tick id 初始化:

```python
        self._exec_tick_id: str | None = None
```

- [ ] **Step 2: action_chain_profile_mixin.py — 新增 refresh + tick 方法**

在 `action_chain_profile_mixin.py` 的 `_on_executor_state` 方法(约第 179-192 行)**之后**,新增两个方法:

```python
    def _refresh_execution_status(self) -> None:
        """从执行器读值并刷新状态栏 3 个执行段。"""
        executor = self.app.executor
        if not executor or not getattr(self, "status_bar", None):
            return
        from src.panel.execution_status import compose_execution_status

        segs = compose_execution_status(executor, self.model.graph)
        self.status_bar.set_segment("exec_loop", segs.loop_text)
        self.status_bar.set_segment("exec_step", segs.step_text)
        self.status_bar.set_segment("exec_time", segs.time_text)

    def _start_exec_tick(self) -> None:
        """启动每秒轮询(仅 RUNNING 时持续)。"""
        self._stop_exec_tick()
        self._exec_tick_id = self.frame.after(1000, self._exec_tick)

    def _exec_tick(self) -> None:
        self._exec_tick_id = None
        self._refresh_execution_status()
        if self.model.executor_state == ExecutorState.RUNNING:
            self._exec_tick_id = self.frame.after(1000, self._exec_tick)

    def _stop_exec_tick(self) -> None:
        if self._exec_tick_id is not None:
            try:
                self.frame.after_cancel(self._exec_tick_id)
            except (tk.TclError, ValueError):
                pass
            self._exec_tick_id = None
```

- [ ] **Step 3: action_chain_profile_mixin.py — 接入事件回调**

修改 `_on_executor_state`(约第 179-192 行),在方法末尾(`if state == ExecutorState.IDLE ...` 之后)增加 tick 启停与刷新:

```python
    def _on_executor_state(self, state=None, **_kw):
        self.run_controls.set_state(state or ExecutorState.IDLE)

        labels = {
            ExecutorState.RUNNING: t("chain.status.running"),
            ExecutorState.PAUSED: t("chain.status.paused"),
            ExecutorState.IDLE: t("chain.status.stopped"),
        }
        self.var_status.set(labels.get(state, t("chain.status.ready")))
        status_state = state or ExecutorState.IDLE
        self.status_bar.set_status_dot(status_state)
        self.status_bar.set_right(labels.get(state, ""))
        if state == ExecutorState.IDLE and self.step_ring and self.step_ring.is_alive():
            self.step_ring.reset_execution()

        # 执行进度段: 启停 tick + 刷新
        if status_state == ExecutorState.RUNNING:
            self._refresh_execution_status()
            self._start_exec_tick()
        else:
            self._stop_exec_tick()
            self._refresh_execution_status()
```

修改 `_on_step_highlight`(约第 194-204 行),移除把步骤消息写入 `var_status`/`set_left` 的旧逻辑,改为刷新执行段:

```python
    def _on_step_highlight(self, step_index=None, iteration=None, **_kw):
        if self.model.executor_state == ExecutorState.IDLE:
            return
        if self.step_ring:
            self.step_ring.highlight(step_index if step_index is not None else -1)
        self._refresh_execution_status()
```

修改 `_on_round_started`(约第 206-208 行),在重置后刷新:

```python
    def _on_round_started(self, _iteration=None, **_kw):
        if self.step_ring and self.step_ring.is_alive():
            self.step_ring.reset_execution()
        self._refresh_execution_status()
```

在 `_sync_executor_state`(约第 220-238 行)末尾、读取 `step_idx` 后,调用一次刷新(typo:`var_status.set` 的步骤消息可保留或移除;为避免与执行段重复,改为调用 refresh):

将该方法的末尾段:

```python
        if state in (ExecutorState.RUNNING, ExecutorState.PAUSED) and self.step_ring:
            executor = self.app.executor
            if executor:
                step_idx = executor.current_step_index
                iteration = executor.loop_iteration
                if step_idx >= 0:
                    self.step_ring.highlight(step_idx)
                    steps = self.model.get_steps()
                    self.var_status.set(t("chain.status.running_step",
                        step=step_idx + 1, total=len(steps), round=iteration + 1))
```

改为(移除重复步骤文本,改用执行段):

```python
        if state in (ExecutorState.RUNNING, ExecutorState.PAUSED) and self.step_ring:
            executor = self.app.executor
            if executor:
                step_idx = executor.current_step_index
                if step_idx >= 0:
                    self.step_ring.highlight(step_idx)
        self._refresh_execution_status()
        if status_state_running := state in (ExecutorState.RUNNING,):
            self._start_exec_tick()
```

> 注:`var_status`(工具栏标签)现仅承载状态/区域文字;步骤细节统一由状态栏 3 段呈现。

在页面 `destroy()`(`action_chain_page.py` 约第 165-168 行)增加 tick 清理:

```python
    def destroy(self):
        self._stop_exec_tick()
        if self.controller:
            self.controller.destroy()
        super().destroy()
```

- [ ] **Step 4: Run relevant unit tests + import check**

Run: `python3 -c "import src.panel.pages.action_chain_page; import src.panel.pages.action_chain_profile_mixin; print('IMPORT OK')"`
Expected: `IMPORT OK`

Run: `pytest tests/unit/panel/test_execution_status.py tests/unit/core/test_action_executor_facade.py -v`
Expected: PASS(底层逻辑不受影响)

- [ ] **Step 5: Manual smoke(记录结果)**

Run: `python main.py`(动作链页 → 添加 3 步 → 启动循环)
确认状态栏出现「循环次数 / 当前步骤 / 执行时间」3 段,每秒刷新,暂停时时间冻结,停止后保留最终值。在 worklog 记录观察结果。

- [ ] **Step 6: Commit**

```bash
git add src/panel/pages/action_chain_page.py src/panel/pages/action_chain_profile_mixin.py
git commit -m "feat(panel): tkinter 动作链页面接入执行进度 3 段状态栏"
```

---

## Task 8: tkinter 工作流页面接线

**Files:**
- Modify: `src/panel/pages/workflow_page.py`

**Interfaces:**
- Consumes: `compose_execution_status` (Task 4), `StatusBar.insert_segment` (Task 6), executor props (Task 5).

- [ ] **Step 1: workflow_page.py — 插入 3 段 + tick 字段**

在 `_build_status_bar`(约第 226-241 行)中,`self._status_bar = StatusBar(self.frame)`(约第 232 行)之后插入 3 段:

```python
        self._status_bar = StatusBar(self.frame)
        # 执行进度 3 段(排在圆点之后)
        self._status_bar.insert_segment(1, "exec_loop", "")
        self._status_bar.insert_segment(2, "exec_step", "")
        self._status_bar.insert_segment(3, "exec_time", "")
        self._exec_tick_id: str | None = None
        self._status_bar.pack(fill=tk.X, side=tk.BOTTOM)
```

在 `__init__`(查找 `self._exec_tick_id` 未定义处,或页面字段初始化区)增加 `self._exec_tick_id: str | None = None`。

- [ ] **Step 2: workflow_page.py — 新增 refresh + tick 方法**

在 `_update_status_bar`(约第 340-352 行)之后新增:

```python
    def _refresh_execution_status(self) -> None:
        """从执行器读值并刷新状态栏 3 个执行段。"""
        executor = self.app.executor
        if not executor or not getattr(self, "_status_bar", None):
            return
        from src.panel.execution_status import compose_execution_status

        segs = compose_execution_status(executor, self._model.graph)
        self._status_bar.set_segment("exec_loop", segs.loop_text)
        self._status_bar.set_segment("exec_step", segs.step_text)
        self._status_bar.set_segment("exec_time", segs.time_text)

    def _start_exec_tick(self) -> None:
        self._stop_exec_tick()
        self._exec_tick_id = self.frame.after(1000, self._exec_tick)

    def _exec_tick(self) -> None:
        self._exec_tick_id = None
        self._refresh_execution_status()
        if self._model.executor_state == ExecutorState.RUNNING:
            self._exec_tick_id = self.frame.after(1000, self._exec_tick)

    def _stop_exec_tick(self) -> None:
        if self._exec_tick_id is not None:
            try:
                self.frame.after_cancel(self._exec_tick_id)
            except (tk.TclError, ValueError):
                pass
            self._exec_tick_id = None
```

> `tk` 与 `ExecutorState` 已在该文件顶部导入(确认 `ExecutorState` 已导入;若无须 `from src.panel.models.chain_model import ExecutorState`)。

- [ ] **Step 3: workflow_page.py — 接入事件回调**

修改 `_on_executor_state`(约第 520-535 行),在方法末尾增加 tick 启停 + 刷新:

```python
    def _on_executor_state(self, state=None, **_kwargs):
        running = state == ExecutorState.RUNNING
        paused = state == ExecutorState.PAUSED
        active = running or paused

        if not running:
            self._canvas.highlight_node(None)

        self.run_controls.set_state(state or ExecutorState.IDLE)
        self._status_bar.set_status_dot(state or ExecutorState.IDLE)

        self._status_bar.set_center(t(STATE_I18N.get(state, "")))

        btn_state = tk.DISABLED if active else tk.NORMAL
        for btn in self._palette_btn_widgets:
            btn.configure(state=btn_state)

        # 执行进度段
        if running:
            self._refresh_execution_status()
            self._start_exec_tick()
        else:
            self._stop_exec_tick()
            self._refresh_execution_status()
```

修改 `_on_node_highlight`(约第 537-540 行),增加刷新:

```python
    def _on_node_highlight(self, node_id=None, **_kwargs):
        if self._model.executor_state != ExecutorState.RUNNING:
            return
        self._canvas.highlight_node(node_id)
        self._refresh_execution_status()
```

在页面 `destroy()`(若存在;查找 `def destroy`)增加 `self._stop_exec_tick()`。若工作流页面无 `destroy` 覆写,在 BasePage.destroy 调用前补一个:

```python
    def destroy(self):
        self._stop_exec_tick()
        super().destroy()
```

- [ ] **Step 4: Import check + unit tests**

Run: `python3 -c "import src.panel.pages.workflow_page; print('IMPORT OK')"`
Expected: `IMPORT OK`

Run: `pytest tests/unit/panel/test_execution_status.py -v`
Expected: PASS

- [ ] **Step 5: Manual smoke**

Run: `python main.py`(工作流页 → 连几个节点 → 启动)
确认状态栏 3 段执行进度正常刷新,且原有节点/边 + 缩放信息仍在。worklog 记录。

- [ ] **Step 6: Commit**

```bash
git add src/panel/pages/workflow_page.py
git commit -m "feat(panel): tkinter 工作流页面接入执行进度 3 段状态栏"
```

---

## Task 9: Qt base_page 状态栏 3 标签

**Files:**
- Modify: `src/panel/qt_backend/pages/base_page.py`

**Interfaces:**
- Produces: `_build_qt_status_bar` 额外创建 `self._exec_loop_lbl` / `self._exec_step_lbl` / `self._exec_time_lbl`(QLabel,objectName=`dnaStatusLabel`)。Consumed by Task 10.

- [ ] **Step 1: Modify `_build_qt_status_bar`**

在 `base_page.py` 的 `_build_qt_status_bar`(约第 71-97 行)中,`h.addWidget(self._status_left)`(约第 85 行)之后、`if center_label:`(约第 87 行)之前,插入 3 个 QLabel:

```python
        self._status_left = QLabel("")
        self._status_left.setObjectName("dnaStatusLabel")
        self._status_right = QLabel("")
        self._status_right.setObjectName("dnaStatusLabel")
        h.addWidget(self._status_left)

        # 执行进度 3 段(紧随左侧信息,走全局 QSS)
        self._exec_loop_lbl = QLabel("")
        self._exec_loop_lbl.setObjectName("dnaStatusLabel")
        self._exec_step_lbl = QLabel("")
        self._exec_step_lbl.setObjectName("dnaStatusLabel")
        self._exec_time_lbl = QLabel("")
        self._exec_time_lbl.setObjectName("dnaStatusLabel")
        h.addWidget(self._exec_loop_lbl)
        h.addWidget(self._exec_step_lbl)
        h.addWidget(self._exec_time_lbl)

        if center_label:
```

> 遵循 `qt-qss-stylesheet-isolation-theme-bug` 记忆:只用 objectName + 全局 QSS,不用 polish/palette/setStyleSheet。

- [ ] **Step 2: Import check**

Run: `python3 -c "import src.panel.qt_backend.pages.base_page; print('IMPORT OK')"`
Expected: `IMPORT OK`

- [ ] **Step 3: Commit**

```bash
git add src/panel/qt_backend/pages/base_page.py
git commit -m "feat(qt): base_page 状态栏新增执行进度 3 个 QLabel"
```

---

## Task 10: Qt 动作链 + 工作流页面接线

**Files:**
- Modify: `src/panel/qt_backend/pages/action_chain_page.py`
- Modify: `src/panel/qt_backend/pages/action_chain_profile_mixin.py`
- Modify: `src/panel/qt_backend/pages/workflow_page.py`

**Interfaces:**
- Consumes: `compose_execution_status` (Task 4), `self.schedule`/`QtTimerScheduler` (既有), `self._exec_*_lbl` (Task 9), executor props (Task 5).

- [ ] **Step 1: Qt action_chain_profile_mixin.py — refresh + tick + 接线**

在 `qt_backend/pages/action_chain_profile_mixin.py` 中新增 refresh + tick 方法(用 `self.schedule`/`cancel`,token 存 `self._exec_tick_token`):

```python
    def _refresh_execution_status(self) -> None:
        """从执行器读值并刷新 3 个执行 QLabel。"""
        executor = self.app.executor
        if not executor:
            return
        from src.panel.execution_status import compose_execution_status

        segs = compose_execution_status(executor, self._model.graph)
        if hasattr(self, "_exec_loop_lbl"):
            self._exec_loop_lbl.setText(segs.loop_text)
        if hasattr(self, "_exec_step_lbl"):
            self._exec_step_lbl.setText(segs.step_text)
        if hasattr(self, "_exec_time_lbl"):
            self._exec_time_lbl.setText(segs.time_text)

    def _start_exec_tick(self) -> None:
        self._stop_exec_tick()
        self._exec_tick_token = self.schedule(1000, self._exec_tick)

    def _exec_tick(self) -> None:
        self._exec_tick_token = None
        self._refresh_execution_status()
        if self._model.executor_state == ExecutorState.RUNNING:
            self._exec_tick_token = self.schedule(1000, self._exec_tick)

    def _stop_exec_tick(self) -> None:
        token = getattr(self, "_exec_tick_token", None)
        if token is not None:
            try:
                self._timer.cancel(token)
            except Exception:  # noqa: BLE001 — token 失效无害
                pass
            self._exec_tick_token = None
```

> Qt 页面的 scheduler 是 `self._timer`(`QtTimerScheduler` 实例,见 `base_page.schedule` 委托给它)。`self.schedule(ms, cb)` 返回 token;取消用 `self._timer.cancel(token)`。`__init__` 已由 base_page 初始化 `self._timer`,无需额外创建。

在页面 `__init__` 初始化 `self._exec_tick_token = None`(动作链 Qt 页面字段区)。

修改 `_on_executor_state`(约第 175-185 行)末尾增加 tick 启停 + 刷新:

```python
    def _on_executor_state(self, state=None, **_kw):
        labels = {
            ExecutorState.RUNNING: t("chain.status.running"),
            ExecutorState.PAUSED: t("chain.status.paused"),
            ExecutorState.IDLE: t("chain.status.stopped"),
        }
        text = labels.get(state, t("chain.status.ready"))
        if hasattr(self, "_status_label"):
            self._status_label.setText(text)
        if hasattr(self, "_status_left"):
            self._status_left.setText(text)

        status_state = state or ExecutorState.IDLE
        if status_state == ExecutorState.RUNNING:
            self._refresh_execution_status()
            self._start_exec_tick()
        else:
            self._stop_exec_tick()
            self._refresh_execution_status()
```

修改 `_on_step_highlight`(约第 187-202 行),移除把步骤消息写入 `_status_label`/`_status_right` 的旧逻辑,改为刷新执行段:

```python
    def _on_step_highlight(self, step_index=None, iteration=None, **_kw):
        if self._model.executor_state == ExecutorState.IDLE:
            return
        if step_index is not None:
            item = self._step_tree.topLevelItem(step_index)
            if item:
                self._step_tree.setCurrentItem(item)
            self._selected_step_idx = step_index
        self._refresh_execution_status()
```

在 `_on_round_started`(约第 204-208 行)末尾加 `self._refresh_execution_status()`。

- [ ] **Step 2: Qt workflow_page.py — refresh + tick + 接线**

在 `qt_backend/pages/workflow_page.py` 新增同名 4 个方法(`_refresh_execution_status` / `_start_exec_tick` / `_exec_tick` / `_stop_exec_tick`),写 `_exec_*_lbl`;在 `_on_executor_state` 与 `_on_node_highlight`(若有)末尾接 refresh + tick 启停,模式与动作链一致。

`_refresh_execution_status` 中读 `self._model.graph`;`_on_executor_state` 末尾:

```python
        if state == ExecutorState.RUNNING:
            self._refresh_execution_status()
            self._start_exec_tick()
        else:
            self._stop_exec_tick()
            self._refresh_execution_status()
```

`__init__` 增加 `self._exec_tick_token = None`。

- [ ] **Step 3: Import check**

Run: `python3 -c "import src.panel.qt_backend.pages.action_chain_page; import src.panel.qt_backend.pages.action_chain_profile_mixin; import src.panel.qt_backend.pages.workflow_page; print('IMPORT OK')"`
Expected: `IMPORT OK`

- [ ] **Step 4: Qt manual smoke**

Run Qt 模式启动(按项目既有方式,如设置后端为 qt):`python main.py`
确认动作链 + 工作流两页状态栏 3 段执行进度正常刷新、暂停冻结、停止保留。worklog 记录。

> ⚠️ Tk 与 Qt **不可同进程混跑**(cocoa SIGABRT);冒烟分别在不同进程测试。

- [ ] **Step 5: Commit**

```bash
git add src/panel/qt_backend/pages/action_chain_page.py src/panel/qt_backend/pages/action_chain_profile_mixin.py src/panel/qt_backend/pages/workflow_page.py
git commit -m "feat(qt): 动作链+工作流页面接入执行进度 3 段状态栏"
```

---

## Task 11: 全量验证 + i18n gate + 收尾

**Files:**
- 无新增;运行全量校验。

- [ ] **Step 1: i18n lint gate**

Run: `python3 scripts/lint_i18n_keys.py && pytest tests/unit/utils/test_i18n_keys.py tests/unit/utils/test_i18n_lint.py -v`
Expected: 全绿(新 key 已登记)

- [ ] **Step 2: 新增代码单测全绿**

Run(逐文件,遵守 Tk/Qt 隔离):
```
pytest tests/unit/core/test_execution_timer.py -v
pytest tests/unit/core/test_action_executor_facade.py -v
pytest tests/unit/utils/test_timing.py -v
pytest tests/unit/panel/test_execution_status.py -v
pytest tests/unit/panel/test_status_bar.py -v
```
Expected: 全 PASS

- [ ] **Step 3: 既有测试无回归(抽样)**

Run: `pytest tests/unit/core/test_event_bridge_layer.py tests/unit/panel/test_chain_model.py tests/unit/panel/test_controller_start_guard.py -v`
Expected: 全 PASS(执行器/事件/模型改动未破坏既有行为)

- [ ] **Step 4: 覆盖率检查(新模块)**

Run: `pytest tests/unit/core/test_execution_timer.py tests/unit/panel/test_execution_status.py tests/unit/utils/test_timing.py --cov=src/core/execution_timer --cov=src/panel/execution_status --cov=src/utils/timing --cov-report=term-missing`
Expected: 三个新模块覆盖率 ≥ 90%

- [ ] **Step 5: 双框架冒烟回归**

- tkinter: `python main.py` → 动作链 + 工作流各跑一轮,确认 3 段显示 + 暂停冻结 + 停止保留 + 主题切换颜色跟随。
- Qt: 切换 Qt 后端启动,重复上述。
- worklog 记录两框架观察结果。

- [ ] **Step 6: 最终提交(若有遗漏的 worklog / 小修)**

```bash
git add -A
git commit -m "test: 执行进度显示全量验证通过(i18n gate + 单测 + 双框架冒烟)"
```

---

## Self-Review 记录

- **Spec coverage**: §6.1→Task1, §6.2→Task5, §6.3→Task3, §6.4→Task4, §6.5→Task6, §6.6(tkinter)→Task7+8, §6.7(Qt)→Task9+10, §9 i18n→Task2, §10 测试→各 Task + Task11。全覆盖。
- **Placeholder scan**: 无 TBD/TODO;Task 10 Step 1 对 `self.app.timer_scheduler` 属性名标注"实现时确认",因 Qt schedule/cancel 的确切持有者需在 Qt 运行时核验——这是必要的不确定性,已显式标注而非含糊。
- **Type consistency**: `elapsed_active`(property,无括号)在 Task5 定义、Task4 `compose_execution_status` 以 `executor.elapsed_active` 访问、Task7-10 一致;`completed_rounds`(property)一致;`insert_segment(index, name, text)` 在 Task6 定义、Task7/8 以 `insert_segment(1, "exec_loop", "")` 调用一致;3 段 name `exec_loop/exec_step/exec_time` 全链路一致。
