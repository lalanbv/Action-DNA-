# 主题系统去重 / UI 统一 / 主题 BUG 修复 — 一体化设计规格

- **日期**：2026-06-15
- **状态**：草案（待审查）
- **范围**：tkinter + Qt(PySide6) 双后端 UI 层
- **方法**：MVC + 单一真相源 + 两 View 层分离 + 组件契约
- **执行顺序**：Phase 1 去重 → Phase 2 UI 统一 → Phase 3 主题 BUG 修复

---

## 0. 背景与问题陈述

项目同时维护两套 GUI 后端：

- **tkinter**（`src/panel/`，控件层 `widgets.py` / `components/` / `dialogs/` / `pages/` / `canvas/`）
- **Qt / PySide6**（`src/panel/qt_backend/`，默认后端）

由 `backend_selector.py` 按优先级选择：环境变量 `DNA_GUI_BACKEND` > 配置 `editor.gui_backend` > PySide6 可用性 > 默认 `qt`。

用户提出 5 项诉求：

1. 修复 tkinter/Qt 主题问题（深色/浅色/跟随系统）
2. 修复 tkinter/Qt 主题切换问题（深色/浅色/跟随系统）
3. 消除相同功能重复开发与使用
4. 消除相同组件/模块（功能一样却写了两遍）
5. 统一不规范的界面设计与组件

约束（来自项目记忆与用户指令）：

- **两后端必须共存**，修复 UI BUG 时必须同时处理 tkinter 与 Qt。
- **MVC 设计理念**，tkinter/Qt 设计清晰分离，追求最优逻辑。
- **增量可控**：一步步操作，准备 → 思路 → 文档指挥 → 按步骤执行。
- **YAGNI**：只做与 5 点相关的改动，不做无关重构。

---

## 1. 现状分析

### 1.1 已共享的部分（正确范式，保留并推广）

位于 `src/panel/canvas/theme/`（9 个文件）：

- `tokens.py` — `CanvasTheme` 数据模型（单一 token 真相源）
- `dark_theme.py` / `light_theme.py` — 主题构建
- `theme_manager.py` — 模式切换 / 缓存 / 回调注册表 / `ThemeCallbackMixin`
- `platform_theme.py` — `detect_system_theme()` 跨平台深浅色检测
- `style_mappings.py` / `color_utils.py` / `node_colors.py` / `font_detection.py`

Qt 侧 `src/panel/qt_backend/theme.py` 为 **QSS 生成器**，消费同一套 `CanvasTheme` tokens，不重复定义颜色。✅

另有已验证的「框架无关逻辑下沉」范式：

- `src/panel/home_shared.py` — 主页共享逻辑（banner section 状态、配置扫描、`THEME_CYCLE`）
- `src/panel/canvas/node_shared.py` — 节点尺寸/图标/标签/端口位置（tk `node_renderer.py` 与 Qt `node_item.py` 共享）

**本设计的去重工作 = 系统化推广此范式。**

### 1.2 重复点（去重目标 D1–D5）

| # | 重复内容 | 位置 | 性质 |
|---|---------|------|------|
| D1 | 系统主题轮询逻辑（30s poll + resolved 对比） | `src/panel/app.py:345-352` ↔ `src/panel/qt_backend/app.py:300-311` | 框架无关业务逻辑，可完全下沉 |
| D2 | 主题初始化恢复（读 `editor.theme_mode` → `set_theme_mode`） | `src/panel/app.py:53-57` ↔ `src/panel/qt_backend/app.py:115-119` | 框架无关，可下沉为一个 helper |
| D3 | 页面 i18n 键常量 | `src/panel/pages/page_i18n.py`（仅 tkinter） | Qt 侧缺失或重复定义 |
| D4 | dialog / page registry 注册元数据 | `src/panel/dialogs/dialog_registry.py` ↔ `src/panel/qt_backend/dialogs/dialog_registry.py`；`page_registry.py` 两份 | 注册元数据可下沉 |
| D5 | workflow 页面 mixin 中的纯逻辑 | `src/panel/pages/workflow_*_mixin.py` ↔ `src/panel/qt_backend/pages/workflow_*_mixin.py` | 纯逻辑部分可下沉 |

### 1.3 不一致点（UI 统一目标 U1–U4）

| # | 不一致 | 现状 |
|---|--------|------|
| U1 | 组件目录规模不对等 | tkinter `components/` 32 个 vs Qt `components/` 9 个 |
| U2 | 组件命名前缀混用 | `dna_button` / `themed_checkbox` / `themed_entry` 等多套前缀 |
| U3 | 页面控制器 mixin 结构不同 | tkinter 有 `profile_ops_mixin`、`page_i18n`；Qt 为 `action_chain_props_mixin` |
| U4 | 主题应用机制不同 | tkinter `apply_theme_recursive` 递归配色 vs Qt 全局 QSS + 各组件 `apply_theme` |

### 1.4 主题 BUG 来源（B1–B5）

| # | 问题 | 根因 | 影响 |
|---|------|------|------|
| **B5** ⭐ | **"跟随系统"模式下 OS 深浅色切换不生效** | `set_theme_mode("system")` 命中 `theme_manager.py:158-159` 的 skip 逻辑（mode 未变即不重建），轮询器检测到 OS 变化却无法触发重建/通知；`current_theme()` 持续返回旧缓存 | 跟随系统时 OS 切换后界面卡旧主题，挂机场景失效 |
| B1 | macOS `defaults read` / Linux `gsettings` 在**主线程** subprocess 阻塞 | `platform_theme.detect_system_theme()` 同步 subprocess | "跟随系统"模式每 30s UI 卡顿一次 |
| B2 | 30s 轮询粒度粗 | 固定轮询间隔 | OS 切换后最长 30s 才响应（且因 B5 实际永不响应） |
| B3 | 无 OS 实时通知 | 缺事件订阅 | Qt 本可事件驱动（`colorSchemeChanged`），却用轮询 |
| B4 | 打开的对话框/弹窗切主题不更新 | 主题回调注册覆盖有缺口 | 运行中切换主题，部分浮层停留在旧主题 |

**B5 复现链**（关键）：

```
OS: dark → light
  ↓
poller: resolved_theme_mode() 返回 "light"，与 _last_resolved("dark") 不同
  ↓
poller: set_theme_mode("system")
  ↓
set_theme_mode: mode("system") == _theme_mode("system") 且 _current_theme 非空 → return（跳过）
  ↓
结果：_current_theme 不重建，回调不触发 → 界面停留在 dark
```

---

## 2. 目标与设计原则

### 2.1 目标

1. tkinter/Qt 两后端在深色/浅色/跟随系统下均**正确、无卡顿、实时响应**（修 B1–B5）。
2. 框架无关业务逻辑单一真相源，消除 D1–D5 重复。
3. 两后端组件遵循**统一契约规格**（同名同 props/state/事件语义），各自 idiomatically 实现。
4. 命名 / 间距 / 色彩 / 尺寸**有规范可循、可校验**（U1–U4 收敛）。

### 2.2 设计原则

| 原则 | 含义 |
|------|------|
| 单一真相源 | 业务逻辑、状态、配置、注册元数据、主题 tokens 只存在一份，位于共享层 |
| Model/Controller 共享，View 分离 | 共享层 = 框架无关 Model + Controller；tkinter/Qt 各为独立 View 层，互不 import |
| 薄 View | View 只做渲染 + 事件绑定，所有决策委托共享层 |
| 契约而非继承 | 组件统一靠"契约规格"（数据描述），非抽象基类，避免强加不适合的工具包范式 |
| 增量可回滚 | 逐文件迁移，保留兼容 re-export shim，两后端全程可运行 |
| YAGNI | 只迁移与 5 点相关的逻辑，不做无关重构；不重命名现有目录 |

### 2.3 不做什么（明确排除）

- ❌ 不强求 Qt 复刻 tkinter 的 32 个自定义控件文件（QSS 原生 + 契约即视为已实现）。
- ❌ 不引入抽象基类继承体系（契约是数据，不是继承）。
- ❌ 不重命名现有 tkinter 目录（避免数百处 import 风暴）。
- ❌ 不做与 5 点无关的重构。

---

## 3. 架构总览

### 3.1 分层目标架构

```
src/panel/
├── canvas/theme/              ★ 保留原位：本就是框架无关的共享主题 Model 层
│   ├── tokens.py              # CanvasTheme（单一 token 真相源）
│   ├── theme_manager.py       # 新增 refresh_theme()（B5 修复）+ restore_from_config()（D2）
│   ├── theme_sync.py          ← 新增：系统主题同步编排（D1 下沉 + B1/B2/B3 修复）
│   ├── platform_theme.py      # detect_system_theme()（B1：改为可被 worker 线程调用）
│   └── ...
│
├── shared/                    ★ 新增：非主题的框架无关 Model + Controller
│   ├── page_i18n.py           ← 迁自 pages/page_i18n.py（D3）
│   ├── registries/            ← 迁入注册元数据（D4）：dialog/page registry 数据层
│   ├── controllers/           ← 新增：页面编排纯逻辑（D5 可下沉部分）
│   └── view_specs/            ← 新增：组件契约规格（Phase 2）
│       ├── button.spec.py
│       ├── entry.spec.py
│       └── ...
│
├── [tkinter View 层]          保留原位（避免 import 风暴）
│   ├── widgets.py / components/ / dialogs/ / pages/   ← 变薄，调用 shared + canvas/theme
│   └── canvas/                ← 画布 View（node_renderer 等消费 node_shared）
│
├── qt_backend/                [Qt View 层] 变薄，调用 shared + canvas/theme
│   ├── components/ / dialogs/ / pages/
│   ├── theme.py               ← QSS 生成器（保留，消费 canvas/theme/tokens）
│   ├── theme_sync_backend.py  ← 新增：Qt 主题同步后端（colorSchemeChanged + marshal）
│   └── ...
│
└── backend_selector.py        不变
```

> **关键决策（YAGNI）**：`canvas/theme/` **不迁移**——它本就是框架无关的共享主题 Model 层，已被两后端共用，整体搬迁纯属目录改名、徒增 import 风险。MVC 的"分离"体现在**逻辑分层**（共享 vs View），而非强迫所有共享代码挤进同一个目录名。仅新增 `src/panel/shared/` 收纳**非主题**的共享逻辑；`theme_sync.py` 因与 `theme_manager.py` 强耦合，就近放 `canvas/theme/` 下。
>
> **迁移策略**：`pages/page_i18n.py` 等被迁移的文件在原位置保留 re-export shim（`from src.panel.shared.page_i18n import *`），保证渐进迁移期间现有 import 不破裂；迁入完成、调用方全部切换后再清理 shim。

### 3.2 主题切换数据流（MVC 视角）

```
[用户切换主题]
  → View(tk/Qt)
    → Controller: set_theme_mode(mode)        [canvas/theme/theme_manager]
      → Model: rebuild CanvasTheme            [canvas/theme/tokens + dark/light]
      → Controller: 遍历 _theme_callbacks
        → 各 View.apply_theme() 重新渲染       [tk: 递归配色 / Qt: 重设 QSS]

[OS 切换深浅色]
  → theme_sync 探测（worker 线程 / Qt 实时事件）
    → 检测到 resolved 变化
      → Controller: refresh_theme()           [强制重建 + 通知，不改 mode → 修 B5]
        → 同上级联
```

**关键约束**：所有 `set_theme_mode` / `refresh_theme` 的调用若源自 worker 线程，必须先 marshal 回 UI 主线程后执行（tkinter / Qt 均非线程安全）。

---

## 4. Phase 1 — 代码去重（第一执行阶段）

### 4.1 目标

消除 D1–D5，建立 `shared/` 层，为 Phase 3 的主题 BUG 修复铺设基础设施。

### 4.2 核心产出：`canvas/theme/theme_sync.py`

框架无关的系统主题同步编排器。探测在 worker 线程执行，结果 marshal 回主线程后才触发刷新。

```python
# canvas/theme/theme_sync.py（框架无关，就近放 theme_manager 旁）
from typing import Callable, Protocol
from src.panel.canvas.theme.platform_theme import detect_system_theme
from src.panel.canvas.theme.theme_manager import refresh_theme

class ThemeSyncBackend(Protocol):
    """各后端实现并注入的主题同步原语。"""
    def marshal_main(self, fn: Callable[[], None]) -> None:
        """将回调 marshal 到 UI 主线程执行。"""
    def start_timer(self, interval_ms: int, fn: Callable[[], None]) -> object:
        """启动周期定时器，返回句柄。"""
    def stop_timer(self, handle: object) -> None:
        """停止定时器。"""

class SystemThemeSync:
    """系统主题同步编排。

    探测在 worker 线程跑（不阻塞 UI 主线程 → B1）。
    检测到 OS resolved 变化时，marshal 回主线程调用 refresh_theme()（→ B5）。
    """
    POLL_INTERVAL_MS = 30000   # tk 降级轮询间隔；Qt 走实时信号，此值仅兜底

    def __init__(self) -> None: ...
    def start(self, backend: ThemeSyncBackend) -> None: ...
    def stop(self) -> None: ...
    def _poll(self) -> None:
        """worker 线程：跑 detect_system_theme，变更则 marshal 回主线程刷新。"""
        resolved = detect_system_theme()
        if resolved != self._last_resolved:
            self._last_resolved = resolved
            self._backend.marshal_main(refresh_theme)
```

**两后端 idiomatically 接入**：

- **Qt**（`qt_backend/theme_sync_backend.py`）：
  - 优先接 `QGuiApplication.styleHints().colorSchemeChanged`（Qt 6.5+）→ 实时响应（B2/B3）。
  - 运行时探测 Qt 版本，6.5 以下降级为 worker 轮询。
  - `marshal_main` 用 `QTimer.singleShot(0, fn)`。
- **tk**（`widgets` 或 app 内 `TkThemeSyncBackend`）：
  - worker 线程 + `root.after(0, fn)` marshal 回主线程轮询（B1）。

### 4.3 去重映射表

| # | 现状 | 迁入 | tkinter 侧改动 | Qt 侧改动 |
|---|------|------|---------------|----------|
| D1 | 两 app.py 轮询逻辑 | `canvas/theme/theme_sync.py` | 注入 `TkThemeSyncBackend`，删除内联轮询 | 注入 `QtThemeSyncBackend`，删除内联轮询 |
| D2 | 两 app.py 主题初始化 | `canvas/theme/theme_manager.restore_from_config(cfg)` | 改为调用 | 改为调用 |
| D3 | `pages/page_i18n.py`（仅 tk） | `shared/page_i18n.py` | 原文件改为 re-export shim | 直接 import shared |
| D4 | 两 dialog/page registry | `shared/registries/`（元数据）+ 各后端薄注册器 | 薄注册器消费共享元数据 | 薄注册器消费共享元数据 |
| D5 | 两 workflow mixin 纯逻辑 | `shared/controllers/workflow_ops.py` 等 | mixin 调用 shared | mixin 调用 shared |

### 4.4 Phase 1 验收标准

- [ ] `theme_sync.py` 单测覆盖：探测 / 变更检测 / marshal / start / stop。
- [ ] 两 `app.py` 主题初始化 + 轮询代码缩减为「调用 shared」。
- [ ] `page_i18n` 仅一份定义，Qt 侧不再重复。
- [ ] grep 验证：D1–D5 相关框架无关逻辑在两后端无拷贝。
- [ ] 现有测试全绿；tk 与 Qt 后端均可正常启动。
- [ ] 覆盖率 ≥80%。

---

## 5. Phase 2 — UI 统一 + 组件契约（第二执行阶段）

### 5.1 组件契约规格（`shared/view_specs/`）

**契约 = 纯数据描述（props/state/events 语义），非抽象基类。** 各后端 idiomatically 实现，靠校验测试保证一致。

```python
# shared/view_specs/button.spec.py
from dataclasses import dataclass
from typing import Literal

@dataclass(frozen=True)
class ButtonSpec:
    """按钮契约 — 两后端必须支持这些语义。

    tk 实现: dna_button(variant=...) 工厂
    Qt 实现: QPushButton + setProperty("dnaBtnStyle", variant) + QSS（已存在于 theme.py）
    """
    variant: Literal["primary", "secondary", "danger", "ghost"] = "secondary"
    enabled: bool = True
    loading: bool = False        # 加载态：禁用 + 指示器
    # 事件: on_click（绑定在 View 层）
    # 尺寸: 取自 tokens（button_height / pad_sm / pad_md）
```

**校验机制**（保证"有规范可控"）：

```
tests/unit/panel/test_view_specs.py
  → 遍历 shared/view_specs/*.spec.py
  → 断言两后端各组件工厂接受相同 props、暴露相同状态查询
  → 缺失组件或参数不符 → 测试失败
```

### 5.2 规范化清单

| 项 | 现状问题 | 统一为 |
|----|---------|--------|
| 命名前缀 | `dna_*` / `themed_*` / 裸名混用 | 契约目录统一命名；工厂入口两端同名（如 `make_button`） |
| 硬编码色彩 | 散落 `#1e1e1e` 等 | 全部走 `CanvasTheme` tokens；新增 lint 脚本 grep 拦截 |
| 硬编码尺寸 | 散落魔法数字 | 走 `scale_manager` + tokens |
| 组件目录 | tk 32 / Qt 9 不对等 | 以契约为准：Qt 用「原生 + QSS」满足同契约即视为已实现，不强求 1:1 文件 |
| 间距 / 圆角 | 各处不一 | tokens 统一 `pad_xs/sm/md/lg`、`radius_*` |

### 5.3 Phase 2 验收标准

- [ ] `view_specs/` 覆盖核心组件（button / entry / checkbox / dropdown / dialog…）。
- [ ] 契约一致性测试通过：两后端组件 API 对齐契约。
- [ ] lint 脚本：新增硬编码色彩 / 尺寸被拦截（已存在的列出待清理清单，不阻塞）。
- [ ] 同主题下 tk / Qt 关键页视觉抽查一致。

---

## 6. Phase 3 — 主题 BUG 修复（第三执行阶段）

### 6.1 B5 修复（最关键）

新增 `refresh_theme()`，`theme_sync` 检测到 OS resolved 变化时调用它（而非 `set_theme_mode("system")`）。

```python
# canvas/theme/theme_manager.py 新增
def refresh_theme() -> None:
    """强制重建当前主题并通知所有订阅。

    用于 system 模式下 OS 实际主题变化：不改变 _theme_mode，
    仅清除缓存 + 重建 + 触发回调（绕过 set_theme_mode 的 skip 逻辑）。
    必须在 UI 主线程调用。
    """
    global _current_theme
    _current_theme = None
    current_theme()                       # 重建
    dead_ids: list[int] = []
    for cb_id, cb in list(_theme_callbacks.items()):
        try:
            cb()
        except Exception:
            dead_ids.append(cb_id)
    for cb_id in dead_ids:
        _theme_callbacks.pop(cb_id, None)
```

`theme_sync._poll` 改为：检测到 OS resolved 变化 → `marshal_main(refresh_theme)`。

### 6.2 B1 / B2 / B3 修复（依赖 Phase 1 `theme_sync`）

- **B1**：`detect_system_theme()` 探测移至 worker 线程，主线程无 subprocess 阻塞。
- **B2**：Qt 走 `colorSchemeChanged` 实时信号；tk 维持 30s 轮询但因不阻塞主线程，已无卡顿。
- **B3**：Qt 接 `QGuiApplication.styleHints().colorSchemeChanged`（Qt 6.5+）；运行时探测版本，低版本降级 worker 轮询。

### 6.3 B4 修复（注册覆盖审计）

- 全量审计所有组件 / 对话框 / 页面 / 浮层是否通过 `ThemeCallbackMixin` 或 `on_theme_change` 注册主题回调。
- 列出未注册项，逐一补齐（尤其 on-the-fly 创建的 dialog、popup、tooltip）。
- 新增测试：切换主题后，断言所有已注册控件均收到 `apply_theme`。

### 6.4 主题持久化验证

- 切换主题时写入 `config.editor.theme_mode`（已有 `home_shared.THEME_CYCLE`，验证其持久化路径完整）。
- 重启后从配置恢复（D2 的 `restore_from_config` 覆盖）。

### 6.5 Phase 3 验收标准

- [ ] **B5 回归测试**：system 模式下模拟 OS dark→light，断言 `current_theme()` 重建 + 回调触发（不依赖 skip）。
- [ ] **B1 测试**：macOS 探测在 worker 线程，主线程计时 <5ms。
- [ ] **B3 测试**：Qt `colorSchemeChanged` 触发 `refresh_theme`（offscreen 模式）。
- [ ] **B4 审计报告**：列出所有未注册控件，补齐并有测试。
- [ ] **持久化测试**：切换 → 写入配置 → 重启恢复。
- [ ] 覆盖率 ≥80%。

---

## 7. 测试策略

| 层级 | 范围 | 工具 / 方式 |
|------|------|------------|
| 单元 | `shared/` 全部（theme_sync、refresh_theme、view_specs 校验、registries、controllers） | pytest，目标 ≥80% |
| 集成 | 两后端主题切换端到端；Qt 用 `QT_QPA_PLATFORM=offscreen` 无头跑 | pytest |
| 回归 | B1–B5 各一条回归测试（尤其 B5 OS 切换重建） | pytest |
| 契约一致性 | 遍历 `view_specs/`，断言两后端组件 API 对齐 | pytest |
| 视觉 | 同主题下 tk / Qt 关键页截图比对（半自动） | 截图归档 |

遵循 TDD：每项改动 **RED → GREEN → REFACTOR**，80%+ 覆盖率门禁。

---

## 8. 分阶段交付与风险控制

### 8.1 执行顺序与检查点

```
Phase 1 去重  →  检查点（两后端可启动 + 测试绿）  →  commit
Phase 2 统一  →  检查点（视觉一致 + 契约测试绿）  →  commit
Phase 3 修BUG →  检查点（B1-B5 回归测试绿）       →  commit
```

> **顺序依据**：Phase 1 先建 `theme_sync` 基础设施，Phase 3 才能在其上修 B1/B2/B3；B5/B4 独立于顺序但放最后集中验证。"去重 → 统一 → 修BUG"既是用户优先级，也是技术依赖所必需。

### 8.2 风险与缓解

| 风险 | 缓解 |
|------|------|
| 迁移 `page_i18n` / registries 等破坏 import | 原位置保留 re-export shim；逐文件迁移；每步跑测试 |
| `canvas/theme/` 新增 `theme_sync` / `refresh_theme` 影响现有行为 | `refresh_theme` 为新增函数，不改 `set_theme_mode` 既有语义；新增逻辑有独立单测；`set_theme_mode` 的 skip 逻辑保持不变（仅 system 轮询改走 `refresh_theme`） |
| Qt 6.5 以下无 `colorSchemeChanged` | 运行时探测版本，降级到 worker 轮询 |
| worker 线程与 UI 线程竞争 | 所有 `set_theme_mode` / `refresh_theme` 必须 marshal 回主线程；单测验证 |
| 范围蔓延 | YAGNI：只动与 5 点相关逻辑；无关重构一律不做 |
| tkinter 无头测试困难 | 共享层逻辑全部可在无 GUI 环境测；GUI 层用现有测试模式 |

### 8.3 交付物

1. 本设计规格文档。
2. 三阶段代码 + 测试，每阶段独立 commit（`feat` / `refactor` / `fix` 前缀，遵循项目 git 规范，全局禁用归属）。
3. 每阶段验收清单全部勾选。

---

## 9. 成功标准（整体）

- ✅ D1–D5 重复消除，框架无关逻辑单一真相源。
- ✅ U1–U4 收敛，组件契约可校验。
- ✅ B1–B5 全部修复并有回归测试。
- ✅ tkinter / Qt 两后端在深色 / 浅色 / 跟随系统下视觉与行为一致。
- ✅ 全程增量推进，每阶段两后端可运行、可回滚。
- ✅ 测试覆盖率 ≥80%。
