# 字段 i18n 化与 QSS 根治与多选拖拽 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 根治 01 期 review 遗留的 3 项——枚举/模式字段绕过 i18n、三个 `_xxx_style` helper 局部 QSS、Qt 多选拖拽只移首行。

**Architecture:** Item 1 在 `step_types.py` 模块级建单一事实源注册表,`describe()` 与 `format_field_value` 共享(行为保持重构);Item 2 把 3 个固定结构 helper 迁到 objectName + 全局 QSS(对齐 `#dnaToolBtn` 约定);Item 3 新增纯函数 `build_insert_block_order` + `drop_insert_target`,`dropEvent` 用光标半行定位、单选/多选统一。

**Tech Stack:** Python 3.11+, PySide6(offscreen), pytest, tkinter(Tk9 逐文件跑), i18n flat-dotted JSON。

## Global Constraints

- Python 3.11+;类型注解齐全;PEP 8;不可变优先。
- i18n key 为**扁平 dotted 字符串**(如 `"common.button.left"`),zh.json 与 en.json **必须成对**补齐。
- Qt 测试 `QT_QPA_PLATFORM=offscreen`;Tk9 多 root 崩溃 → panel Tk 测试**逐文件**跑,禁止同进程多 Tk root。
- 路径/文件名禁空格;变更记录归 `docs/变更记录文档/20260619/`。
- `describe()` 输出**零变化**(行为保持),现有 `test_chain_model`/`test_step_param_view` 即回归守护。
- 提交只在用户要求时进行;本计划每个 Task 末尾的 commit 步骤**待用户确认后执行**。

---

## File Structure

| 文件 | 职责 | 动作 |
|------|------|------|
| `src/utils/translations/zh.json` | 中文扁平 i18n | 新增 5 key |
| `src/utils/translations/en.json` | 英文扁平 i18n | 新增 5 key |
| `src/core/step_types.py` | 类型化步骤 + 字段值翻译注册表 | 新增注册表 + `field_value_i18n_key()`;重构 2 个 `describe()` |
| `src/panel/components/step_param_view.py` | 字段格式化 + order 构造(Qt/tk 共用) | 改 `format_field_value`;新增 `build_insert_block_order` + `drop_insert_target` |
| `src/panel/qt_backend/theme.py` | 全局 QSS | 新增 3 条 objectName 规则 |
| `src/panel/qt_backend/pages/action_chain_props_mixin.py` | Qt 详情面板渲染 | 删 3 helper,改 objectName |
| `src/panel/qt_backend/pages/action_chain_page.py` | Qt 步骤树 + 拖拽 | 改 `dropEvent` 用新算法 |
| `tests/unit/core/test_step_types_field_labels.py` | 注册表 + describe 回归 | 新建 |
| `tests/unit/panel/test_step_param_view.py` | order + 格式化 | 扩充 |
| `tests/unit/panel/qt/test_qt_step_props_panel.py` | objectName 冒烟 | 扩充 |

---

## Task 1: 补齐 i18n key(zh/en)

**Files:**
- Modify: `src/utils/translations/zh.json`(锚点行 201 `"common.mode.all_hold"`、行 269 `"dialog.detect_mode.wait_until_found"`)
- Modify: `src/utils/translations/en.json`(锚点行 202 `"common.mode.all_hold"`、行 270 `"dialog.detect_mode.wait_until_found"`)

**Interfaces:**
- Produces: `common.button.left/right/middle`、`dialog.color_mode.hsv/rgb`(后续 Task 2 注册表引用)

- [ ] **Step 1: zh.json 在 `common.mode.all_hold`(行 201)后插入 button 三键**

在 `"common.mode.all_hold": "全部按住",` 行**之后**新增三行:

```json
    "common.button.left": "左键",
    "common.button.middle": "中键",
    "common.button.right": "右键",
```

- [ ] **Step 2: zh.json 在 `dialog.detect_mode.wait_until_found`(行 269)后插入 color_mode 两键**

在 `"dialog.detect_mode.wait_until_found": "一直等待直到检测到",` 行**之后**新增两行:

```json
    "dialog.color_mode.hsv": "HSV 色彩空间",
    "dialog.color_mode.rgb": "RGB 色彩空间",
```

- [ ] **Step 3: en.json 对应插入(行 202 后 + 行 270 后)**

行 202 `"common.mode.all_hold": "Hold All",` 之后:

```json
    "common.button.left": "Left",
    "common.button.middle": "Middle",
    "common.button.right": "Right",
```

行 270 `"dialog.detect_mode.wait_until_found": "Wait Until Found",` 之后:

```json
    "dialog.color_mode.hsv": "HSV Color Space",
    "dialog.color_mode.rgb": "RGB Color Space",
```

- [ ] **Step 4: 校验 JSON 合法 + key 可取**

Run: `python3 -c "import json; zh=json.load(open('src/utils/translations/zh.json',encoding='utf-8')); en=json.load(open('src/utils/translations/en.json',encoding='utf-8')); assert zh['common.button.left']=='左键' and en['common.button.left']=='Left'; assert zh['dialog.color_mode.hsv'] and en['dialog.color_mode.rgb']; print('OK')"`
Expected: `OK`

- [ ] **Step 5: i18n key 齐全性 gate**

Run: `python -m pytest tests/unit/utils/test_i18n_keys.py tests/unit/utils/test_i18n_lint.py -q`
Expected: PASS(新 key 尚未被代码引用,但齐全性 gate 只校验 JSON 内部一致性;若 gate 校验「代码引用必须存在」则本步可能 WARN,以 Task 2 完成后再跑为准)

---

## Task 2: step_types.py 字段值翻译注册表 + describe() 行为保持重构

**Files:**
- Modify: `src/core/step_types.py`(导入后加注册表;`ClickImageStep.describe` 行 70-84;`KeyComboStep.describe` 行 277-285)
- Test: `tests/unit/core/test_step_types_field_labels.py`(新建)

**Interfaces:**
- Produces: `field_value_i18n_key(field_name: str, raw: str) -> str | None`(模块级公开函数);`_FIELD_VALUE_I18N: dict[str, dict[str, str]]`
- Consumes: Task 1 的 i18n key

- [ ] **Step 1: 写失败测试(新建文件)**

`tests/unit/core/test_step_types_field_labels.py`:

```python
"""step_types 字段值翻译注册表 + describe() 行为保持回归。"""
from __future__ import annotations

from src.core.action import DetectMode, FoundAction, MatchStrategy, ThresholdMode
from src.core.step_types import (
    ClickImageStep,
    KeyComboStep,
    field_value_i18n_key,
)


def test_found_action_lookup() -> None:
    assert field_value_i18n_key("found_action", "LEFT_CLICK") == "dialog.found_action.left_click"
    assert field_value_i18n_key("found_action", "OUTPUT_COORD") == "dialog.found_action.output_coord"


def test_combo_mode_lookup() -> None:
    assert field_value_i18n_key("combo_mode", "hold_tap") == "common.mode.hold_tap"
    assert field_value_i18n_key("combo_mode", "sequence") == "common.mode.sequence"


def test_detect_match_threshold_lookup() -> None:
    assert field_value_i18n_key("detect_mode", "SKIP_IF_NOT_FOUND") == "dialog.detect_mode.skip_if_not_found"
    assert field_value_i18n_key("match_strategy", "ADAPTIVE") == "dialog.match_strategy.adaptive"
    assert field_value_i18n_key("threshold_mode", "GLOBAL") == "dialog.threshold_mode.global"


def test_button_color_mode_lookup() -> None:
    assert field_value_i18n_key("button", "left") == "common.button.left"
    assert field_value_i18n_key("color_mode", "hsv") == "dialog.color_mode.hsv"


def test_unknown_returns_none() -> None:
    assert field_value_i18n_key("found_action", "NOPE") is None
    assert field_value_i18n_key("not_a_field", "x") is None


def test_click_image_describe_translates_found_action() -> None:
    s = ClickImageStep(image_path="/x/btn.png", found_action=FoundAction.RIGHT_CLICK)
    # describe 应含翻译后的「右键点击」而非原始 RIGHT_CLICK
    desc = s.describe()
    assert "RIGHT_CLICK" not in desc
    assert "右键点击" in desc or "Right" in desc  # 视当前 locale


def test_key_combo_describe_translates_mode() -> None:
    s = KeyComboStep(combo_keys="ctrl+c", combo_mode="sequence")
    desc = s.describe()
    assert "sequence" not in desc.lower().replace("sequence", "", 1) or "顺序" in desc or "Sequence" in desc
```

- [ ] **Step 2: 运行测试,确认失败**

Run: `python -m pytest tests/unit/core/test_step_types_field_labels.py -q`
Expected: FAIL(`ImportError: cannot import name 'field_value_i18n_key'`)

- [ ] **Step 3: 在 step_types.py 导入块后(行 19 `from src.utils.i18n import t` 之后)新增注册表与函数**

```python
# ── 字段值翻译注册表(单一事实源)──────────────────────────────────
# Enum.name 或 str 值 → i18n key。describe() 与 step_param_view.format_field_value
# 共用,杜绝双份维护。key 必须在 translations/{zh,en}.json 中成对存在。
_FIELD_VALUE_I18N: dict[str, dict[str, str]] = {
    "found_action": {
        "LEFT_CLICK": "dialog.found_action.left_click",
        "RIGHT_CLICK": "dialog.found_action.right_click",
        "LEFT_DOUBLE_CLICK": "dialog.found_action.left_double_click",
        "RIGHT_DOUBLE_CLICK": "dialog.found_action.right_double_click",
        "LONG_PRESS": "dialog.found_action.long_press",
        "DRAG_TO": "dialog.found_action.drag_to",
        "ONLY_MOVE": "dialog.found_action.only_move",
        "OUTPUT_COORD": "dialog.found_action.output_coord",
    },
    "detect_mode": {
        "WAIT_UNTIL_FOUND": "dialog.detect_mode.wait_until_found",
        "SKIP_IF_NOT_FOUND": "dialog.detect_mode.skip_if_not_found",
        "FAIL_IF_NOT_FOUND": "dialog.detect_mode.fail_if_not_found",
    },
    "match_strategy": {
        "ADAPTIVE": "dialog.match_strategy.adaptive",
        "FIRST_MATCH": "dialog.match_strategy.first_match",
        "BEST_CONFIDENCE": "dialog.match_strategy.best_confidence",
    },
    "threshold_mode": {
        "GLOBAL": "dialog.threshold_mode.global",
        "AUTO": "dialog.threshold_mode.auto",
        "PER_TEMPLATE": "dialog.threshold_mode.per_template",
    },
    "combo_mode": {
        "hold_tap": "common.mode.hold_tap",
        "sequence": "common.mode.sequence",
        "all_hold": "common.mode.all_hold",
    },
    "button": {
        "left": "common.button.left",
        "right": "common.button.right",
        "middle": "common.button.middle",
    },
    "color_mode": {
        "hsv": "dialog.color_mode.hsv",
        "rgb": "dialog.color_mode.rgb",
    },
}


def field_value_i18n_key(field_name: str, raw: str) -> str | None:
    """返回字段原始值(Enum.name 或 str 值)对应的 i18n key;无映射返回 None。"""
    return _FIELD_VALUE_I18N.get(field_name, {}).get(raw)
```

- [ ] **Step 4: 重构 ClickImageStep.describe(行 70-84),删 fa_keys 局部 dict**

替换整个 `describe` 方法体为:

```python
    def describe(self) -> str:
        name = os.path.basename(self.image_path) if self.image_path else t("common.not_set")
        action_label = t(field_value_i18n_key("found_action", self.found_action.name) or "")
        return t("action.describe.click_image", name=name, action=action_label)
```

- [ ] **Step 5: 重构 KeyComboStep.describe(行 277-285),删 mode_map 局部 dict**

替换整个 `describe` 方法体为:

```python
    def describe(self) -> str:
        mode_name = t(field_value_i18n_key("combo_mode", self.combo_mode) or "")
        return t("action.describe.key_combo", keys=self.combo_keys, mode=mode_name)
```

- [ ] **Step 6: 运行新测试,确认通过**

Run: `python -m pytest tests/unit/core/test_step_types_field_labels.py -q`
Expected: PASS(7 passed)

- [ ] **Step 7: describe() 零变化回归**

Run: `python -m pytest tests/unit/panel/test_chain_model.py tests/unit/panel/test_step_param_view.py -q`
Expected: PASS(全部既有用例不回退)

- [ ] **Step 8: i18n lint(注册表引用的 key 必须存在于 JSON)**

Run: `python scripts/lint_i18n_keys.py && python -m pytest tests/unit/utils/test_i18n_lint.py tests/unit/utils/test_i18n_keys.py -q`
Expected: PASS / exit 0

---

## Task 3: format_field_value 接入翻译

**Files:**
- Modify: `src/panel/components/step_param_view.py`(`format_field_value` 行 78-99;导入块行 16-18)
- Test: `tests/unit/panel/test_step_param_view.py`(扩充)

**Interfaces:**
- Consumes: `field_value_i18n_key` from Task 2
- Produces: `format_field_value` 对注册字段返回翻译值

- [ ] **Step 1: 写失败测试(追加到 test_step_param_view.py 末尾)**

```python
def test_format_enum_field_translated() -> None:
    from src.core.step_types import ClickImageStep
    s = ClickImageStep()  # found_action 默认 LEFT_CLICK
    assert format_field_value(s, "found_action") != "LEFT_CLICK"  # 不再是原始 .name


def test_format_str_mode_field_translated() -> None:
    from src.core.step_types import KeyComboStep
    s = KeyComboStep(combo_mode="sequence")
    assert format_field_value(s, "combo_mode") != "sequence"


def test_format_unregistered_str_passthrough() -> None:
    from src.core.step_types import PressKeyStep
    s = PressKeyStep(key="space")  # key 字段未注册 → 保持原值
    assert format_field_value(s, "key") == "space"


def test_format_button_translated() -> None:
    from src.core.step_types import ClickPosStep
    s = ClickPosStep(button="right")
    assert format_field_value(s, "button") != "right"
```

- [ ] **Step 2: 运行,确认失败**

Run: `python -m pytest tests/unit/panel/test_step_param_view.py -q -k "translated or passthrough"`
Expected: FAIL(当前 Enum 返回 `value.name`、str 返回原值)

- [ ] **Step 3: 在 step_param_view.py 导入块加 field_value_i18n_key**

把行 16 `from src.core.step_types import WaitRandomStep, WaitStep` 改为:

```python
from src.core.step_types import WaitRandomStep, WaitStep, field_value_i18n_key
```

- [ ] **Step 4: 重写 format_field_value(行 78-99)**

```python
def format_field_value(step, field_name: str) -> str:
    """格式化单个字段值为人类可读字符串。

    Enum/语义字符串优先查 ``_FIELD_VALUE_I18N`` 注册表翻译;按键名等未注册值保持原样;
    路径(含 / 或 \\)→ basename;空串→未设置;list/tuple→「N 项」;None→``--``;
    bool→✓/✗;其余→``str``。
    """
    value = getattr(step, field_name, None)
    if value is None:
        return "--"
    if isinstance(value, Enum):
        key = field_value_i18n_key(field_name, value.name)
        return t(key) if key else value.name
    if isinstance(value, bool):
        return "✓" if value else "✗"
    if isinstance(value, str):
        if value == "":
            return t("common.not_set")
        key = field_value_i18n_key(field_name, value)
        if key:
            return t(key)
        if "/" in value or "\\" in value:
            return os.path.basename(value)
        return value
    if isinstance(value, (list, tuple)):
        return t("chain.detail.n_items", count=len(value)) if value else "--"
    return str(value)
```

- [ ] **Step 5: 运行,确认通过**

Run: `python -m pytest tests/unit/panel/test_step_param_view.py -q`
Expected: PASS(既有 + 4 新增全过)

---

## Task 4: build_insert_block_order + drop_insert_target 纯函数

**Files:**
- Modify: `src/panel/components/step_param_view.py`(新增两个函数,置于 `build_bottom_order` 之后、`format_field_value` 之前,即行 75 后)
- Test: `tests/unit/panel/test_step_param_view.py`(扩充)

**Interfaces:**
- Produces: `build_insert_block_order(n, selected, target) -> list[int]`、`drop_insert_target(target_idx, click_below_center, n) -> int`

- [ ] **Step 1: 写失败测试(追加到 test_step_param_view.py)**

在导入顶部追加 `build_insert_block_order, drop_insert_target`(与现有 `build_move_order` 等同组导入)。

```python
def test_insert_block_contiguous_to_middle() -> None:
    # [0,1,2,3,4], 选中 [1,2] 插到 target=4 之前 → [0,3,1,2,4]
    assert build_insert_block_order(5, [1, 2], 4) == [0, 3, 1, 2, 4]


def test_insert_block_to_end() -> None:
    # 选中 [0,1] 插到末尾 target=5 → [2,3,4,0,1]
    assert build_insert_block_order(5, [0, 1], 5) == [2, 3, 4, 0, 1]


def test_insert_block_non_contiguous_keeps_relative_order() -> None:
    # 选中 [1,3] 插到 target=0(顶部)→ [1,3,0,2,4]
    assert build_insert_block_order(5, [1, 3], 0) == [1, 3, 0, 2, 4]


def test_insert_block_drop_on_self_is_noop() -> None:
    # 选中 [2,3],target 落在块内 → 原序
    assert build_insert_block_order(5, [2, 3], 2) == [0, 1, 2, 3, 4]


def test_insert_block_single_matches_before_target() -> None:
    # 单元素 [2] 插到 target=4 之前 → [0,1,3,2,4]
    assert build_insert_block_order(5, [2], 4) == [0, 1, 3, 2, 4]


def test_insert_block_empty_or_bad_returns_identity() -> None:
    assert build_insert_block_order(5, [], 3) == [0, 1, 2, 3, 4]
    assert build_insert_block_order(5, [9], 3) == [0, 1, 2, 3, 4]
    assert build_insert_block_order(5, [1], 99) == [0, 1, 2, 3, 4]


def test_drop_insert_target_below_all_appends() -> None:
    assert drop_insert_target(None, False, 5) == 5


def test_drop_insert_target_upper_half_before() -> None:
    assert drop_insert_target(3, False, 5) == 3


def test_drop_insert_target_lower_half_after() -> None:
    assert drop_insert_target(3, True, 5) == 4
```

- [ ] **Step 2: 运行,确认失败**

Run: `python -m pytest tests/unit/panel/test_step_param_view.py -q -k "insert_block or drop_insert"`
Expected: FAIL(`ImportError`)

- [ ] **Step 3: 在 step_param_view.py 新增两函数(行 75 `build_bottom_order` 之后)**

```python
def build_insert_block_order(n: int, selected: list[int], target: int) -> list[int]:
    """选中块(保相对顺序)整体 insert 到 ``target`` 下标之前;``target==n`` 追加末尾。

    ``target`` 为「移除选中后」的目标位(与 ``build_move_order`` 的 pop-后-按下标插入
    语义对齐)。``selected`` 去重保序;非法/空选/越界时原序返回。供拖拽多选块落点使用。
    """
    sel = sorted({s for s in selected if 0 <= s < n})
    if not sel or not (0 <= target <= n):
        return list(range(n))
    sel_set = set(sel)
    remaining = [i for i in range(n) if i not in sel_set]
    sel_before = sum(1 for s in sel if s < target)
    insert_pos = max(0, min(target - sel_before, len(remaining)))
    return remaining[:insert_pos] + sel + remaining[insert_pos:]


def drop_insert_target(target_idx: int | None, click_below_center: bool, n: int) -> int:
    """由拖拽落点计算 insert target 下标(供 ``build_insert_block_order``)。

    ``target_idx=None`` → 落到所有行下方空区 → 追加末尾(``n``);
    否则光标在目标行下半部 → ``idx+1``,上半部 → ``idx``。Qt 原生拖拽指示线语义。
    """
    if target_idx is None:
        return n
    return target_idx + 1 if click_below_center else target_idx
```

- [ ] **Step 4: 运行,确认通过**

Run: `python -m pytest tests/unit/panel/test_step_param_view.py -q`
Expected: PASS(既有 + 9 新增全过)

---

## Task 5: Qt dropEvent 用新算法(半行定位 + 单选/多选统一)

**Files:**
- Modify: `src/panel/qt_backend/pages/action_chain_page.py`(`_ReorderableTreeWidget.dropEvent` 行 73-84;导入块行 27-33)
- Test: `tests/unit/panel/qt/test_qt_step_props_panel.py`(扩充导入冒烟)

**Interfaces:**
- Consumes: `build_insert_block_order`, `drop_insert_target` from Task 4

- [ ] **Step 1: 写导入冒烟测试(确认 dropEvent 已切换到新算法,不再用 build_move_order 处理多选)**

追加到 `tests/unit/panel/qt/test_qt_step_props_panel.py`(确保文件已 `QT_QPA_PLATFORM=offscreen`):

```python
def test_reorderable_tree_uses_block_order_module() -> None:
    """_ReorderableTreeWidget.dropEvent 必须引用 build_insert_block_order(多选块语义)。"""
    import inspect

    from src.panel.qt_backend.pages import action_chain_page as mod

    src = inspect.getsource(mod._ReorderableTreeWidget.dropEvent)
    assert "build_insert_block_order" in src
    assert "drop_insert_target" in src
    # 不应再用只取首行的旧写法
    assert "_drag_rows[0]" not in src
```

- [ ] **Step 2: 运行,确认失败**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/unit/panel/qt/test_qt_step_props_panel.py::test_reorderable_tree_uses_block_order_module -q`
Expected: FAIL(`_drag_rows[0]` 仍存在)

- [ ] **Step 3: 更新导入块(行 27-33)加入两个新函数**

把:
```python
from src.panel.components.step_param_view import (
    build_batch_move_order,
    build_bottom_order,
    build_move_order,
    build_top_order,
    wait_text,
)
```
改为:
```python
from src.panel.components.step_param_view import (
    build_batch_move_order,
    build_bottom_order,
    build_insert_block_order,
    build_move_order,
    build_top_order,
    drop_insert_target,
    wait_text,
)
```

- [ ] **Step 4: 重写 dropEvent(行 73-84)**

```python
    def dropEvent(self, event):
        if event.source() is not self or not self._drag_rows:
            super().dropEvent(event)
            return
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        target_item = self.itemAt(pos)
        n = self.topLevelItemCount()
        if target_item is None:
            target_idx = None
            click_below = False
        else:
            target_idx = self.indexOfTopLevelItem(target_item)
            rect = self.visualItemRect(target_item)
            click_below = pos.y() > rect.center().y()
        target = drop_insert_target(target_idx, click_below, n)
        new_order = build_insert_block_order(n, self._drag_rows, target)
        self._drag_rows = []
        event.accept()
        self.reordered.emit(new_order)
```

- [ ] **Step 5: 运行冒烟测试,确认通过**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/unit/panel/qt/test_qt_step_props_panel.py -q`
Expected: PASS

- [ ] **Step 6: controller reorder 回归(reorder_steps 不变)**

Run: `python -m pytest tests/unit/panel/test_action_chain_controller_reorder.py -q`
Expected: PASS

---

## Task 6: QSS 根治 —— objectName + 全局 QSS

**Files:**
- Modify: `src/panel/qt_backend/theme.py`(在 `QPushButton#dnaMonBtn` 规则块之后、约行 76 处新增 3 条规则)
- Modify: `src/panel/qt_backend/pages/action_chain_props_mixin.py`(删 `_input_style`/`_btn_style`/`_delete_btn_style` 行 212-255;改 4 处调用点)
- Test: `tests/unit/panel/qt/test_qt_step_props_panel.py`(扩充 objectName 断言)

**Interfaces:**
- Produces: 全局 QSS 规则 `QLineEdit#dnaDetailInput, QSpinBox#dnaDetailInput`、`QPushButton#dnaDetailBtn`、`QPushButton#dnaDeleteBtn`

- [ ] **Step 1: 写失败测试(追加到 test_qt_step_props_panel.py)**

```python
def test_props_inputs_and_buttons_use_objectname(page: "_FakePage") -> None:
    from PySide6.QtWidgets import QLineEdit, QPushButton, QSpinBox

    from src.core.action import ActionType
    from src.core.step_types import STEP_CLASSES

    step = STEP_CLASSES[ActionType.CLICK_IMAGE]()
    page._show_step_props(step, 0, 3)

    inputs = page._host.findChildren(QLineEdit) + page._host.findChildren(QSpinBox)
    assert any(w.objectName() == "dnaDetailInput" for w in inputs), "备注/序号输入框须 dnaDetailInput"

    btns = page._host.findChildren(QPushButton)
    names = {w.objectName() for w in btns}
    assert "dnaDetailBtn" in names, "常规按钮须 dnaDetailBtn"
    assert "dnaDeleteBtn" in names, "删除按钮须 dnaDeleteBtn"
```

- [ ] **Step 2: 运行,确认失败**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/unit/panel/qt/test_qt_step_props_panel.py::test_props_inputs_and_buttons_use_objectname -q`
Expected: FAIL(objectName 为空)

- [ ] **Step 3: theme.py 在 `QPushButton#dnaToolBtn:hover {...}` 块之后(约行 87)新增 3 条全局 QSS 规则**

```css

    /* ── 详情面板 widget(action_chain_props_mixin)—— objectName 全局 QSS,随主题刷新 ── */
    QLineEdit#dnaDetailInput, QSpinBox#dnaDetailInput {{
        background-color: {t.input_bg};
        color: {t.text_primary};
        border: 1px solid {t.border_default};
        border-radius: 3px;
        padding: 2px {qt_scale_manager().s(4)}px;
        font-size: {qt_scale_manager().s(10)}px;
    }}
    QLineEdit#dnaDetailInput:focus, QSpinBox#dnaDetailInput:focus {{
        border-color: {t.accent_blue};
    }}
    QPushButton#dnaDetailBtn {{
        background-color: {t.btn_bg};
        color: {t.text_primary};
        border: 1px solid {t.border_default};
        border-radius: 3px;
        padding: {qt_scale_manager().s(4)}px;
        font-size: {qt_scale_manager().s(10)}px;
    }}
    QPushButton#dnaDetailBtn:hover {{
        background-color: {t.btn_bg_hover};
        border-color: {t.accent_blue};
    }}
    QPushButton#dnaDeleteBtn {{
        background-color: transparent;
        color: {t.accent_red};
        border: 1px solid {t.accent_red};
        border-radius: 3px;
        padding: {qt_scale_manager().s(4)}px;
        font-size: {qt_scale_manager().s(10)}px;
    }}
    QPushButton#dnaDeleteBtn:hover {{
        background-color: {t.accent_red};
        color: white;
    }}
```

> 注意:theme.py 的 QSS 字符串用 `str.format` 风格(`{t.input_bg}`、`{{` `}}` 转义大括号)。新增规则须遵循同一格式,置于该 format 字符串内部。实现时定位 `QPushButton#dnaToolBtn:hover` 块结尾的 `}}` 之后插入。

- [ ] **Step 4: mixin 改调用点为 setObjectName**

(a) 行 111 `comment_edit.setStyleSheet(self._input_style(th, sm))` → 删除该行,改为在其创建后:
```python
        comment_edit = QLineEdit(step.comment or "")
        comment_edit.setObjectName("dnaDetailInput")
```
(即移除 `setStyleSheet`,加 `setObjectName`)

(b) 行 117-118 `btn_style = self._btn_style(th, sm)` 与行 125 `b.setStyleSheet(btn_style)` → 删除 `btn_style` 变量,`b = QPushButton(text)` 之后加 `b.setObjectName("dnaDetailBtn")`。

(c) 行 130 `del_btn.setStyleSheet(self._delete_btn_style(th, sm))` → 改为 `del_btn.setObjectName("dnaDeleteBtn")`。

(d) `_build_move_to_row`(行 148-166):行 157 `spin.setStyleSheet(self._input_style(th, sm))` → `spin.setObjectName("dnaDetailInput")`;行 161 `confirm.setStyleSheet(self._btn_style(th, sm))` → `confirm.setObjectName("dnaDetailBtn")`。

- [ ] **Step 5: 删除三个 helper 方法(行 212-255 整段)**

删除 `_input_style`、`_btn_style`、`_delete_btn_style` 三个方法及其上方注释行 `# ── 样式 helper(随主题刷新)──`。

- [ ] **Step 6: 校验无残留引用**

Run: `grep -n "_input_style\|_btn_style\|_delete_btn_style" src/panel/qt_backend/pages/action_chain_props_mixin.py src/panel/qt_backend/pages/action_chain_page.py`
Expected: 无输出(已全部移除)

- [ ] **Step 7: 运行 Qt 属性面板测试,确认通过**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/unit/panel/qt/test_qt_step_props_panel.py -q`
Expected: PASS(含新 objectName 断言)

- [ ] **Step 8: mypy 类型检查(改动文件)**

Run: `python -m mypy src/core/step_types.py src/panel/components/step_param_view.py src/panel/qt_backend/pages/action_chain_props_mixin.py src/panel/qt_backend/pages/action_chain_page.py --ignore-missing-imports`
Expected: 无新增错误

---

## Task 7: 全量验证 + 变更记录

**Files:**
- Verify: 全部新增/改动测试 + i18n gate + mypy
- Create: `docs/变更记录文档/20260619/字段i18n化与QSS根治与多选拖拽.md`

- [ ] **Step 1: 相关单元测试全量**

Run: `python -m pytest tests/unit/core/test_step_types_field_labels.py tests/unit/panel/test_step_param_view.py tests/unit/panel/test_chain_model.py tests/unit/panel/test_action_chain_controller_reorder.py -q`
Expected: PASS

- [ ] **Step 2: Qt 测试(offscreen)**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/unit/panel/qt/test_qt_step_props_panel.py -q`
Expected: PASS

- [ ] **Step 3: i18n gate 全量**

Run: `python scripts/lint_i18n_keys.py && python -m pytest tests/unit/utils/test_i18n.py tests/unit/utils/test_i18n_lint.py tests/unit/utils/test_i18n_keys.py tests/unit/utils/test_lint_i18n_cli.py -q`
Expected: PASS / exit 0

- [ ] **Step 4: mypy 全量(改动文件)**

Run: `python -m mypy src/core/step_types.py src/panel/components/step_param_view.py src/panel/qt_backend/theme.py src/panel/qt_backend/pages/action_chain_props_mixin.py src/panel/qt_backend/pages/action_chain_page.py --ignore-missing-imports`
Expected: 无新增错误

- [ ] **Step 5: Tk 侧冒烟(format_field_value 共用,确认 tk 详情也翻译)**

Run: `python -m pytest tests/unit/panel/test_step_property_panel_tk.py -q`(若存在;逐文件跑)
Expected: PASS

- [ ] **Step 6: 写变更记录**

创建 `docs/变更记录文档/20260619/字段i18n化与QSS根治与多选拖拽.md`,按既有变更记录格式记录:背景、3 项改动、影响文件、测试、风险/回滚。

- [ ] **Step 7: 汇报 + 等待提交确认**

向用户汇报全部验证结果(贴关键输出),**等待用户确认后再 commit**(用户规则:仅按要求提交)。

---

## Self-Review(已完成)

- **Spec 覆盖**:Item 1 → Task 1+2+3;Item 2 → Task 6;Item 3 → Task 4+5;变更记录 → Task 7。第 4 项(路径 sniff)按 spec 不做。✓
- **占位符扫描**:每步含完整代码/确切命令/预期输出,无 TBD。✓
- **类型一致**:`field_value_i18n_key(field_name:str, raw:str)->str|None`、`build_insert_block_order(n:int, selected:list[int], target:int)->list[int]`、`drop_insert_target(target_idx:int|None, click_below_center:bool, n:int)->int` 在各 Task 间签名一致。✓
- **行为保持**:`describe()` 重构为 `t(field_value_i18n_key(...) or "")`,与原 `t(dict.get(name, ""))` 等价;Task 2 Step 7 回归守护。✓
