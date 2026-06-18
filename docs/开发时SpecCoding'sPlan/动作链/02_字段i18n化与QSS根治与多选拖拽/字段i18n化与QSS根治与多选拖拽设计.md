# 字段 i18n 化与 QSS 根治与多选拖拽 设计

> 承接 01 期「步骤详情与快速重排」。针对 01 期收尾 review 标记的 3 个「超出当次 scope」遗留项,做最纯粹/最安全/最正规的根治。第 4 项(路径 sniff)判定可接受,不做。

- 日期:2026-06-19
- 范围:`src/core/step_types.py`、`src/panel/components/step_param_view.py`、`src/panel/qt_backend/theme.py`、`src/panel/qt_backend/pages/action_chain_props_mixin.py`、`src/panel/qt_backend/pages/action_chain_page.py`、`src/utils/translations/{zh,en}.json`
- 双框架:Item 1 走共用层(Qt/tk 同时受益);Item 2/3 为 Qt 专有(QSS/拖拽)。

---

## 1. 背景与遗留项

01 期 review 标记 4 项,本次处理 3 项:

| # | 遗留项 | 严重度 | 处理 |
|---|--------|--------|------|
| 1 | 枚举/模式字段绕过 i18n(`LEFT_CLICK`/`hold_tap` 原始值) | 高 | ✅ 本期 |
| 2 | 三个 `_xxx_style` helper 重复 + 局部 QSS | 中 | ✅ 本期 |
| 3 | Qt 多选拖拽只移首行 | 中(bug) | ✅ 本期 |
| 4 | 路径判断 sniff 值内容 | 低 | ⏭️ 可接受,不做 |

---

## 2. Item 1 — 枚举/模式字段 i18n 化

### 2.1 根因

`step_param_view.format_field_value`([step_param_view.py:78-99](../../../src/panel/components/step_param_view.py)):

- `Enum` → 返回 `value.name`(如 `LEFT_CLICK`、`SKIP_IF_NOT_FOUND`、`ADAPTIVE`、`GLOBAL`)
- 模式 `str` → 返回原值(如 `hold_tap`、`sequence`、`all_hold`、`left`、`hsv`)

这些原始值直接进入「关键参数」「全部字段」表 → 绕过 i18n。而 `step_types.py` 各 `describe()` 内**已存在**等价翻译表(`ClickImageStep.fa_keys`、`KeyComboStep.mode_map` 等),形成**双份维护**。

### 2.2 方案:模块级单一事实源(方案 B)

`describe()` 早已耦合 i18n(调用 `t()`),因此把翻译表提到 `step_types.py` 模块级、供 `describe()` 与 `format_field_value` 共享,是**消除重复**的最纯粹解,且为行为保持重构。

**新增(`src/core/step_types.py` 模块级)**:

```python
# 字段原始值(Enum.name 或 str 值)→ i18n key 的统一注册表。
# describe() 与 step_param_view.format_field_value 共用,杜绝双份维护。
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
        "SKIP_IF_NOT_FOUND": "dialog.detect_mode.skip_if_not_found",
        "FAIL_IF_NOT_FOUND": "dialog.detect_mode.fail_if_not_found",
        "WAIT_UNTIL_FOUND": "dialog.detect_mode.wait_until_found",
    },
    "match_strategy": {
        "ADAPTIVE": "dialog.match_strategy.adaptive",
        "BEST_CONFIDENCE": "dialog.match_strategy.best_confidence",
        "FIRST_MATCH": "dialog.match_strategy.first_match",
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
    """返回字段原始值对应的 i18n key;无映射返回 None。"""
    return _FIELD_VALUE_I18N.get(field_name, {}).get(raw)
```

> key 的实际枚举名(`FAIL_IF_NOT_FOUND`/`WAIT_UNTIL_FOUND`/`BEST_CONFIDENCE`/`FIRST_MATCH`/`PER_TEMPLATE`)实现时以 `src/core/action.py` 中 `DetectMode`/`MatchStrategy`/`ThresholdMode`/`FoundAction` 的真实 `.name` 为准核对。

**`describe()` 改造(行为保持)**:

```python
# ClickImageStep.describe:原 fa_keys 局部 dict 删除,改为:
action_label = t(field_value_i18n_key("found_action", self.found_action.name) or "")
# KeyComboStep.describe:原 mode_map 局部 dict 删除,改为:
mode_name = t(field_value_i18n_key("combo_mode", self.combo_mode) or "")
```

**`format_field_value` 改造**:

```python
if isinstance(value, Enum):
    raw = value.name
    key = field_value_i18n_key(field_name, raw)
    return t(key) if key else raw          # 注册→翻译;未注册(如按键名)→原 .name
if isinstance(value, str):
    if value == "":
        return t("common.not_set")
    key = field_value_i18n_key(field_name, value)
    if key:
        return t(key)
    if "/" in value or "\\" in value:       # 路径 → basename
        return os.path.basename(value)
    return value
```

**新增 i18n key(zh/en 各一份)**:`common.button.left/right/middle`、`dialog.color_mode.hsv/rgb`。其余 key 已存在。

### 2.3 安全性

- `describe()` 输出**零变化**:原 `t(fa_keys.get(name, ""))` 与新 `t(field_value_i18n_key(...) or "")` 等价;现有 `test_chain_model`/`test_step_param_view` 即回归守护。
- `format_field_value` 对未注册字段(按键名 `key`、路径、数字)保持原逻辑,无副作用。
- Qt/tk 共用 `format_field_value`,一处修复双框架生效(符合 UI 双框架同步规则)。
- i18n lint:新 key 以字符串字面量出现在注册表,AST key 校验可见;补齐 zh/en 双语。

---

## 3. Item 2 — 三个 `_xxx_style` helper QSS 根治

### 3.1 根因

`QtActionChainPropsMixin._input_style/_btn_style/_delete_btn_style`([action_chain_props_mixin.py:212-255](../../../src/panel/qt_backend/pages/action_chain_props_mixin.py))用局部 `setStyleSheet` 构造 QSS,不符合项目 objectName + 全局 QSS 约定(见 `qt-qss-stylesheet-isolation-theme-bug` 记忆:局部 setStyleSheet 形成样式上下文隔离,主题切换不跟随)。

### 3.2 方案:objectName + 全局 QSS(方案 A,对齐 `#dnaToolBtn`/`#dnaMonBtn`/`#dnaStyledPanel`)

**`src/panel/qt_backend/theme.py` 全局 QSS 新增**:

```css
/* 详情面板输入框 —— objectName 全局 QSS,随主题刷新 */
QLineEdit#dnaDetailInput, QSpinBox#dnaDetailInput {
    background-color: {t.input_bg};
    color: {t.text_primary};
    border: 1px solid {t.border_default};
    border-radius: 3px;
    padding: 2px {qt_scale_manager().s(4)}px;
    font-size: {qt_scale_manager().s(10)}px;
}
QLineEdit#dnaDetailInput:focus, QSpinBox#dnaDetailInput:focus {
    border-color: {t.accent_blue};
}
/* 详情面板常规按钮 */
QPushButton#dnaDetailBtn {
    background-color: {t.btn_bg};
    color: {t.text_primary};
    border: 1px solid {t.border_default};
    border-radius: 3px;
    padding: {qt_scale_manager().s(4)}px;
    font-size: {qt_scale_manager().s(10)}px;
}
QPushButton#dnaDetailBtn:hover {
    background-color: {t.btn_bg_hover};
    border-color: {t.accent_blue};
}
/* 详情面板删除按钮(危险色) */
QPushButton#dnaDeleteBtn {
    background-color: transparent;
    color: {t.accent_red};
    border: 1px solid {t.accent_red};
    border-radius: 3px;
    padding: {qt_scale_manager().s(4)}px;
    font-size: {qt_scale_manager().s(10)}px;
}
QPushButton#dnaDeleteBtn:hover {
    background-color: {t.accent_red};
    color: white;
}
```

**mixin 改造**:

- 删除 `_input_style`/`_btn_style`/`_delete_btn_style` 三个方法。
- `comment_edit`/`spin`(move_to)→ `setObjectName("dnaDetailInput")`。
- `↑↓ 复制 编辑` 按钮 → `setObjectName("dnaDetailBtn")`。
- 删除按钮 → `setObjectName("dnaDeleteBtn")`。
- `apply_theme` 不再需要为这些 widget 重涂(全局 QSS 随主题自动刷新);`_show_step_props` 末尾重建面板时 objectName 自动带上样式。

### 3.3 边界:不迁的部分(关键)

`_build_param_grid` 的 `label_style`/`value_style`、`_add_collapsible_fields` 的 toggle 样式带**按调用变化的 `font_px` 参数**(`sm.s(9)`/`sm.s(8)`),全局 QSS 无法表达参数化字号 → **正确保留内联**。强行迁全局是错误设计。本期只迁「结构固定、可全局化」的 3 个 helper,边界清晰。

### 3.4 安全性

- objectName 选择器特异性高于类型选择器,精确覆盖该面板内 widget,不影响其它 `QLineEdit`/`QPushButton`。
- 主题切换走全局 QSS 重建(`theme.py` 已有的主题刷新路径),消除样式上下文隔离风险。
- 视觉与原 helper 等价(同色/同 padding/同字号)。

---

## 4. Item 3 — Qt 多选拖拽(光标半行精确定位)

### 4.1 根因

`_ReorderableTreeWidget.dropEvent`([action_chain_page.py:73-84](../../../src/panel/qt_backend/pages/action_chain_page.py)):

```python
new_order = build_move_order(n, self._drag_rows[0], target)   # 只取首行
```

多选时仅首行移动,其余选中项原地不动。

### 4.2 关键洞察:现有单行真实语义

核对 `build_move_order(n, src, target)`:pop `src` 后按 `target` 下标插入 → 实际效果是「drop 到目标行 → 落在该行**之后**」。因此与其在「前/后」二选一,采用**原生 Qt 标准的半行定位**(拖拽指示线语义)更优:光标落在目标行上半部→插到该行前,下半部→插到该行后,落到列表下方空区→追加末尾。

### 4.3 方案

**新增纯函数(`src/panel/components/step_param_view.py`,与其它 order 构造器同处)**:

```python
def build_insert_block_order(n: int, selected: list[int], target: int) -> list[int]:
    """选中块(保相对顺序)整体 insert 到 ``target`` 下标之前;``target==n`` 追加末尾。

    与单元素 ``build_move_order`` 的「pop 后按下标插入」语义对齐:target 视为
    「移除选中后」的目标位。非法或空选时原序返回。
    """
    sel = sorted({s for s in selected if 0 <= s < n})
    if not sel or not (0 <= target <= n):
        return list(range(n))
    sel_set = set(sel)
    remaining = [i for i in range(n) if i not in sel_set]
    sel_before = sum(1 for s in sel if s < target)
    insert_pos = max(0, min(target - sel_before, len(remaining)))
    return remaining[:insert_pos] + sel + remaining[insert_pos:]
```

**`dropEvent` 改造(单选/多选统一,光标半行定位)**:

```python
def dropEvent(self, event):
    if event.source() is not self or not self._drag_rows:
        super().dropEvent(event)
        return
    pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
    target_item = self.itemAt(pos)
    n = self.topLevelItemCount()
    if target_item is None:
        target = n                                  # 落到所有行下方 → 追加末尾
    else:
        idx = self.indexOfTopLevelItem(target_item)
        rect = self.visualItemRect(target_item)
        target = idx + 1 if pos.y() > rect.center().y() else idx   # 下半→后 / 上半→前
    new_order = build_insert_block_order(n, self._drag_rows, target)
    self._drag_rows = []
    event.accept()
    self.reordered.emit(new_order)
```

- 单选拖拽因此获得**更精确**的半行定位:下半部匹配旧行为(行为对齐回归断言守护),上半部新增「插到该行前」,严格优于现状。
- `build_move_order` 保留不动,供「移动到序号」spinbox 路径(`_on_move_to_index`)继续使用。

### 4.4 安全性

- 核心是纯函数,完全可单测,无 GUI 依赖。
- 半行定位是 Qt 原生标准行为,可预测。
- 单选下半部 == 旧 `build_move_order` 结果(回归断言对齐),杜绝行为回退。

---

## 5. 测试与验证

| 模块 | 测试要点 |
|------|----------|
| `build_insert_block_order` | 单元素/连续块/离散块;拖到末尾(`target=n`);拖回自身块(no-op);空选;越界;「块保相对顺序」断言 |
| `format_field_value` | 7 个注册字段翻译正确;未注册字段(按键名/路径/数字/bool)保持原逻辑;空串→未设置 |
| `describe()` | 输出零变化(现有 `test_chain_model`/`test_step_param_view` 回归) |
| `field_value_i18n_key` | 命中/未命中/字段不存在 |
| i18n | zh/en 双语 key 齐全;`i18n_lint` + `lint_i18n_keys.py` 通过 |
| Qt 面板 | objectName 样式随主题刷新;详情面板按钮/输入框渲染正确(`test_qt_step_props_panel.py`) |

**测试运行约束**:Tk9 多 root 崩溃 → panel Tk 测试逐文件跑;Qt 测试 offscreen。Qt(cocoa)+Tk 不同进程。

---

## 6. 文档与变更记录

- 本设计文档:`docs/开发时SpecCoding'sPlan/动作链/02_字段i18n化与QSS根治与多选拖拽/字段i18n化与QSS根治与多选拖拽设计.md`
- 实现计划:同目录「…实现计划.md」(writing-plans 产出)
- 变更记录:`docs/变更记录文档/20260619/`(实现完成后按 AutoRecordChanges 归档)

---

## 7. 不做项(YAGNI)

- 第 4 项路径 sniff:判定可接受,不改。
- `_build_param_grid`/折叠区参数化字号样式迁全局:全局 QSS 无法表达,正确保留内联。
- `action_chain_page._build_loop_controls` 的 combo/spin 局部样式重复:超出本期 3 项范围,留待主题规范统一时处理。
- 枚举类加 `label()` 方法(方案 C):str 字段无枚举类,覆盖不全,否决。
