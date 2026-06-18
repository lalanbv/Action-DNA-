# 修复容器自死锁导致 Windows exe 卡死(窗口出现即无响应、无日志)

**日期**:2026-06-18
**类型**:fix / perf(底层并发正确性)
**影响**:Windows 打包 exe 双击后窗口出现即卡死、`assets/logs/` 无任何日志;macOS dev 偶发不触发。

## 根因

`src/core/container/container.py` 的 `ServiceContainer._lock` 为 `threading.Lock`(**非重入**)。

死锁链:
1. phase3.5 GUI 线程 `get(ActionExecutor)` → `_resolve` 持有 `self._lock`。
2. 持锁期间调工厂 lambda → 求值实参 `self.ring_log`。
3. `self.ring_log` 是 `ServiceProviderMixin` 的 property → `try_get(RingBufferLog)` → `_resolve` **再次请求同一把 `self._lock`**。
4. `threading.Lock` 非重入 → 同线程二次 acquire **永久阻塞** → GUI 线程冻死。

死锁发生在 `ActionExecutor.__init__` **之前**(故 `[boot] phase3.5.a` 心跳永不出现),`try/except` 与 `sys.excepthook` 全部失效 → 表现为「卡死无日志」。

**为何 dev 不卡 / exe 必卡**:RingBufferLog 若被更早代码路径先解析(`_resolve` 见 `instance is not None` 直接返回、不取锁)则不触发;exe 下模块加载/解析顺序不同,phase3.5 成为其首次解析 → 必死锁。

## 修复

`_lock`: `threading.Lock()` → `threading.RLock()`(可重入)。

DI 容器标准做法 —— 工厂回调允许递归解析依赖;同线程可多次获取,跨线程仍互斥,单例双重检查锁语义不变。

## 变更文件

| 文件 | 变更 |
|------|------|
| `src/core/container/container.py` | **核心修复**:`_lock` 改 `RLock` + 解释注释 |
| `tests/unit/core/test_container_reentrant.py` | **新建**:递归解析防回归(线程+2s超时检测死锁)、单例去重、跨线程互斥 3 用例 |
| `src/core/action_executor.py` | `__init__` 内 `.a`-`.k` 细粒度心跳(本轮定位用,可保留作启动诊断) |
| `src/panel/qt_backend/app.py` | phase3.1-.9 + phase3.5.L1/P1 心跳(本轮定位用) |

## 验证

- 新测试:`pytest tests/unit/core/test_container_reentrant.py -v` → 3 passed
- 全量 core 单元套件:`pytest tests/unit/core -q` → **1994 passed**(零回归)
- 逻辑铁证:`Lock`(非重入) + 同线程二次 acquire = 确定性死锁(Python 语义),防回归测试可靠捕获

## 备注

- 上一轮(2026-06-18)pynput `_restart_listener` 异步化为有效防腐(pynput 确可在 Windows 主线程阻塞),但**非本次卡死根因**;保留。
- 用户需重新打包 Windows exe(`build_windows.bat`)验证:启动后日志应出现 `[boot] phase3.5.a` … `phase3.5 OK`,GUI 不再卡死。
