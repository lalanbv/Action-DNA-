# Qt 等待秒数失效 + 步骤显示错误 + 浮点数值框机制修复

**日期**: 2026-06-18
**类型**: fix (bug)
**影响范围**: Qt 后端 (PySide6) — 动作链 + 工作流 所有浮点数值字段

## 问题描述

用户报告 Qt 版本多个问题:
1. 动作链和工作流的「固定等待」修改秒数不生效 — 改了等待时间没效果
2. 动作步骤列表显示不正确 — 等待列永远空白
3. 动作步骤详细信息显示不正确 — 详情数值错误
4. UI 样式难看

## 根因

经 systematic-debugging 调查,定位到**一个核心机制缺陷** + **属性名残留** + **潜在崩溃**,前 3 个用户可见问题都源于核心机制缺陷。

### 根因 A(核心) — 浮点数值框机制完全损坏

`src/panel/qt_backend/dialogs/base_dialog.py` 的 `_add_labeled_spinbox` 通过 `themed_spinbox` 创建 **`QSpinBox`(仅整数)**。对小数步进(`increment < 1`,如等待秒数 0.1):
- min/max 被乘以 1000(`0.1→100`, `300→300000`),但 `value` 和 `single_step` **未缩放**
- `value=1.0` 喂给 QSpinBox → 截断+钳制到 min=100 → 显示 **"100"**
- `single_step=0.1` 喂给 QSpinBox → 截断为 0 → **上下箭头失效**
- `_get_float` 读 `spin.value()` 直接用,**从不除以 1000**
- `_populate_fields` 的 `setValue(wait_seconds)` 被钳到 100

**后果**: 等待/长按/移动速度等所有浮点字段,在 11 个对话框全部失效 — 动作链(`_add_step_dialog`/`_on_edit_step`)和工作流(`_edit_node_action` → 同一 `open_step_dialog`)都中招。

> tkinter 版用 `tk.Spinbox`(原生浮点),本身正确;工作流错误配置的重试延迟已直接用 `QDoubleSpinBox` — 旁证正确做法。

### 根因 B — 等待列属性名残留

`action_chain_page.py` `_refresh_step_list` 用 `step.wait_time`,但类型化步骤无此字段(迁移前旧 ActionStep 才有;实际为 `WaitStep.wait_seconds` / `WaitRandomStep.wait_min+wait_max`)。`hasattr` 永远 False → 等待列永远空白。

### 根因 C — `ExecutorState` 未导入(潜在崩溃)

`action_chain_page.py` 引用 `ExecutorState.RUNNING`(执行状态 ticker 的 `is_running` lambda),但顶部 import 从未导入。lazy 求值时触发会 `NameError`。

### 根因 D — QDoubleSpinBox 无全局主题

`theme.py` 全局 QSS 只样式化 `QSpinBox`,无 `QDoubleSpinBox` 规则。修复 A 后引入的 QDoubleSpinBox 会是默认丑陋样式。

## 修复方案

### 1. 新增 `themed_doublespinbox` (`src/panel/qt_backend/widgets.py`)
镜像 `themed_spinbox` 的 API(`minimum/maximum/value/single_step/prefix/suffix/objectName`),用 `QDoubleSpinBox`,额外支持 `decimals`(默认 2)。`decimals` 必须先于 `setValue` 设置。

### 2. 修复 `_add_labeled_spinbox` (`src/panel/qt_backend/dialogs/base_dialog.py`)
- `increment < 1`(小数): 改用 `themed_doublespinbox`,真实 `min/max/value/increment`
- `increment >= 1`(整数): 保持 `themed_spinbox`(QSpinBox)
- **删除** ×1000 缩放逻辑
- 返回类型注解改为 `QAbstractSpinBox`
- `_get_float`/`_get_int` 读 `.value()` 对两种控件都正确,无需改动

### 3. 添加 QDoubleSpinBox 全局 QSS (`src/panel/qt_backend/theme.py`)
镜像 QSpinBox 的背景/边框/padding/min-height 规则,确保浮点框主题跟随(深/浅切换一致)。

### 4. 修复步骤列表等待列 (`src/panel/qt_backend/pages/action_chain_page.py`)
新增静态方法 `_step_wait_text(step)`:
- `WaitStep` → `"{wait_seconds:g}s"`
- `WaitRandomStep` → `"{min:g}~{max:g}s"`
- 其他 → `""`(时间信息由 `describe()` 详情列承载)

`_refresh_step_list` 的 `step.wait_time` 替换为 `self._step_wait_text(step)`。

### 5. 补 ExecutorState 导入 (`src/panel/qt_backend/pages/action_chain_page.py`)
`from src.panel.models.chain_model import ChainModel, ExecutorState`

## 受影响对话框(根因 A,全部自动修复)

| 对话框 | 浮点字段 |
|--------|----------|
| QtWaitDialog | wait_seconds |
| QtWaitRandomDialog | wait_min, wait_max |
| QtHoldKeyDialog | hold_duration |
| QtIdleBehaviorDialog | idle_duration, idle_action_chance |
| QtMultiKeySequenceDialog | key_interval_min, key_interval_max |
| QtMouseDragDialog | duration |
| QtKeyComboDialog | hold_duration |
| QtClickPosDialog | hold_duration |
| QtStartTimerDialog | timer_timeout |
| QtClickImageDialog | retry_wait_min, retry_wait_max, hold_duration |
| QtMouseMoveDialog | move_speed, curve_amount |

## 测试

### 新增回归测试
- `tests/unit/panel/qt/test_qt_spinbox_dialog.py`(8 用例): wait/wait_random roundtrip、QDoubleSpinBox 类型与范围验证、整数 spinbox 保持 QSpinBox、`_step_wait_text` 三分支
- `tests/unit/panel/qt/test_qt_widgets.py::TestThemedDoubleSpinbox`(2 用例)

### TDD 流程
- RED: 7 个新测试如期失败(整数分支 1 个本就通过)
- GREEN: 实现后全部通过

### 回归验证(累计 315+ 测试通过, 0 回归)
- Qt 单元测试 68 个(含新测试)
- core step_types + panel chain_model/controller/view_specs 144 个
- Tk 对话框测试 4 个(跨框架完整)
- 序列化 + executor facade + step commands 63 个

### 端到端模拟
编辑等待步骤 1.0s → 0.25s → 保存正确(0.25,原被钳到 100)→ 列表"0.25s"(原空白)→ 详情"等待0.25s"(原错误)。

## 修改文件清单
- `src/panel/qt_backend/widgets.py` — 新增 themed_doublespinbox
- `src/panel/qt_backend/dialogs/base_dialog.py` — 修 _add_labeled_spinbox + import
- `src/panel/qt_backend/theme.py` — 加 QDoubleSpinBox QSS
- `src/panel/qt_backend/pages/action_chain_page.py` — _step_wait_text + ExecutorState 导入 + WaitStep 导入
- `tests/unit/panel/qt/test_qt_spinbox_dialog.py` — 新建回归测试
- `tests/unit/panel/qt/test_qt_widgets.py` — 扩展 TestThemedDoubleSpinbox

## 备注
- tkinter 路径未改动(本身正确,符合双框架统一规则)
- UI 改进聚焦在根因:浮点框主题化是最大视觉收益(不再显示"100"+箭头可用);未做大规模 UI 重写
