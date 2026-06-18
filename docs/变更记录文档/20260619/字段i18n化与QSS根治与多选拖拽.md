# 字段 i18n 化与 QSS 根治与多选拖拽

- 日期:2026-06-19
- 范围:01 期「步骤详情与快速重排」review 遗留 4 项的根治(第 4 项已由 01 期完成,跳过)
- 关联设计:`docs/开发时SpecCoding'sPlan/动作链/02_字段i18n化与QSS根治与多选拖拽/`

## 背景

01 期收尾 `/simplify` 标记 4 项超出当次 scope 的遗留:枚举/模式字段绕过 i18n、三个 `_xxx_style` helper 重复、Qt 多选拖拽只移首行、路径 sniff。其中第 4 项 01 期已用字段名判断(`_PATH_FIELD_SUFFIXES`)完成且更优;本期处理前 3 项。执行中发现工作区已有 01 期在途改动(`_control_qss` 合并、`build_block_insert_order` 多选块、`_semantic_label` 2 字段翻译),本期在其上补全到「最正规」。

## 改动

### Item 1 — 枚举/模式字段 i18n 化(单一事实源)

**问题**:`format_field_value` 对 Enum 返回 `.name`、对模式 str 返回原值,绕过 i18n;且 `describe()` 内与 `step_param_view` 内各存一份翻译表(双份维护)。

**修复**:
- `src/core/step_types.py`:新增模块级 `_FIELD_VALUE_I18N` 注册表(7 字段:found_action/detect_mode/match_strategy/threshold_mode/combo_mode/button/color_mode)+ 纯函数 `field_value_i18n_key(field_name, raw) -> str | None`。`ClickImageStep.describe`/`KeyComboStep.describe` 改引用之(删局部 `fa_keys`/`mode_map`,行为保持)。
- `src/panel/components/step_param_view.py`:`format_field_value` 改查 `field_value_i18n_key`;删除 `_FOUND_ACTION_KEYS`/`_COMBO_MODE_KEYS`/`_semantic_label`(消除双份维护)。覆盖由 2 字段扩到 7 字段。保留 `_PATH_FIELD_SUFFIXES` 字段名路径判断(Item 4)。
- i18n:`button` 复用既有 `dialog.btn.left/right/middle`(DRY);新增 `dialog.color_mode.hsv/rgb`(zh/en 各 2 key)。
- 效果:`describe()` 与字段表共用同一注册表,Qt/tk 双框架同受益。

### Item 2 — QSS 根治(objectName + 全局 QSS)

**问题**:`QtActionChainPropsMixin` 用局部 `setStyleSheet`(01 期已把 3 helper 合并为 `_control_qss`,但仍局部样式),不符 objectName + 全局 QSS 约定。

**修复**:
- `src/panel/qt_backend/theme.py`:全局 QSS 新增 3 条 objectName 规则:`QLineEdit#dnaDetailInput, QSpinBox#dnaDetailInput`、`QPushButton#dnaDetailBtn`、`QPushButton#dnaDeleteBtn`(随主题自动刷新)。
- `src/panel/qt_backend/pages/action_chain_props_mixin.py`:4 处调用点改 `setObjectName`,删除 `_control_qss` 方法。
- 边界:`_build_param_grid`/折叠区的参数化字号样式保留内联(全局 QSS 无法表达按调用变化的 `font_px`)。

### Item 3 — Qt 多选拖拽(半行精确定位 + 末尾追加)

**问题**:01 期已用 `build_block_insert_order` 修复多选块(核心已不再只移首行),但无半行定位,且落到列表下方插到最后行前(非追加末尾)。

**修复**:
- `src/panel/components/step_param_view.py`:`build_block_insert_order` guard 放宽 `0 <= target <= n`(支持 `target=n` 追加末尾);新增纯函数 `drop_insert_target(target_idx, click_below_center, n)`(Qt 原生指示线语义:上半→前、下半→后、落空→n)。
- `src/panel/qt_backend/pages/action_chain_page.py`:`dropEvent` 用光标在目标行的纵向位置决定 target,单选/多选统一走 `build_block_insert_order`。

### Item 4 — 路径 sniff

01 期已完成(`_PATH_FIELD_SUFFIXES` 字段名判断),本期保留不动。

## 影响文件

| 文件 | 改动 |
|------|------|
| `src/core/step_types.py` | +`_FIELD_VALUE_I18N`/`field_value_i18n_key`;重构 2 个 `describe()` |
| `src/panel/components/step_param_view.py` | `format_field_value` 接入注册表;删 `_semantic_label`+2 dict;`build_block_insert_order` 放宽;+`drop_insert_target` |
| `src/panel/qt_backend/theme.py` | +3 条 objectName 全局 QSS |
| `src/panel/qt_backend/pages/action_chain_props_mixin.py` | 4 处 setObjectName;删 `_control_qss` |
| `src/panel/qt_backend/pages/action_chain_page.py` | `dropEvent` 半行定位;+`drop_insert_target` 导入 |
| `src/utils/translations/{zh,en}.json` | +`dialog.color_mode.hsv/rgb` |
| `tests/unit/core/test_step_types_field_labels.py` | 新建(注册表 + describe 回归) |
| `tests/unit/panel/test_step_param_view.py` | +7 字段翻译断言、+append/drop_insert_target 断言 |
| `tests/unit/panel/qt/test_qt_step_props_panel.py` | +dropEvent inspect 冒烟、+objectName 断言 |

## 测试

- `tests/unit/core/`(含新 `test_step_types_field_labels.py`):**1976 passed**(describe 零变化回归)。
- `tests/unit/panel/test_step_param_view.py`:39 passed(含 7 字段 i18n、append、drop_insert_target)。
- `tests/unit/panel/qt/`(offscreen):**73 passed**(含 dropEvent inspect、objectName)。
- `tests/unit/panel/test_step_property_panel_tk.py`:3 passed(tk 侧共用 format_field_value)。
- i18n:`lint_i18n_keys.py` exit 0;`test_i18n*` gate 全过。
- mypy:改动纯 python 文件(step_types/step_param_view)`Success: no issues`。(全量 mypy 被 `pixel_search_descriptor.py:86` 预存 type 注释语法错误阻塞,与本次无关。)

## 风险与回滚

- Item 1 为行为保持重构:`describe()` 输出零变化,1976 core 测试守护;字段表显示由裸值变 i18n 标签(预期改进)。
- Item 2 视觉等价(同色/同 padding/同字号);objectName 特异性高于类型选择器,不影响其它 widget。
- Item 3 单选拖拽行为微调(新增上半→前、末尾追加),为标准 Qt 行为;`build_move_order` 保留不动供「移动到序号」spinbox。
- 回滚:`git checkout` 上述文件即可;无数据/配置迁移。

## 不做项

- 第 4 项路径 sniff:01 期已完成,保留。
- `_build_param_grid`/折叠区参数化字号迁全局 QSS:全局 QSS 无法表达,正确保留内联。
- `_toolbar_btn_style`(action_chain_page 工具栏):非 Item 2 范围,不动。
