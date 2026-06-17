# 执行进度显示设计 — 循环次数 / 当前步骤 / 执行时间

- **日期**: 2026-06-17
- **状态**: 已批准(待实现)
- **作者**: brainstorming session
- **影响范围**: 核心执行器 + 工具层 + 显示层(tkinter + Qt 双框架,动作链 + 工作流共 4 个界面)

---

## 1. 背景与问题

当前软件在循环执行动作链 / 工作流时,用户无法得知:
- 已经跑了多少回合(循环进度)
- 当前执行到第几步(步骤进度)
- 一共执行了多久(耗时)

现有显示不完整:
- **动作链**(tkinter + Qt): 仅显示 `运行中: 步骤 {step}/{total}`,**无循环次数、无执行时间**,且既有代码 `step_index + 1` 存在 off-by-one 隐患。
- **工作流**(tkinter + Qt): 状态栏只显示节点/边数与缩放,**执行时完全无进度信息**。
- 执行器**无任何计时能力**(无启动时间戳)。

## 2. 目标

在动作链 + 工作流的 4 个界面(tkinter × 2 + Qt × 2)底部状态栏,以**3 个独立分段**实时显示:

```
循环次数: x/y      当前步骤: x/y      执行时间: xx天xx小时xx分xx秒
```

- **精准**: 循环次数使用独立精确计数器;步骤基准以 TDD 锁定,杜绝 off-by-one。
- **可靠**: 暂停冻结、停止保留最终值、双框架行为一致。
- **最优**: 总步数用可达启用 ACTION 节点数(给定 DAG 约束下的最优静态上界)。

## 3. 非目标(Out of Scope)

- 不改变执行引擎的遍历 / 分支语义。
- 不为 DAG 预测运行时实际路径长度(不可消除的限制)。
- 不新增"预计剩余时间 / ETA"(无可靠分母)。
- 不改变现有日志、事件总线结构(仅新增只读属性与少量事件回调接线)。

---

## 4. 设计决策(已与用户确认)

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 显示位置 | 状态栏**独立分段**(3 段) | 复用 StatusBar 分段机制,窗口窄时自动换行,4 界面统一 |
| 时间格式 | **智能省略前导零**,固定最多 2 个有效单位 | `45秒` / `2分14秒` / `1小时5分` / `1天3小时`,避免一堆 0 |
| 暂停计时 | **暂停时冻结**(排除暂停时长) | 准确反映"真正在跑的时间" |
| 循环次数 x | **已完成回合**(独立精确计数器) | 自然跑完时不差一 |
| 总步数 y | 从 START 可达且启用且有 action 的 ACTION 节点数 | 给定 DAG 约束下最优静态上界 |

## 5. 架构

```text
ActionExecutor(后台线程)
  ├─ ExecutionTimer          [新增] 启动/暂停/恢复/停止 + elapsed_active()
  ├─ _completed_rounds       [新增] 已完成回合精确计数
  ├─ current_step_index      [已有] 当前步骤(引擎发布)
  └─ graph.loop_count        [已有] 总循环数(0=∞)
         │
         ▼  (UI 主线程: 事件触发 + 每秒轮询)
build_execution_segments()   [新增] 纯函数: 原始值 → 3 段文本
         │
         ▼
StatusBar 3 个独立分段        循环次数 | 当前步骤 | 执行时间
(tkinter StatusBar.set_segment / Qt QLabel, 4 界面统一)
```

**计时放在执行器层(而非 UI 层)**: 计时是执行语义的一部分,应由执行器作为单一可信源统一管理;UI 仅"每秒读一次 + 渲染"。避免 4 界面 × 2 框架重复实现暂停冻结逻辑。

---

## 6. 组件规格

### 6.1 `ExecutionTimer`(新增)

**文件**: `src/core/execution_timer.py`(约 60 行)

线程安全的活跃执行计时器,排除暂停时长。使用 `time.monotonic()`(不受系统时钟调整影响)。

```python
class ExecutionTimer:
    """活跃执行计时器 — 排除暂停时长。线程安全。

    生命周期: start → (pause/resume)* → stop。
    stop 后 elapsed() 返回冻结的最终值, 直至下次 start 重置。
    """
    def __init__(self) -> None: ...
    def start(self) -> None: ...     # 记录 _start=monotonic(), 清零累计, 清 _final
    def pause(self) -> None: ...     # 仅当运行中且未暂停: _pause_at=monotonic()
    def resume(self) -> None: ...    # _paused_total += now - _pause_at; 清 _pause_at
    def stop(self) -> None: ...      # _final = _elapsed_locked()(幂等)
    def reset(self) -> None: ...     # 全部归零(供 start 调用)
    def elapsed(self) -> float | None: ...  # 未启动返回 None
    def _elapsed_locked(self) -> float | None: ...
```

**elapsed 公式**:
```
active = now - _start - _paused_total - (now - _pause_at if 暂停中 else 0)
return max(0.0, active)
```

**不变量**:
- `stop()` 幂等:重复调用不改变 `_final`。
- `pause()` 在未启动 / 已暂停时为空操作(不抛异常)。
- `resume()` 在未暂停时为空操作。
- `_final` 非 None 时,`elapsed()` 恒返回 `_final`(冻结)。

> **为何独立成类**: 单一职责、可独立单元测试、避免 `action_executor.py`(已 600+ 行)继续膨胀。符合项目"小文件、高内聚、不可变友好"风格。

### 6.2 `ActionExecutor` 改动

**文件**: `src/core/action_executor.py`

1. `__init__` 增加 `self._timer = ExecutionTimer()` 与 `self._completed_rounds = 0`。
2. 生命周期接线:
   - `start()`: `_completed_rounds = 0`;`self._timer.start()`
   - `pause()`: `self._timer.pause()`
   - `resume()`: `self._timer.resume()`
   - `stop()`: `self._timer.stop()`
   - `_run_with_engine` 的 `finally`: `self._timer.stop()`(自然跑完也冻结最终值)
3. `_run_with_engine` 每回合成功后递增:
   ```python
   self._graph_engine.run(graph, ctx)
   with self._lock:
       self._consecutive_failures = 0
       self._completed_rounds += 1   # 仅完整跑完一回合才计入
   iteration += 1
   ```
4. 新增只读属性:
   - `elapsed_active(self) -> float | None` — 委托 `self._timer.elapsed()`
   - `completed_rounds(self) -> int` — `with self._lock: return self._completed_rounds`

**精确性保证**: `_completed_rounds` 仅在 `graph_engine.run()` 正常返回(到达 END)后递增;异常 / 手动停止的回合不计入。自然跑完 N 圈后值为 N(用既有 `_loop_iteration` 会错显 N-1)。

### 6.3 `format_duration_human`(新增)

**文件**: `src/utils/timing.py` 增加函数

```python
def format_duration_human(seconds: float) -> str:
    """把秒数格式化为人类可读时长, 智能省略前导零, 固定最多 2 个有效单位。

    < 60s  → "45秒"
    < 1h   → "2分14秒"
    < 1d   → "1小时5分"
    >= 1d  → "1天3小时"
    """
```

边界:`seconds < 0` → 按 0 处理(显示 `0秒`);非数 / None 由调用方保证不传入。

### 6.4 `build_execution_segments`(新增纯函数)

**文件**: `src/panel/execution_status.py`(约 50 行)

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class ExecutionSegments:
    loop_text: str   # "循环次数: 3/∞" | "循环次数: 3/10" | "循环次数: 0/∞"
    step_text: str   # "当前步骤: 5/12" | "当前步骤: —/12"(未运行)
    time_text: str   # "执行时间: 2分14秒" | "执行时间: —"

def build_execution_segments(
    *,
    completed_rounds: int,
    loop_count: int,            # 0 = 无限
    is_loop: bool,              # graph.loop
    step_index: int,            # 引擎发布的 current_step_index(< 0 = 未运行)
    total_steps: int,           # 可达启用 ACTION 节点数
    elapsed_seconds: float | None,
) -> ExecutionSegments: ...
```

**规则**:
- 循环次数: `is_loop` 为假 → 分母为 `1`(单次);`loop_count == 0` → 分母 `∞`;否则分母 `loop_count`。分子恒为 `completed_rounds`。
- 当前步骤: `step_index < 0` → `—/total`;否则 **`step_index` 直接作为分子(已是 1 基,不要再 +1)** / `total`。
  > 基准已核实:`test_event_bridge_layer.py:82-87` 证实首个 ACTION 的 `ctx.step_index=1`,`test_action_executor_facade.py:146` 证实初始为 0 → 首个动作 = 1。既有 UI 的 `step_index + 1` 是 off-by-one bug,本次一并修正。
- 执行时间: `elapsed_seconds is None` → `—`;否则 `format_duration_human(elapsed_seconds)`。
- 文本走 i18n(`exec.status.loop` / `exec.status.step` / `exec.status.time`),占位符避免 `key`/`count` 裸名(用 `current`/`total`/`duration`)。

> 4 个界面共用此纯函数,保证格式完全一致,且可脱离 GUI 单元测试。

### 6.5 StatusBar 增强(tkinter)

**文件**: `src/panel/components/status_bar.py`

新增 `insert_segment(self, after: str, name: str, text: str = "") -> tk.Label`:在指定 `after` 段(如 `"dot"`)之后插入新段,控制显示顺序(让 3 个执行段排在圆点之后、其它信息之前,更醒目)。复用既有 `_segments` 列表与 `_perform_reflow` 换行逻辑。

> Qt 侧无对应抽象,直接在 `_build_qt_status_bar` 用 `QLabel` + `insertWidget` 实现等价顺序。

### 6.6 显示层 — tkinter(2 页面)

**动作链** `src/panel/pages/action_chain_page.py` + `action_chain_profile_mixin.py`:
- `build()`: `self.status_bar.insert_segment("dot", "exec_loop")` / `"exec_step"` / `"exec_time"`。
- 新增 `_refresh_execution_status()`: 读 `executor.completed_rounds / current_step_index / elapsed_active()` + `model.graph`,调 `build_execution_segments`,写 3 段。
- 新增每秒轮询 `_exec_tick()`(用 `frame.after(1000, ...)` / `after_cancel`):仅 `RUNNING` 时持续;刷新后若仍 RUNNING 则重新 schedule。
- 接线:`_on_step_highlight` / `_on_round_started` / `_on_executor_state` 调 `_refresh_execution_status()`;`_on_executor_state` 在 RUNNING 时启动 tick、IDLE 时停止 tick 并做最后一次刷新(显示冻结最终值)。
- 移除既有 `_on_step_highlight` 中把步骤消息写入 `var_status`/`set_left` 的逻辑(避免与执行段重复);工具栏 `var_status` 仅保留状态/区域文字。

**工作流** `src/panel/pages/workflow_page.py`:
- `_build_status_bar()`: 插入 3 段(在圆点后)。
- 同样新增 `_refresh_execution_status()` + `_exec_tick()`。
- 接线:`_on_node_highlight` / `_on_executor_state` 调刷新;`_update_status_bar()` 保留既有节点/边 + 缩放信息(left/right),执行段独立。

**总步数计算**:
```python
def _count_reachable_action_nodes(graph) -> int:
    return sum(
        1 for n in graph.ordered_nodes()
        if n.node_type == NodeType.ACTION and n.enabled and n.action is not None
    )
```

### 6.7 显示层 — Qt(2 页面)

**`src/panel/qt_backend/pages/base_page.py`**: `_build_qt_status_bar` 增加 3 个 `QLabel`(`objectName="dnaStatusLabel"` 走全局 QSS),`insertWidget` 置于 `_status_left` 之后。

**动作链** `qt_backend/pages/action_chain_page.py` + `action_chain_profile_mixin.py`:
- 新增 `_refresh_execution_status()`(写 3 个 QLabel)、`_exec_tick`(用 `self.schedule(1000, ...)` + `QtTimerScheduler.cancel(token)`)。
- 接线同 tkinter。

**工作流** `qt_backend/pages/workflow_page.py`: 同上;`_update_status_bar()` 保留节点/边 + 缩放。

> 主题刷新(`apply_theme`):新增 QLabel 已设 `objectName="dnaStatusLabel"`,随全局 QSS 自动刷新,无需额外处理(遵循 `qt-qss-stylesheet-isolation-theme-bug` 记忆:新页面容器样式一律走全局 QSS)。

---

## 7. 事件与刷新触发点

执行段需在以下时机刷新(全部汇聚到 `_refresh_execution_status()`):

| 触发 | 事件 / 回调 | 更新内容 |
|------|-------------|----------|
| 步骤切换 | `EXECUTOR_STEP_CHANGED` → `UI_STEP_HIGHLIGHT` / `UI_NODE_HIGHLIGHT` | 步骤段 |
| 新回合开始 | `EXECUTOR_ROUND_STARTED` → `UI_ROUND_STARTED` | 步骤段重置 |
| 状态变化 | `EXECUTOR_STATE_CHANGED` | 启停 tick + 全段刷新 |
| 暂停 / 恢复 | `EXECUTOR_PAUSED` / `EXECUTOR_RESUMED` | 时间冻结 / 解冻 |
| 每秒 | UI 轮询 tick(仅 RUNNING) | 时间段(以及循环段,因 completed_rounds 会变) |

**tick 生命周期**:
- RUNNING → 启动 tick(`after(1000)` / `schedule(1000)`)
- 每次 tick: `_refresh_execution_status()` → 若仍 RUNNING,重新 schedule 下一次
- IDLE / PAUSED → 停止 tick(PAUSED 时时间已冻结,无需 tick;但状态切换瞬间刷新一次以显示冻结值)

**线程安全**: 所有 UI 刷新在主线程执行。执行器事件经 `_schedule_main` / Qt 信号已桥接到主线程;tick 本身就在主线程。读 `executor` 属性均有内部锁保护。

---

## 8. 精确语义约定(实现须严格遵守)

1. **循环次数 x = `completed_rounds`**(已完成回合):
   - 首回合运行中显示 `0/∞`(或 `0/N`);首回合完成后 `1/∞`。
   - 自然跑完 N 圈 → `N/N`(精确);手动停止 → 已完整跑完的回合数。
2. **无限循环分母 = `∞`**(`loop_count == 0`)。`is_loop == False`(单次)分母 = `1`。
3. **当前步骤 x = `current_step_index` 直接取值(已是 1 基,不要再 +1)**:
   - 已核实:首个 ACTION 的 `current_step_index = 1`(见 §6.4 证据)。
   - 测试用例(回归守卫):3 步动作链,断言显示依次为 `1/3 → 2/3 → 3/3`。
   - `current_step_index < 0` → 显示 `—/total`。
4. **总步数 y = 可达启用 ACTION 节点数**:
   - 动作链(线性)= 精确值。
   - 工作流(DAG)= 最优静态上界;分支场景下 x 可能不达 y(只走一条分支),属不可消除限制。
5. **执行时间 = 活跃时长(排除暂停)**;`elapsed_active() is None` → 显示 `—`。
6. **停止后**: 执行时间冻结最终值,循环 / 步骤保留上次值;**下次 `start()` 才重置**。
7. **DAG 末尾**: 工作流一轮结束 `current_step_index` 会被引擎置 -1,步骤段显示 `—/total`(正常)。

---

## 9. i18n 键(新增)

`src/utils/translations/zh.json` + `en.json` 新增(占位符避开 `key`/`count` 裸名陷阱,遵循 `i18n-t-placeholder-trap` 记忆):

| key | zh | en |
|-----|----|----|
| `exec.status.loop` | `循环次数: {current}/{total}` | `Loops: {current}/{total}` |
| `exec.status.step` | `当前步骤: {current}/{total}` | `Step: {current}/{total}` |
| `exec.status.time` | `执行时间: {duration}` | `Time: {duration}` |
| `exec.status.infinite` | `∞` | `∞` |
| `exec.status.dash` | `—` | `—` |
| `duration.seconds` | `{s}秒` | `{s}s` |
| `duration.minutes_seconds` | `{m}分{s}秒` | `{m}m {s}s` |
| `duration.hours_minutes` | `{h}小时{m}分` | `{h}h {m}m` |
| `duration.days_hours` | `{d}天{h}小时` | `{d}d {h}h` |

> 新增 key 须经 `scripts/lint_i18n_keys.py` gate 校验(遵循 `i18n-framework-enhancement` 记忆)。

---

## 10. 测试策略(遵循 TDD + 80%+ 覆盖)

| 层级 | 测试文件 | 关键用例 |
|------|----------|----------|
| `ExecutionTimer` | `tests/unit/core/test_execution_timer.py` | start/pause/resume/elapsed;暂停冻结(模拟 sleep);stop 幂等;未启动返回 None;`reset` 清零 |
| `format_duration_human` | `tests/unit/utils/test_timing.py`(扩展) | 45s/134s/3900s/97200s 边界;负数归 0 |
| `build_execution_segments` | `tests/unit/panel/test_execution_status.py` | 无限 vs 有限;单次(loop=False);step<0 → `—`;elapsed=None → `—`;completed_rounds 精确 |
| 步骤基准锁定 | `tests/unit/panel/test_execution_status.py` | 3 步链 → `1/3, 2/3, 3/3`(回归守卫,防 off-by-one 复发)|
| `ActionExecutor` 计数 | `tests/unit/core/test_action_executor.py`(扩展) | `_completed_rounds` 在每回合后递增;手动停止不误计;`elapsed_active` 接线 |
| StatusBar insert | `tests/unit/panel/test_status_bar.py`(扩展) | `insert_segment` 顺序正确;reflow 不崩 |
| i18n gate | 既有 `lint_i18n_keys.py` | 新 key 已登记,占位符合规 |

**GUI 接线**(4 页面的 tick / 刷新)优先以纯逻辑测试覆盖;GUI 渲染本身不在单元测试范围(遵循既有 `env-quirks-vision-qt` 记忆:Tk/Qt 测试逐文件跑)。

---

## 11. 文件变更清单

### 新增
- `src/core/execution_timer.py` — ExecutionTimer
- `src/panel/execution_status.py` — build_execution_segments + ExecutionSegments
- `tests/unit/core/test_execution_timer.py`
- `tests/unit/panel/test_execution_status.py`

### 修改 — 核心
- `src/core/action_executor.py` — 持有 timer + completed_rounds,生命周期接线,新增属性

### 修改 — 工具
- `src/utils/timing.py` — format_duration_human
- `src/utils/translations/zh.json` / `en.json` — 新 i18n 键

### 修改 — tkinter 显示
- `src/panel/components/status_bar.py` — insert_segment
- `src/panel/pages/action_chain_page.py` — 插段 + tick
- `src/panel/pages/action_chain_profile_mixin.py` — 接线
- `src/panel/pages/workflow_page.py` — 插段 + tick + 接线

### 修改 — Qt 显示
- `src/panel/qt_backend/pages/base_page.py` — _build_qt_status_bar 加 3 QLabel
- `src/panel/qt_backend/pages/action_chain_page.py` — tick + 接线
- `src/panel/qt_backend/pages/action_chain_profile_mixin.py` — 接线
- `src/panel/qt_backend/pages/workflow_page.py` — tick + 接线

### 测试扩展
- `tests/unit/utils/test_timing.py`
- `tests/unit/core/test_action_executor.py`
- `tests/unit/panel/test_status_bar.py`

---

## 12. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 步骤 off-by-one(既有隐患) | TDD 用 3 步链测试钉死基准 |
| DAG 总步数近似误导用户 | 文档 + 设计注明"最优静态上界";动作链精确 |
| tick 未清理导致页面销毁后回调泄漏 | IDLE 时 cancel;页面 `destroy()` 显式 cancel tick token(参考既有订阅清理模式) |
| Qt 主题不跟随 | QLabel 用 `objectName` 走全局 QSS,不动 polish/palette(遵循 `qt-qss-stylesheet-isolation-theme-bug`) |
| `time.monotonic` 不可用(打包/特殊环境) | 标准库稳定可用;ExecutionTimer 单测覆盖 |
| 暂停后 resume 漏算 | resume 测试断言 `_paused_total` 累加正确 |

---

## 13. 验收标准

- [ ] 动作链(tkinter + Qt)运行时状态栏显示 循环次数 / 当前步骤 / 执行时间 三段,实时刷新
- [ ] 工作流(tkinter + Qt)同上
- [ ] 循环次数:已完成回合,无限显示 `∞`,有限收尾精确(如 `5/5`)
- [ ] 当前步骤:3 步链依次显示 `1/3, 2/3, 3/3`(无 off-by-one)
- [ ] 执行时间:智能省略前导零;暂停时冻结;停止后保留最终值
- [ ] 单元测试全部通过,新代码覆盖率 ≥ 80%
- [ ] i18n lint gate 通过,zh/en 键齐全
- [ ] 双框架主题切换正常,3 段颜色跟随
