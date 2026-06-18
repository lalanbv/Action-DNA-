# mypy 类型注释语法阻断修复（pixel_search 描述符）

**日期**: 2026-06-19
**类型**: fix (工具链)
**影响范围**: `src/core/engine/descriptors/pixel_search_descriptor.py` — mypy 静态检查工具链

## 问题描述

运行项目配置的 mypy（`[tool.mypy]`）时，对任意文件检查都会**立即崩溃中断**：

```
src/core/engine/descriptors/pixel_search_descriptor.py:86: error:
  Syntax error in type comment "PixelSearchStep  — 由 action_type() 约束"  [syntax]
Found 1 error in 1 file (errors prevented further checking)
```

该语法错误发生在被间接导入的依赖文件里，导致 mypy 无法构建类型信息、**中止对全部目标文件的检查**——整个静态类型门失效。

## 根因

`pixel_search_descriptor.py:86` 使用了畸形的 PEP 484 类型注释：

```python
step = action  # type: PixelSearchStep  — 由 action_type() 约束
```

`# type:` 注释**必须恰好是 `# type: 类型名`**，注释后不能跟任何额外文字。中文说明「 — 由 action_type() 约束」被 mypy 当成类型表达式的一部分解析 → 语法错误。

且 `PixelSearchStep` 在该文件**完全未导入**（连 `TYPE_CHECKING` 块都没有），即便语法修对仍会报「未定义名」。

`pixel_search_descriptor.py` 是**全仓库唯一**用 `# type:` 注释做类型收窄的描述符——其余描述符（`extended_descriptors.py` 等 8 处）一律用 `cast(SpecificStep, action)`。

## 修复

对齐代码库既定模式（`extended_descriptors.py` 的 `cast()` 用法）：

```python
# 顶部运行时导入（cast 实参在运行时求值，必须运行时可用）
from typing import TYPE_CHECKING, cast
from src.core.step_types import PixelSearchStep
...
step = cast(PixelSearchStep, action)  # action_type() 约束保证此处为 PixelSearchStep
```

### 过程中的坑（记录供后续避雷）

首版误将 `PixelSearchStep` 放进 `if TYPE_CHECKING:` 块 → 5 个 pixel search 测试 `NameError`。
**原因**：`from __future__ import annotations` 只延迟**注解**（函数签名 / 变量注解），**不延迟 `cast()` 的实参**——`cast(PixelSearchStep, x)` 的首个参数在运行时求值，故被收窄的类型必须是**运行时导入**（非 `TYPE_CHECKING`）。`extended_descriptors.py` 正是把 step 类型放在运行时导入、只把 `ExecutionContext` 放 `TYPE_CHECKING`。

## 验证

- `test_pixel_search_descriptor.py`：**12/12 过**（含 HSV/BGR/preset 搜索 + 无颜色失败用例）
- mypy 对该文件：**0 错误**
- core 全套：**2001/2001 过**（无连带回归）

## 收尾时附带发现（未处理，留作决策）

mypy 解阻后暴露 **66 个预存类型警告**跨 5 文件（mixin `attr-defined` / Optional `union-attr` 等），经核查**全是预存模式、0 个来自本轮重构、非 bug**（测试 100% 绿），且项目 mypy 配置非严格（`ignore_missing_imports=true`、无 `strict`）。已与用户确认：留作后续独立「类型硬化」任务，不在本次范围。
