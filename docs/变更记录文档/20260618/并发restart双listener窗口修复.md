# 并发 restart 双 listener 窗口修复

- **日期**:2026-06-18(继 `baddc87` 异步化修复后的 code-review 后续)
- **类型**:fix(并发竞态 / 热键双触发)
- **影响范围**:`PynputBackend._do_restart_listener`(Qt/tk 双框架共享)

## 背景

`baddc87` 把 `_restart_listener` 异步化(每请求一线程)解决了主线程阻塞卡死。
但 `/code-review` 发现该模型的一个并发竞态:多个 `_do_restart_listener` 线程
**并发**执行 `start()`,各自创建 pynput listener,在旧线程步骤3 stop 前形成
**双 listener 窗口** —— 两个 `WH_KEYBOARD_LL` 全局钩子短暂共存,重叠的热键
会被两个 listener 各触发一次(回调双执行)。

## 根因

`_do_restart_listener` 三段持锁(stop-old → 锁外 start → commit),`start()` 在
`self._lock` 之外。两个线程可同时处于步骤2(各自 `GlobalHotKeys(...).start()`),
各自安装全局钩子。世代号 `_restart_gen` 只保证「最终仅最新提交」,无法阻止
「旧线程已 start、未到步骤3 stop」与「新线程已 start」重叠的窗口。

## 修复

新增专用执行锁 `_exec_lock`,**把整个 `_do_restart_listener` 流程串行化**:
同时只有一个线程在 stop-old / start / commit,从根上消除双 listener 窗口。

- `_exec_lock` 只在后台 `_do_restart_listener` 线程获取
- 主线程的 `_restart_listener` / `register` / `stop` 都**不碰** `_exec_lock`
  → 不引入主线程阻塞(即便某次 `start()` 挂起,后续 restart 仅在后台排队,
    UI 事件循环不受影响)
- `start()` 仍在 `self._lock` 之外(避免持 state 锁阻塞 start)
- 锁序:`_exec_lock` 外、`self._lock` 内;其余路径仅 `self._lock` → 无死锁

## 测试

`tests/unit/core/input/test_global_hotkey_backend.py` 新增:
- `fake_pynput_tracked` fixture:追踪同时存活的 listener 数(峰值 `max_active`)
- `test_no_concurrent_active_listeners_on_rapid_restart`:快速连续两次 `register`
  触发并发 restart,断言 `max_active <= 1`

RED→GREEN:
- RED(每请求一线程模型):`max_active=2`(双 listener,日志显示两个"即将启动"并发)
- GREEN(`_exec_lock` 串行化):`max_active=1`(listener 串行启动)

## 影响文件

| 文件 | 改动 |
|------|------|
| `src/core/input/global_hotkey_backend.py` | 新增 `_exec_lock`;`_do_restart_listener` 用其包裹全流程 |
| `tests/unit/core/input/test_global_hotkey_backend.py` | 新增 `fake_pynput_tracked` + 并发测试 |

## 验证

- RED→GREEN:并发测试同步模型失败(`max_active=2`)→ 串行化通过(`max_active=1`)
- `pytest tests/unit/core/` → **1991 passed**(原 1990 + 新并发测试,无回归)
- mypy 无新增 error(3 个为预存 `_listener: object` / `create_backend` 技术债)

## 风险与回退

- **向后兼容**:热键功能完全不变;串行化仅影响后台 restart 调度顺序
- **回退**:移除 `_exec_lock` 字段 + 去掉 `with self._exec_lock:` 即可
