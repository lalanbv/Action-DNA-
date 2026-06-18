# 跳过项落地 — Qt Spinbox 公共 helper 提取 + 四项跳过核查

> 日期：2026-06-19
> 范围：`src/panel/qt_backend/widgets.py`（实质改动）、`src/panel/qt_backend/theme.py`（核查确认）
> 触发：上一轮 `/simplify` 末尾「附理由跳过的 4 项」，用户要求逐项落地。

## 背景

上一轮 `/simplify` 在文末列出 4 项「附理由跳过」。本轮按用户要求逐项评估并落地。结论：**仅第 1 项需要代码改动**（且找到了当初被否提案所担心的「可读性」问题的真正解法），其余 3 项经核查已处于健康/已解决状态。

## 逐项处理

### 1. `themed_doublespinbox` / `themed_spinbox` 公共 helper — 落地

**文件**：`src/panel/qt_backend/widgets.py`

**当初被否理由**：两控件共享 ~90% 的 kw-pop 结构（minimum/maximum/value/prefix/suffix/single_step/objectName 共 7 块），可抽公共 helper，但**会降低两种独立控件的可读性**，属可接受重复，不动。

**本轮改法**（化解被否理由的核心顾虑）：

被否理由成立的前提是「抽取会牺牲类型安全或可读性」。经核查该前提**不成立**——`QSpinBox`（int 重载）与 `QDoubleSpinBox`（float 重载）的 `setMinimum/setValue/setSingleStep` 签名不兼容，联合类型直接调用确会触发 mypy 报错；但 **值约束 `TypeVar` 配合 `kw.pop()` 返回 `Any`** 可干净规避（`Any` 与任意签名双向兼容，不参与签名校验），调用点仍保留 `QSpinBox`/`QDoubleSpinBox` 精确类型，**零 `type: ignore`**：

```python
_NumericSpin = TypeVar("_NumericSpin", QSpinBox, QDoubleSpinBox)

def _configure_spinbox(spin: _NumericSpin, kw: dict[str, Any]) -> _NumericSpin:
    """统一应用 QSpinBox/QDoubleSpinBox 共用 kw-pop 并返回 spin。"""
    if "minimum" in kw:
        spin.setMinimum(kw.pop("minimum"))
    # ... maximum/value/prefix/suffix/single_step/objectName 同构
    return spin
```

两控件函数各自收敛为「建控件 → 设字体 →（doublespinbox 特有：`setDecimals`）→ `_configure_spinbox`」，消除 14 行重复。`themed_doublespinbox` 的 `setDecimals` 仍**先于** `_configure_spinbox`（内含 `setValue`）调用，保留「decimals 必须先于 setValue 否则值被旧精度舍入」的原行为不变。

### 2. `theme.py` `current_theme` 未用导入 — 核查确认已清理

**文件**：`src/panel/qt_backend/theme.py`

`theme_to_qss(t: CanvasTheme)` 接收 `CanvasTheme` 作参数，`current_theme` 导入确实从未被引用。核查发现导入行已是 `from src.panel.canvas.theme import CanvasTheme`（`current_theme` 已移除，系 ruff F401 自动清理），本轮**无新增改动**，仅确认其已处于健康状态。

### 3. `step_key_fields` / `props_mixin`（240 行重写）/ i18n — 深度审查通过，无改动

对当初因「超出上下文且成本敏感」而搁置的新模块深度审查：

| 审查维度 | 结果 |
|----------|------|
| `KEY_FIELDS`（17 种 ActionType → `[(字段名, i18n_key)]`）覆盖完整性 | 全覆盖；无配置者降级为仅「全部字段」表 |
| `chain.kf.*` 键（42 个）zh/en 成对存在 | **42/42 全齐**，无缺失 |
| `chain.detail.*` / `common.*` 引用键（12 个） | 全齐 |
| `_FIELD_VALUE_I18N` 单一事实源（describe 与 format_field_value 共用） | 机制清晰，无双份维护 |
| `QtActionChainPropsMixin` 结构（_clear_props 递归释放 / move-to 闭包捕获 / collapsible 折叠区） | 设计良好，docstring 完备 |

**结论**：代码质量高，无问题，无需改动。

### 4. `pixel_search_descriptor.py` 未提交改动 — 已解决

当初列为「游离的无关改动，不在本次范围」。核查：已在 `18b3241 fix: pixel_search 描述符类型注释语法错误阻断 mypy` 提交，不再是未提交状态。**自动解决**。

## 验证

| 检查 | 结果 |
|------|------|
| mypy（`widgets.py`，聚焦改动区 115–185 行） | **改动区零报错**；仅 5 处既有错误（`QFrame.VLine`/`QFont.Bold` 等 PySide6 存根限制）在 272–313 行，非本次引入 |
| `tests/unit/panel/qt/` 全目录（73 项） | **73 passed**（含 `test_qt_widgets` 28、`test_qt_spinbox_dialog` 8、`test_qt_step_props_panel` 8、`test_theme_sync_backend` 3） |
| i18n lint 门禁 + 硬编码 UI lint 门禁 | **均 exit=0**（非阻塞）；告警行号均在本次未编辑区域，是既有噪声 |

## 净变更

实质代码改动仅 `widgets.py` 1 文件（+27 / −31），逻辑等价性由 73 个 Qt 单测兜底。`theme.py` 的 diff 为会话起始工作区状态，非本轮新增。
