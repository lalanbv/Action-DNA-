# Windows exe 启动卡死修复(pynput 全局热键主线程阻塞)

- **日期**:2026-06-18
- **类型**:fix(启动卡死 / 静默无日志)
- **影响范围**:全局热键后端(PynputBackend)+ 启动诊断(双框架 Qt/tk 共享)

## 背景

Windows 端双击打包 exe,窗口能出现但界面卡死无响应,`assets/logs/` 无任何日志。

## 根因

`PynputBackend._restart_listener()` 在主线程(phase3 QTimer 回调)**同步**调用
`GlobalHotKeys(...).start()`。pynput 的 `Listener.start()` 在主线程同步等待 listener
线程安装 Windows `WH_KEYBOARD_LL` 全局键盘钩子;打包 exe / 特定桌面会话 /
安全软件介入下,`SetWindowsHookEx` 挂起 → `start()` 阻塞主线程 → Qt 事件循环冻结。

关键:这是**阻塞**而非**异常**,故 `sys.excepthook`、`threading.excepthook`、
phase 的 `try/except` **全部失效** → 表现为「窗口出现但卡死,无任何日志」。
这也解释了上次 `aec0b3f`「分阶段 try/except」加固为何未解决 —— `try/except`
抓不住「阻塞」,只拦得住「异常」。

### 排查路径(逐层排除)

1. `main.py` 已有 `excepthook` + `try/except` + `MessageBox`,任何 Python 异常都会落日志/弹窗 → 排除 Python 异常
2. 「窗口出现但卡死 + 无日志」⇒ 主线程被**同步阻塞**(非异常),excepthook/try-except 全抓不住
3. phase2 三服务构造均不阻塞:
   - `ScreenCapture.__init__` 仅设 `threading.local()`(mss 懒加载,首次截图才创建)
   - `InputController.__init__` Windows 下用 ctypes `SendInputBackend`(构造不阻塞)
   - `TemplateMatcher.__init__` 仅 `require_cv2()` + OrderedDict/Lock(不阻塞)
4. 收敛到 phase3 唯一的主线程同步阻塞候选:`HotkeyManager.register_defaults()` → `PynputBackend._restart_listener()` → `GlobalHotKeys.start()`

## 修复

### 1. 核心修复:全局热键 listener 启动异步化(`src/core/input/global_hotkey_backend.py`)

- `_restart_listener()` 改为后台 daemon 线程派发,**主线程立即返回**,绝不等待 `start()`
- 新增 `_do_restart_listener()`:三段持锁,确保阻塞的 `start()` **不持有** `self._lock`,
  不会拖住 `register` / `stop` 等其它获取同一把锁的调用方
- 世代号 `_restart_gen` 去重并发重启,仅最新一次提交生效
- `stop()` 设终态标志 `_stopped=True`,防止在途的后台启动「复活」已停 listener

### 2. 启动诊断心跳日志

- `main.py`:`_setup` / `crash_diagnostics` / `preload` / backend qt·tk / `run` 各步 `[boot]` 心跳
- `src/panel/qt_backend/app.py`:phase1/2/3 各阶段 + HotkeyManager 注册段 `[boot]` 心跳
- `src/panel/app.py`:tkinter 后端对等(phase1/phase3/HotkeyManager)
- `global_hotkey_backend.py`:`_do_restart_listener` 的 `start()` 前后 `[boot]` 心跳(关键验证点)

### 3. 防回归测试(`tests/unit/core/input/test_global_hotkey_backend.py`,新建)

- mock `GlobalHotKeys.start` 为阻塞,断言 `_restart_listener` 不阻塞调用线程
- 断言 listener 仍被后台真正创建(防止退化成「丢弃启动」)

## 影响文件

| 文件 | 改动 |
|------|------|
| `src/core/input/global_hotkey_backend.py` | 核心修复:listener 启动异步化 + 诊断心跳 |
| `main.py` | 启动心跳日志(各 boot 步骤) |
| `src/panel/qt_backend/app.py` | Qt phase 心跳日志 |
| `src/panel/app.py` | tkinter phase 心跳日志(双框架对等) |
| `tests/unit/core/input/test_global_hotkey_backend.py` | 新建:异步化防回归测试 |

## 验证

- RED→GREEN:同步实现测试失败(2.12s)→ 异步化通过(0.07s)
- `pytest tests/unit/core/` → **1990 passed**(含 input/pynput,无回归)
- `pytest tests/unit/panel/test_app_close_robustness.py` → 5 passed
- 导入/语法正常;mypy 无新增 error(3 个为预存的 `_listener: object` 技术债,非本次引入)
- **待 Windows 端重新打包运行验证**(日志现记录完整 `[boot]` 心跳链)

## 风险与回退

- **向后兼容**:热键回调本就异步触发(用户按键时才回调),listener 延迟数十 ms 就绪对功能无感知影响;注册/注销/batch 语义不变
- **若根因判断偏差**:诊断心跳日志会暴露真实卡死层(日志最后一行即定位),诊断工作不白费
- **回退**:恢复 `_restart_listener` 同步实现 + 移除心跳日志即可(改动均为增量)
