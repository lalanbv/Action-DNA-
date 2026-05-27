# Action\<DNA\> — 自动化工作流引擎

## 项目简介

通过浏览器运行云游戏，本项目在浏览器层进行屏幕截图 + 模板匹配 + OCR + 像素搜索 + 模拟鼠标键盘。ACE 检测不到浏览器层的操作。

## 技术栈

- **Python 3.11+**
- **mss** — 高速屏幕截图
- **OpenCV** — 图像模板匹配
- **rapidocr_onnxruntime** — OCR 文字识别（可选依赖，优雅降级）
- **pyautogui** — 鼠标/键盘模拟（带随机化防检测）
- **tkinter** — 控制面板 GUI（内置，暗色/亮色主题 + i18n 中英文）
- **pytest** — 测试框架（84 个测试文件，99% 覆盖率）

## 项目结构

```
├── main.py                              # 入口，启动 PanelApp
├── pyproject.toml                       # 项目配置 + pytest/mypy 设置
├── requirements.txt                     # 依赖清单
├── profiles/                            # 用户配置（运行时生成）
│   └── <配置名>/
│       ├── profile.json                 # 动作链/工作流配置
│       └── images/                      # 配置引用的模板图片副本
├── config/settings.json                 # 全局配置
├── assets/
│   ├── templates/                       # 通用模板图片
│   └── logs/                            # 运行日志
├── src/
│   ├── core/
│   │   ├── config.py                    # 配置管理
│   │   ├── logger.py                    # 日志
│   │   ├── condition.py                 # 条件表达式求值
│   │   ├── easing.py                    # 缓动函数（鼠标移动轨迹）
│   │   ├── serialization.py             # 序列化工具
│   │   ├── step_types.py                # 步骤类型枚举
│   │   ├── action.py                    # v1 动作链数据模型
│   │   ├── action_executor.py           # 执行器 Facade（v1/v2 统一入口）
│   │   ├── flow.py                      # FlowGraph DAG 数据模型 + chain_to_flow
│   │   ├── monitor.py                   # 屏幕状态监控
│   │   ├── buffer_pool.py               # 截图缓冲池
│   │   ├── screen_guard.py              # 屏保/锁屏检测
│   │   ├── fail_safe.py                 # 安全停止机制
│   │   ├── input_controller.py          # 鼠标/键盘模拟（随机化）
│   │   ├── engine/                      # v2 DAG 执行引擎
│   │   │   ├── graph_engine.py          # DAG 执行引擎
│   │   │   ├── fsm_engine.py            # FSM 有限状态机引擎（opt-in）
│   │   │   ├── execution_context.py     # 不可变执行上下文
│   │   │   ├── node_descriptor.py       # 描述符基类 + 端口定义
│   │   │   ├── node_registry.py         # 描述符注册表（@auto_register）
│   │   │   ├── node_result.py           # 节点执行结果
│   │   │   ├── execution_blocker.py     # Layer 阻塞信号
│   │   │   ├── workflow_validator.py    # 三阶段 FlowGraph 验证
│   │   │   └── descriptors/             # 各动作类型描述符
│   │   │       ├── click_image_descriptor.py    # 模板匹配点击
│   │   │       ├── click_pos_descriptor.py      # 固定坐标点击
│   │   │       ├── press_key_descriptor.py      # 按键模拟
│   │   │       ├── wait_descriptor.py           # 固定/随机等待
│   │   │       ├── condition_descriptor.py      # 条件分支
│   │   │       ├── ocr_descriptor.py            # OCR 文字识别
│   │   │       ├── pixel_search_descriptor.py   # 像素颜色搜索
│   │   │       ├── record_descriptor.py         # 录制回放
│   │   │       ├── flow_descriptors.py          # Start/End/Loop 流程控制
│   │   │       └── extended_descriptors.py      # HoldKey/Scroll/Drag 等
│   │   ├── layers/                      # Layer 中间件管道
│   │   │   ├── layer.py                 # Layer 抽象基类
│   │   │   ├── event_bridge_layer.py    # 事件总线桥接
│   │   │   ├── pause_layer.py           # 暂停/恢复
│   │   │   ├── retry_layer.py           # 自动重试
│   │   │   ├── timing_layer.py          # 耗时统计
│   │   │   ├── logging_layer.py         # 执行日志
│   │   │   ├── breakpoint_layer.py      # 断点调试
│   │   │   └── debug_screenshot_layer.py # 调试截图
│   │   ├── variables/                   # 类型化变量池
│   │   │   ├── pool.py                  # VariablePool（线程安全）
│   │   │   ├── types.py                 # 变量类型枚举
│   │   │   ├── scope.py                 # 作用域管理
│   │   │   ├── typed_variable.py        # 类型化变量
│   │   │   └── builtins.py              # 内置系统变量
│   │   ├── events/                      # 事件总线
│   │   │   ├── bus.py                   # EventBus 发布/订阅
│   │   │   └── events.py               # 事件类型定义
│   │   ├── error/                       # 错误策略
│   │   │   ├── error_config.py          # 错误策略配置
│   │   │   └── exceptions.py            # 自定义异常
│   │   ├── vision/                      # 视觉检测
│   │   │   ├── vision_pipeline.py       # 截图 + 模板匹配管道
│   │   │   ├── ocr_recognizer.py        # OCR 文字识别器
│   │   │   ├── ocr_result.py            # OCR 结果类型
│   │   │   ├── pixel_searcher.py        # HSV 像素搜索器
│   │   │   ├── pixel_result.py          # 像素搜索结果
│   │   │   └── _cv2_guard.py            # OpenCV 可用性守卫
│   │   ├── input/                       # 全局热键
│   │   │   ├── hotkey_manager.py        # 热键管理器
│   │   │   └── global_hotkey_backend.py # 全局热键后端
│   │   ├── io/                          # 导入导出
│   │   │   ├── importer.py              # 配置导入
│   │   │   └── script_exporter.py       # 脚本导出
│   │   ├── debug/                       # 调试工具
│   │   │   ├── debugger.py              # 调试器核心
│   │   │   ├── breakpoint_manager.py    # 断点管理
│   │   │   └── ring_buffer_log.py       # 环形缓冲日志
│   │   ├── editor/                      # 编辑器撤销/重做
│   │   │   ├── undo_manager.py          # 撤销管理器
│   │   │   └── commands/                # 命令模式（8 个命令）
│   │   ├── plugins/                     # 插件系统核心
│   │   │   ├── plugin_interface.py      # 插件接口基类
│   │   │   ├── plugin_loader.py         # 插件加载器
│   │   │   ├── plugin_context.py        # 插件上下文
│   │   │   ├── plugin_node_registry.py  # 插件节点注册
│   │   │   └── dialog_registry.py       # 插件对话框注册
│   │   ├── exporter.py                  # FlowGraph JSON 序列化
│   │   └── importer.py                  # FlowGraph JSON 反序列化
│   ├── panel/                           # tkinter GUI 层
│   │   ├── app.py                       # 主窗口 + 页面路由 + 服务容器
│   │   ├── profile_manager.py           # 配置文件保存/加载/图片管理
│   │   ├── region_picker.py             # 区域框选器
│   │   ├── widgets.py                   # 通用 UI 组件工厂
│   │   ├── canvas/                      # 流程图画布（14 个模块）
│   │   │   ├── graph_canvas.py          # 主画布
│   │   │   ├── node_renderer.py         # 节点渲染
│   │   │   ├── edge_renderer.py         # 边渲染
│   │   │   ├── edge_animator.py         # 边动画（流动/闪烁）
│   │   │   ├── grid_renderer.py         # 网格背景
│   │   │   ├── interaction_handler.py   # 拖拽/选择交互
│   │   │   ├── viewport.py              # 视口管理
│   │   │   ├── zoom_controller.py       # 缩放控制
│   │   │   ├── minimap.py               # 小地图
│   │   │   ├── minimap_settings.py      # 小地图设置
│   │   │   ├── floating_controls.py     # 浮动控制面板
│   │   │   ├── search_dialog.py         # 节点搜索
│   │   │   ├── scale.py                 # 断点/缩放常量
│   │   │   └── theme.py                 # 暗/亮主题管理
│   │   ├── components/                  # 可复用 UI 组件（17 个）
│   │   ├── controllers/                 # 页面控制器
│   │   │   ├── action_chain_controller.py  # 动作链控制器
│   │   │   └── workflow_controller.py      # 工作流控制器
│   │   ├── dialogs/                     # 步骤编辑对话框（17 个）
│   │   ├── models/
│   │   │   └── chain_model.py           # 动作链数据模型
│   │   └── pages/                       # 7 个功能页 + 3 个 mixin
│   │       ├── base_page.py             # 页面基类
│   │       ├── home_page.py             # 主页（功能卡片选择）
│   │       ├── action_chain_page.py     # 动作链自动化
│   │       ├── workflow_page.py         # 工作流编辑器
│   │       ├── plugin_page.py           # 插件管理
│   │       ├── record_page.py           # 宏录制
│   │       ├── notification_page.py     # 通知设置
│   │       ├── schedule_page.py         # 定时调度
│   │       ├── settings_page.py         # 全局设置
│   │       ├── workflow_actions_mixin.py
│   │       ├── workflow_palette_mixin.py
│   │       └── workflow_properties_mixin.py
│   ├── plugins/                         # 内置插件（3 个）
│   │   └── builtin/
│   │       ├── combat/                  # 战斗辅助（5 个描述符）
│   │       ├── navigation/              # 地图导航（5 个描述符）
│   │       └── task/                    # 任务自动化（4 个描述符）
│   ├── notification/                    # 通知系统
│   │   ├── notifier.py                  # 通知管理器
│   │   ├── rule_manager.py             # 规则管理
│   │   ├── triggers.py                 # 触发器定义
│   │   └── channels/                   # 通知渠道
│   │       ├── system_notify.py        # 系统通知
│   │       ├── sound_notify.py         # 声音提醒
│   │       └── webhook_notify.py       # Webhook 推送
│   ├── recorder/                        # 宏录制
│   │   ├── recorder.py                  # 录制器
│   │   └── event_merger.py             # 事件合并
│   ├── schedule/                        # 定时调度
│   │   └── scheduler.py                # 调度器
│   ├── game/                            # 游戏特定逻辑
│   │   ├── game_state.py               # 游戏状态
│   │   ├── combat.py                   # 战斗逻辑
│   │   ├── navigation.py              # 导航逻辑
│   │   └── task.py                     # 任务逻辑
│   └── utils/                           # 工具模块
│       ├── i18n.py                      # 国际化（中/英）
│       ├── paths.py                     # 路径工具
│       ├── timing.py                    # 时间工具
│       ├── step_ring.py                 # 环形缓冲区
│       └── translations/               # 翻译文件
│           ├── zh.json                  # 中文
│           └── en.json                  # 英文
├── DNA_Design_Scheme/                   # v2.0 设计文档（14 份）
├── docs/
│   ├── plugin_guide.md                  # 插件开发指南
│   ├── plugin_api.md                    # 插件 API 参考
│   └── plugin_examples/                 # 插件示例
├── worklog/                             # 工作日志
├── benchmarks/                          # 性能基准测试
│   └── bench_engine.py
└── tests/                               # 测试（84 个文件）
    ├── unit/core/                       # 单元测试
    ├── integration/                     # 集成测试
    ├── regression/                      # 回归测试
    └── e2e/                             # 端到端测试
```

## 使用方式

```bash
python3 -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows
pip install -r requirements.txt
python main.py
```

1. 主页选择功能卡片 → 进入对应页面
2. 可选：框选浏览器云游戏窗口区域
3. 添加动作步骤或编辑工作流 DAG
4. 保存配置 → 下次可直接加载
5. 点击「启动」循环执行

## 页面导航架构

```text
PanelApp (app.py)
  ├── 共享服务: VisionPipeline, InputController, ActionExecutor, PluginLoader, EventBus
  └── navigate_to(page_id) — 销毁当前页面，创建新页面

HomePage → 7 个功能卡片:
  ├── action_chain    → ActionChainPage    # v1 动作链自动化
  ├── workflow_editor → WorkflowPage       # v2 DAG 工作流编辑器
  ├── plugin          → PluginPage         # 插件管理
  ├── record          → RecordPage         # 宏录制
  ├── notification    → NotificationPage   # 通知设置
  ├── schedule        → SchedulePage       # 定时调度
  └── settings        → SettingsPage       # 全局设置
```

新增功能只需：(1) 创建 `XXXPage(BasePage)` (2) 在 `home_page.py` 的 `_FEATURE_I18N` 列表加一条

## 执行引擎架构

```text
v1: ActionChain → ActionExecutor → 顺序执行
v2: FlowGraph(DAG) → GraphEngine → 拓扑排序 → Layer管道 → Descriptor执行
    └── FSM引擎(opt-in): 状态恢复 + 全局转换 + 延迟事件
```

### 节点描述符

| 类别 | 描述符 | 说明 |
|------|--------|------|
| 流程控制 | Start, End, Loop | 流程起止 + 循环 |
| 点击 | ClickImage, ClickPos | 模板匹配点击 + 固定坐标 |
| 按键 | PressKey, HoldKey, KeyCombo, MultiKeySequence | 单键/长按/组合/多键序列 |
| 等待 | Wait, WaitRandom | 固定/随机等待 |
| 条件 | Condition | 条件分支 |
| 检测 | OCR, PixelSearch | 文字识别 + 像素颜色搜索 |
| 操作 | Scroll, MouseDrag, MouseMove, Record, StartTimer, IdleBehavior | 滚轮/拖拽/移动/录制/计时/空闲 |

### Layer 中间件管道（7 层）

EventBridge → Retry → Timing → Logging → Breakpoint → DebugScreenshot → Pause

### 插件系统

- 接口：`PluginInterface` 基类 + `plugin.json` 清单
- 加载：`PluginLoader` 动态发现 + 加载
- 扩展：插件可注册自定义描述符 + 自定义对话框
- 内置插件：combat（战斗）、navigation（导航）、task（任务）

## 防检测策略

- 鼠标移动带随机时长 (0.15~0.35s) + 缓动曲线
- 点击位置在目标中心附近随机偏移
- 点击前有随机短暂停顿
- 按键操作间有随机延迟
- 所有等待优先使用随机范围

## 并发限制规则（必须严格遵守）

1. 单次回话中最多同时调用3个工具
2. 最多同时启动2个子代理，且子代理必须按顺序执行
3. 禁止使用Agent Teams功能
4. 禁止在后台运行任何任务
5. 所有工具调用必须等待前一个完成后再发起下一个

## 上下文压缩规则（必须严格遵守）

1. 压缩时必须完整保留：
   - 当前正在编辑的所有文件路径
   - 本次会话中所有测试失败的信息和错误日志
   - 已经确认的架构决策和技术选型
   - 项目的目录结构和关键依赖版本
2. 压缩时只总结对话历史，不要修改或删除任何代码片段
3. 压缩后主动告诉我压缩了多少token，以及当前剩余上下文空间
