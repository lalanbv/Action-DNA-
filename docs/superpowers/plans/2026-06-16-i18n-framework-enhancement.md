# i18n Framework Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 增强 i18n 运行时能力(format 修复 / 可用语言列表 / locale 检测 / 复数)+ 建立 key 校验工具链(AST 扫描 + CLI + pytest gate)+ 补齐 166 处硬编码中文(logger 152 + 异常 14)。

**Architecture:** Phase 1 增强 `src/utils/i18n.py`(全部向后兼容,新增可选 `count` 参数 + 新函数)+ 新建 `src/utils/i18n_lint.py`(AST 扫描核心,增强版取代 test_i18n.py 内联逻辑)+ `scripts/lint_i18n_keys.py`(CLI)+ pytest gate。Phase 2 用 tokenize 扫描生成补齐清单,按模块分批替换 logger/异常为 `t()`,每批用 lint gate 兜底零回归。

**Tech Stack:** Python 3.11+, pytest, `ast`, `tokenize`, `argparse`, `dataclasses(frozen=True)`, `locale`。

**Spec:** [docs/superpowers/specs/2026-06-16-i18n-framework-enhancement-design.md](../specs/2026-06-16-i18n-framework-enhancement-design.md)

---

## File Structure

| 文件 | 动作 | 职责 |
|------|------|------|
| `src/utils/i18n.py` | 改 | t() 加 count + format 修复;新增 `get_available_languages` / `detect_system_locale` |
| `src/utils/i18n_lint.py` | **新建** | `LintFinding`/`LintReport` + `collect_used_keys` + `lint_i18n`(AST 扫描 + 动态前缀 + 四类对比) |
| `scripts/lint_i18n_keys.py` | **新建** | CLI(`--json`/`--strict`) |
| `scripts/gen_i18n_backfill_inventory.py` | **新建** | Phase 2 扫描硬编码中文生成清单 |
| `tests/unit/utils/test_i18n.py` | 改 | 新能力测试;移除内联 `_collect_t_keys_from_source`/`TestTranslationCompleteness`(迁至 i18n_lint) |
| `tests/unit/utils/test_i18n_lint.py` | **新建** | i18n_lint 逻辑单测 |
| `tests/unit/utils/test_i18n_keys.py` | **新建** | key gate(missing/mismatch 阻断) |
| `src/utils/translations/{zh,en}.json` | 改 | Phase 2 新增 ~166 key |
| 约 40 个调用点文件 | 改 | Phase 2 替换 logger/异常为 t() |

---

# Phase 1: 框架增强 + 工具链(严格 TDD)

## Task 1: format 错误修复(bug 级)

**Files:**
- Modify: `src/utils/i18n.py:77-97`(t 函数)
- Test: `tests/unit/utils/test_i18n.py`(新增 TestFormatError 类)

- [ ] **Step 1: 写失败测试**

在 `tests/unit/utils/test_i18n.py` 新增(文件末尾):

```python
class TestFormatError:
    """format 错误应安全降级 + 记 warning,不静默、不崩。"""

    def test_missing_kwarg_degrades_with_warning(self, caplog) -> None:
        init("zh")
        with caplog.at_level("WARNING"):
            result = t("chain.msg.profile_loaded")  # value 含 {name} 但未传 name
        assert "{name}" in result  # 返回带占位符的原文本(可见)
        assert any("format failed" in r.message for r in caplog.records)

    def test_value_error_does_not_crash(self, caplog) -> None:
        """原代码未 catch ValueError 会崩;修复后降级。"""
        init("zh")
        with caplog.at_level("WARNING"):
            result = t("app.title", name="x")  # value 无占位符,format 仍应正常
        assert result == "Action<DNA>"

    def test_successful_format_unchanged(self) -> None:
        init("zh")
        assert "test" in t("workflow.msg.profile_loaded", name="test")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/unit/utils/test_i18n.py::TestFormatError -v`
Expected: FAIL — `test_missing_kwarg_degrades_with_warning` 失败(现实现 `except (KeyError, IndexError): pass` 静默吞错,不记 warning,`caplog` 为空)

- [ ] **Step 3: 修复 t()**

Modify `src/utils/i18n.py` 的 `t` 函数(77-97 行),将:

```python
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return text
```

改为:

```python
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError, ValueError) as exc:
            # 安全降级:不崩、不静默。记录 warning + 返回带占位符的原文本(开发者可见)
            _logger.warning("i18n format failed for key %r: %s", key, exc)
    return text
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/unit/utils/test_i18n.py::TestFormatError -v`
Expected: PASS

- [ ] **Step 5: 回归全部 i18n 测试**

Run: `pytest tests/unit/utils/test_i18n.py -v`
Expected: PASS(无回归)

- [ ] **Step 6: 提交**

```bash
git add src/utils/i18n.py tests/unit/utils/test_i18n.py
git commit -m "fix(i18n): t() format errors degrade safely instead of silent swallow"
```

---

## Task 2: get_available_languages

**Files:**
- Modify: `src/utils/i18n.py`(新增公共函数,置于 `all_keys` 之后)
- Test: `tests/unit/utils/test_i18n.py`(新增 TestAvailableLanguages)

- [ ] **Step 1: 写失败测试**

```python
class TestAvailableLanguages:
    def test_returns_sorted_language_codes(self) -> None:
        langs = get_available_languages()
        assert isinstance(langs, list)
        assert "zh" in langs and "en" in langs
        assert langs == sorted(langs)  # 排序

    def test_only_json_files(self) -> None:
        langs = get_available_languages()
        assert all("." not in lang for lang in langs)  # 无扩展名残留
```

import 处加 `get_available_languages`。

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/unit/utils/test_i18n.py::TestAvailableLanguages -v`
Expected: FAIL(`ImportError: cannot import name 'get_available_languages'`)

- [ ] **Step 3: 实现**

在 `src/utils/i18n.py` 的 `all_keys()` 函数之后新增:

```python
def get_available_languages() -> list[str]:
    """返回 translations/ 目录下所有可用语言代码(如 ['en', 'zh']),排序去重。

    供设置页动态渲染语言下拉框。
    """
    if IS_FROZEN:
        base = os.path.join(getattr(sys, "_MEIPASS", ""), "src", "utils", "translations")
    else:
        base = os.path.join(os.path.dirname(__file__), "translations")
    langs: set[str] = set()
    try:
        for entry in os.listdir(base):
            if entry.endswith(".json"):
                langs.add(entry[:-5])
    except OSError:
        pass
    return sorted(langs)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/unit/utils/test_i18n.py::TestAvailableLanguages -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/utils/i18n.py tests/unit/utils/test_i18n.py
git commit -m "feat(i18n): add get_available_languages() API"
```

---

## Task 3: detect_system_locale

**Files:**
- Modify: `src/utils/i18n.py`(新增函数,置于 get_available_languages 之后)
- Test: `tests/unit/utils/test_i18n.py`(新增 TestDetectLocale)

- [ ] **Step 1: 写失败测试**

```python
class TestDetectLocale:
    def test_zh_mapping(self, monkeypatch) -> None:
        import locale as _locale
        monkeypatch.setattr(_locale, "getlocale", lambda: ("zh_CN.UTF-8", "UTF-8"))
        monkeypatch.setattr(_locale, "getdefaultlocale", lambda: ("zh_CN", "UTF-8"))
        assert detect_system_locale() == "zh"

    def test_en_mapping(self, monkeypatch) -> None:
        import locale as _locale
        monkeypatch.setattr(_locale, "getlocale", lambda: ("en_US", "UTF-8"))
        monkeypatch.setattr(_locale, "getdefaultlocale", lambda: ("en_US", None))
        assert detect_system_locale() == "en"

    def test_unknown_falls_back_to_zh(self, monkeypatch) -> None:
        import locale as _locale
        monkeypatch.setattr(_locale, "getlocale", lambda: ("ja_JP", None))
        monkeypatch.setattr(_locale, "getdefaultlocale", lambda: ("ja_JP", None))
        assert detect_system_locale() == "zh"

    def test_detection_failure_returns_default(self, monkeypatch) -> None:
        import locale as _locale
        def boom():
            raise RuntimeError("no locale")
        monkeypatch.setattr(_locale, "getlocale", boom)
        monkeypatch.setattr(_locale, "getdefaultlocale", boom)
        assert detect_system_locale() == "zh"
```

import 处加 `detect_system_locale`。

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/unit/utils/test_i18n.py::TestDetectLocale -v`
Expected: FAIL(ImportError)

- [ ] **Step 3: 实现**

在 `src/utils/i18n.py` 的 `get_available_languages()` 之后新增:

```python
def detect_system_locale() -> str:
    """检测系统首选语言,映射到支持的 i18n 语言码。

    映射规则:``zh* → zh, en* → en, 其他 → zh(默认)``。检测失败返回 ``'zh'``。
    供 init() 首次启动且 settings 未指定语言时使用。
    """
    try:
        import locale
        loc = locale.getlocale()[0]
        if not loc:
            # getdefaultlocale 在 3.11 仍可用(3.15 移除),作为 fallback
            loc = locale.getdefaultlocale()[0]  # noqa: DEPRECATED
        if loc:
            low = loc.lower()
            if low.startswith("zh"):
                return "zh"
            if low.startswith("en"):
                return "en"
    except Exception:
        pass
    return "zh"
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/unit/utils/test_i18n.py::TestDetectLocale -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/utils/i18n.py tests/unit/utils/test_i18n.py
git commit -m "feat(i18n): add detect_system_locale() with zh/en/default mapping"
```

---

## Task 4: 复数支持(pluralization)

**Files:**
- Modify: `src/utils/i18n.py:77-97`(t 函数加 `count` 参数)
- Modify: `src/utils/translations/zh.json`、`en.json`(各加 1 个测试 key,验证后保留作示例)
- Test: `tests/unit/utils/test_i18n.py`(新增 TestPlural)

- [ ] **Step 1: 写失败测试**

```python
class TestPlural:
    def test_one_for_count_1(self) -> None:
        init("en")
        # 需 en.json 提供 _test.plural.one / .other
        assert t("_test.plural", count=1) == "1 step"

    def test_other_for_count_n(self) -> None:
        init("en")
        assert t("_test.plural", count=5) == "5 steps"

    def test_zh_falls_back_to_base_key(self) -> None:
        """中文无复数,直接用基础 key(无 .one/.other)。"""
        init("zh")
        assert t("_test.plural", count=1) == "1 步"
        assert t("_test.plural", count=5) == "5 步"

    def test_count_auto_injected_into_kwargs(self) -> None:
        init("en")
        assert "{count}" not in t("_test.plural", count=3)  # 占位符已被填充

    def test_no_count_unchanged(self) -> None:
        """无 count 参数时行为与现状完全一致。"""
        init("zh")
        assert t("app.title") == "Action<DNA>"
        assert "test" in t("workflow.msg.profile_loaded", name="test")
```

import 处确认 `t` 已导入。

- [ ] **Step 2: 加测试翻译 key**

在 `src/utils/translations/zh.json`(按字母序,`_test` 在文件顶部 `action.*` 之前)加:

```json
  "_test.plural": "{count} 步",
```

在 `src/utils/translations/en.json` 对应位置加:

```json
  "_test.plural.one": "{count} step",
  "_test.plural.other": "{count} steps",
```

- [ ] **Step 3: 跑测试确认失败**

Run: `pytest tests/unit/utils/test_i18n.py::TestPlural -v`
Expected: FAIL(`test_one_for_count_1` 得到 "_test.plural" key 本身,因 t() 尚不支持复数)

- [ ] **Step 4: 实现 t() 复数**

Modify `src/utils/i18n.py` 的 `t` 函数签名与查找逻辑。将:

```python
def t(key: str, **kwargs: object) -> str:
    """获取翻译文本，支持 format 参数。

    查找顺序: 当前语言 → zh 回退 → 返回 key 本身。
    """
    if not _initialized:
        init("zh")

    with _lock:
        translations = _translations
        fallback = _fallback_translations

    text = translations.get(key)
    if text is None:
        text = fallback.get(key, key)
```

改为:

```python
def t(key: str, count: int | None = None, **kwargs: object) -> str:
    """获取翻译文本，支持 format 参数与复数。

    查找顺序:
    - count 非 None 时: ``{key}.one``/``{key}.other``(count==1 选 one)→ ``{key}`` → 回退同序 → key 本身
    - count 为 None 时: 当前语言 → zh 回退 → key 本身(与历史行为一致)

    count 非 None 时自动注入 kwargs(供 ``{count}`` 占位)。
    """
    if not _initialized:
        init("zh")

    with _lock:
        translations = _translations
        fallback = _fallback_translations

    if count is not None:
        kwargs.setdefault("count", count)
        suffix = ".one" if count == 1 else ".other"
        text = translations.get(key + suffix)
        if text is None:
            text = translations.get(key)
        if text is None:
            text = fallback.get(key + suffix)
        if text is None:
            text = fallback.get(key, key)
    else:
        text = translations.get(key)
        if text is None:
            text = fallback.get(key, key)
```

(下方的 `if kwargs: ...format...` 块已在 Task 1 修复,保持不变。)

- [ ] **Step 5: 跑测试确认通过**

Run: `pytest tests/unit/utils/test_i18n.py::TestPlural -v`
Expected: PASS

- [ ] **Step 6: 回归全部 i18n 测试**

Run: `pytest tests/unit/utils/test_i18n.py -v`
Expected: PASS

- [ ] **Step 7: 提交**

```bash
git add src/utils/i18n.py src/utils/translations/zh.json src/utils/translations/en.json tests/unit/utils/test_i18n.py
git commit -m "feat(i18n): add pluralization via count param (.one/.other suffix convention)"
```

---

## Task 5: i18n_lint.py — 数据结构 + 静态 key 收集

**Files:**
- Create: `src/utils/i18n_lint.py`
- Test: `tests/unit/utils/test_i18n_lint.py`

- [ ] **Step 1: 写失败测试**

```python
"""i18n_lint 单元测试。"""
import ast
from pathlib import Path

from src.utils.i18n_lint import (
    LintFinding,
    LintReport,
    collect_used_keys,
    _parse_imports,
    _is_i18n_call,
)


class TestParseImports:
    def test_from_import(self) -> None:
        tree = ast.parse("from src.utils.i18n import t\n")
        imp = _parse_imports(tree)
        assert "t" in imp.local_names

    def test_aliased_import(self) -> None:
        tree = ast.parse("from src.utils.i18n import t as tr\n")
        imp = _parse_imports(tree)
        assert "tr" in imp.local_names

    def test_module_import(self) -> None:
        tree = ast.parse("from src.utils import i18n\n")
        imp = _parse_imports(tree)
        assert imp.module_alias == "i18n"


class TestIsI18nCall:
    def test_direct_t(self) -> None:
        tree = ast.parse("from src.utils.i18n import t\nt('a')\n")
        imp = _parse_imports(tree)
        call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
        assert _is_i18n_call(call, imp) == "t"

    def test_module_attr_t(self) -> None:
        tree = ast.parse("from src.utils import i18n\ni18n.t('a')\n")
        imp = _parse_imports(tree)
        call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
        assert _is_i18n_call(call, imp) == "t"

    def test_non_i18n_call(self) -> None:
        tree = ast.parse("print('a')\n")
        imp = _parse_imports(tree)
        call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
        assert _is_i18n_call(call, imp) is None


class TestCollectStaticKeys:
    def test_collects_static_keys(self, tmp_path) -> None:
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "a.py").write_text(
            "from src.utils.i18n import t\n"
            "from src.utils import i18n\n"
            "t('static.one')\n"
            "i18n.t('static.two')\n"
            "t('static.three', name='x')\n"
            "schedule_validation('static.four', 'ctx')\n",
            encoding="utf-8",
        )
        used, prefixes, dynamic = collect_used_keys(tmp_path)
        assert used == {"static.one", "static.two", "static.three", "static.four"}
        assert prefixes == set()
        assert dynamic == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/unit/utils/test_i18n_lint.py -v`
Expected: FAIL(ImportError: No module named src.utils.i18n_lint)

- [ ] **Step 3: 实现 i18n_lint.py(静态部分)**

Create `src/utils/i18n_lint.py`:

```python
"""i18n key 校验 — AST 扫描 t() 调用,对比翻译 json,报告缺失/不对齐/冗余/动态。

供 ``scripts/lint_i18n_keys.py``(CLI)与 ``tests/unit/utils/test_i18n_keys.py``(pytest gate)共用。
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from pathlib import Path

# i18n 函数名(跟踪 import 后的本地绑定)
_I18N_FUNCS = frozenset({"t", "schedule_validation", "has_key"})


@dataclass(frozen=True)
class LintFinding:
    """一条校验记录。"""

    severity: str  # "missing" | "mismatch" | "redundant" | "dynamic"
    key: str
    detail: str
    location: str | None = None  # "file:line"(dynamic 用)


@dataclass(frozen=True)
class LintReport:
    """校验报告。has_errors 为真表示有阻断级问题(missing/mismatch)。"""

    missing: list[LintFinding] = field(default_factory=list)
    mismatch: list[LintFinding] = field(default_factory=list)
    redundant: list[LintFinding] = field(default_factory=list)
    dynamic: list[LintFinding] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return bool(self.missing or self.mismatch)


@dataclass
class _FileImports:
    """文件级 i18n 调用名跟踪(由 _parse_imports 填充)。"""

    local_names: set[str] = field(default_factory=set)  # 本地绑定为 i18n 函数的名
    module_alias: str | None = None  # from src.utils import i18n → "i18n"


def _parse_imports(tree: ast.AST) -> _FileImports:
    """解析文件 import,识别 i18n 函数的本地绑定。"""
    imp = _FileImports()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in _I18N_FUNCS:
                    imp.local_names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.endswith("i18n"):
                    imp.module_alias = alias.asname or alias.name
    return imp


def _is_i18n_call(call: ast.Call, imp: _FileImports) -> str | None:
    """若 call 是 i18n 函数调用,返回函数名;否则 None。"""
    func = call.func
    if isinstance(func, ast.Name) and func.id in imp.local_names:
        return func.id
    if (isinstance(func, ast.Attribute) and func.attr in _I18N_FUNCS
            and isinstance(func.value, ast.Name)
            and imp.module_alias and func.value.id == imp.module_alias):
        return func.attr
    return None


def _extract_key_arg(arg: ast.AST) -> tuple[str | None, str | None]:
    """从调用第一参数提取 (静态 key) 或 (动态前缀)。均为 None 则无法解析。"""
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value, None
    if isinstance(arg, ast.JoinedStr):  # f-string:提取首变量前的静态前缀
        prefix_parts: list[str] = []
        for val in arg.values:
            if isinstance(val, ast.Constant) and isinstance(val.value, str):
                prefix_parts.append(val.value)
            else:
                break
        if prefix_parts:
            return None, "".join(prefix_parts)
    return None, None


def collect_used_keys(src_root: Path) -> tuple[set[str], set[str], list[LintFinding]]:
    """AST 扫描 src_root,返回 (静态 keys, 动态前缀, dynamic findings)。

    排除 translations/ 与 __pycache__/。
    """
    used: set[str] = set()
    prefixes: set[str] = set()
    dynamic: list[LintFinding] = []
    for py in sorted(src_root.rglob("*.py")):
        if any(part in {"translations", "__pycache__"} for part in py.parts):
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (SyntaxError, OSError):
            continue
        imp = _parse_imports(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fname = _is_i18n_call(node, imp)
            if fname is None or not node.args:
                continue
            static, prefix = _extract_key_arg(node.args[0])
            if static is not None:
                used.add(static)
            elif prefix is not None:
                prefixes.add(prefix)
                dynamic.append(LintFinding(
                    "dynamic", prefix, f"动态 key 前缀(调用 {fname})", f"{py}:{node.lineno}"))
            else:
                dynamic.append(LintFinding(
                    "dynamic", "", f"无法解析的 {fname}() 参数", f"{py}:{node.lineno}"))
    return used, prefixes, dynamic
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/unit/utils/test_i18n_lint.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/utils/i18n_lint.py tests/unit/utils/test_i18n_lint.py
git commit -m "feat(i18n): add i18n_lint core (data structures + AST key collection)"
```

---

## Task 6: i18n_lint.py — 动态前缀豁免 + 对比 + lint_i18n

**Files:**
- Modify: `src/utils/i18n_lint.py`(新增 `_load_keys` + `lint_i18n`)
- Test: `tests/unit/utils/test_i18n_lint.py`(新增 TestLintI18n)

- [ ] **Step 1: 写失败测试**

```python
class TestLintI18n:
    def _setup(self, tmp_path, src_code, zh, en):
        src = tmp_path / "pkg"; src.mkdir()
        (src / "__init__.py").write_text("", encoding="utf-8")
        (src / "a.py").write_text(src_code, encoding="utf-8")
        trans = tmp_path / "translations"; trans.mkdir()
        (trans / "zh.json").write_text(json.dumps(zh), encoding="utf-8")
        (trans / "en.json").write_text(json.dumps(en), encoding="utf-8")
        return tmp_path / "pkg", trans

    def test_missing_detected(self, tmp_path):
        src, trans = self._setup(tmp_path,
            "from src.utils.i18n import t\nt('used.missing')\n",
            {"other.key": "x"}, {"other.key": "x"})
        r = lint_i18n(src, trans)
        assert [f.key for f in r.missing] == ["used.missing"]
        assert r.has_errors

    def test_mismatch_detected(self, tmp_path):
        src, trans = self._setup(tmp_path, "pass\n",
            {"a": "x", "b": "y"}, {"a": "x"})
        r = lint_i18n(src, trans)
        assert "b" in [f.key for f in r.mismatch]

    def test_redundant_detected(self, tmp_path):
        src, trans = self._setup(tmp_path, "pass\n",
            {"unused": "x"}, {"unused": "x"})
        r = lint_i18n(src, trans)
        assert "unused" in [f.key for f in r.redundant]
        assert not r.has_errors  # redundant 非阻断

    def test_dynamic_prefix_exempts_redundant(self, tmp_path):
        """t(f'prefix.{x}') 的前缀下所有 json key 不算 redundant。"""
        src, trans = self._setup(tmp_path,
            "from src.utils.i18n import t\nt(f'prefix.{x}')\n",  # noqa
            {"prefix.a": "x", "prefix.b": "y"}, {"prefix.a": "x", "prefix.b": "y"})
        r = lint_i18n(src, trans)
        assert r.redundant == []  # 被动态前缀豁免
        assert len(r.dynamic) == 1
```

import 顶部加:`import json` 和 `from src.utils.i18n_lint import lint_i18n`(补充到现有 import)。

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/unit/utils/test_i18n_lint.py::TestLintI18n -v`
Expected: FAIL(`lint_i18n` 未定义)

- [ ] **Step 3: 实现 lint_i18n**

在 `src/utils/i18n_lint.py` 末尾追加:

```python
def _load_keys(path: Path) -> set[str]:
    """加载 json 文件的 key 集合。失败返回空集。"""
    try:
        return set(json.loads(path.read_text(encoding="utf-8")).keys())
    except (OSError, json.JSONDecodeError):
        return set()


def lint_i18n(src_root: Path, translations_dir: Path) -> LintReport:
    """扫描 src_root + 对比 translations/{zh,en}.json,生成 LintReport。"""
    used, prefixes, dynamic = collect_used_keys(src_root)
    zh_keys = _load_keys(translations_dir / "zh.json")
    en_keys = _load_keys(translations_dir / "en.json")

    def covered_by_prefix(key: str) -> bool:
        return any(key.startswith(p) for p in prefixes)

    missing = [LintFinding("missing", k, "代码使用但 zh.json 缺失")
               for k in sorted(used - zh_keys)]
    mismatch = [LintFinding("mismatch", k, "zh/en 不对齐")
                for k in sorted(zh_keys ^ en_keys)]
    redundant = [LintFinding("redundant", k, "json 有但代码未引用(疑似)")
                 for k in sorted(zh_keys - used) if not covered_by_prefix(k)]
    return LintReport(missing, mismatch, redundant, dynamic)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/unit/utils/test_i18n_lint.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/utils/i18n_lint.py tests/unit/utils/test_i18n_lint.py
git commit -m "feat(i18n): i18n_lint four-way comparison + dynamic prefix exemption"
```

---

## Task 7: scripts/lint_i18n_keys.py CLI

**Files:**
- Create: `scripts/lint_i18n_keys.py`

- [ ] **Step 1: 实现 CLI**(风格对齐 `scripts/lint_hardcoded_ui.py`)

Create `scripts/lint_i18n_keys.py`:

```python
#!/usr/bin/env python3
"""i18n key 校验 CLI — AST 扫描 t() 对比翻译 json。

用法::

    python scripts/lint_i18n_keys.py              # 人类可读报告
    python scripts/lint_i18n_keys.py --json       # 机器可读(CI 解析)
    python scripts/lint_i18n_keys.py --strict     # redundant/dynamic 也算错

退出码:has_errors(missing/mismatch)为真 → 1;--strict 下有警告 → 1;否则 0。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.utils.i18n_lint import LintReport, lint_i18n


def _format_text(report: LintReport) -> str:
    lines: list[str] = []
    if report.has_errors:
        lines.append("❌ FAIL(有阻断级问题)")
    elif report.redundant or report.dynamic:
        lines.append("✅ OK(仅有非阻断警告)")
    else:
        lines.append("✅ OK")
    for sev in ("missing", "mismatch", "redundant", "dynamic"):
        items = getattr(report, sev)
        if items:
            lines.append(f"\n## {sev} ({len(items)})")
            for f in items:
                loc = f"  @ {f.location}" if f.location else ""
                lines.append(f"  - {f.key}: {f.detail}{loc}")
    return "\n".join(lines)


def _format_json(report: LintReport) -> str:
    data = {sev: [{"key": f.key, "detail": f.detail, "location": f.location}
                  for f in getattr(report, sev)]
            for sev in ("missing", "mismatch", "redundant", "dynamic")}
    return json.dumps(data, ensure_ascii=False, indent=2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="i18n key 校验(AST 扫描 + 翻译对比)")
    parser.add_argument("--src", default="src", help="源码根目录(默认 src)")
    parser.add_argument("--translations", default="src/utils/translations",
                        help="翻译目录(默认 src/utils/translations)")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--strict", action="store_true",
                        help="redundant/dynamic 也算错(非 0 退出)")
    args = parser.parse_args(argv)

    report = lint_i18n(Path(args.src), Path(args.translations))
    print(_format_json(report) if args.json else _format_text(report))

    if report.has_errors:
        return 1
    if args.strict and (report.redundant or report.dynamic):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: 手动验证(应通过:现有 778 key 对齐)**

Run: `python scripts/lint_i18n_keys.py`
Expected: 输出 `✅ OK`(missing=0, mismatch=0;可能有少量 dynamic/redundant 警告——若 dynamic 有 `action_type.` 等前缀被正确豁免,则 redundant 也应为空或极少)

- [ ] **Step 3: 验证 --json 输出**

Run: `python scripts/lint_i18n_keys.py --json | python -m json.tool > /dev/null && echo OK`
Expected: `OK`(合法 JSON)

- [ ] **Step 4: 提交**

```bash
git add scripts/lint_i18n_keys.py
git commit -m "feat(i18n): add lint_i18n_keys CLI (--json/--strict)"
```

---

## Task 8: pytest gate + 迁移 test_i18n.py 内联 AST(DRY)

**Files:**
- Create: `tests/unit/utils/test_i18n_keys.py`
- Modify: `tests/unit/utils/test_i18n.py`(移除内联 `_collect_t_keys_from_source` / `_load_translations` / `src_keys`/`zh_keys`/`en_keys` fixture / `TestTranslationCompleteness`,因被 i18n_lint + test_i18n_keys 取代)

- [ ] **Step 1: 创建 gate 测试**

Create `tests/unit/utils/test_i18n_keys.py`:

```python
"""i18n key gate — 真实 src + translations 下零缺失、零不对齐。

missing/mismatch 阻断(防腐化);redundant/dynamic 不阻断(信息性)。
"""
from pathlib import Path

from src.utils.i18n_lint import lint_i18n

_SRC = Path("src")
_TRANS = Path("src/utils/translations")


def test_no_missing_keys() -> None:
    report = lint_i18n(_SRC, _TRANS)
    assert not report.missing, \
        "缺失 key(代码用但 json 无): " + ", ".join(f.key for f in report.missing)


def test_no_mismatched_keys() -> None:
    report = lint_i18n(_SRC, _TRANS)
    assert not report.mismatch, \
        "zh/en 不对齐: " + ", ".join(f.key for f in report.mismatch)
```

- [ ] **Step 2: 跑 gate(应通过)**

Run: `pytest tests/unit/utils/test_i18n_keys.py -v`
Expected: PASS

- [ ] **Step 3: 迁移 test_i18n.py(移除内联 AST,DRY)**

在 `tests/unit/utils/test_i18n.py` 中**删除**:
- `import ast`(若仅用于此)与 `import json`(若仅用于此)
- `_collect_t_keys_from_source` 函数(96-114 行)
- `_load_translations` 函数(117-120 行)
- `_SRC_KEYS`/`_ZH_KEYS`/`_EN_KEYS` 模块全局(123-125 行)
- `src_keys`/`zh_keys`/`en_keys` fixture(128-149 行)
- `TestTranslationCompleteness` 类(152-165 行)

这些职责已由 `src/utils/i18n_lint.py` + `test_i18n_keys.py` 取代(且更强:识别 i18n.t/别名/schedule_validation + 动态前缀豁免)。

- [ ] **Step 4: 跑全部 i18n 测试确认无回归**

Run: `pytest tests/unit/utils/test_i18n.py tests/unit/utils/test_i18n_keys.py tests/unit/utils/test_i18n_lint.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add tests/unit/utils/test_i18n_keys.py tests/unit/utils/test_i18n.py
git commit -m "test(i18n): add key gate; remove inlined AST from test_i18n (DRY via i18n_lint)"
```

---

# Phase 2: 补齐 166 处硬编码中文

## Task 9: 补齐清单扫描脚本 + 生成 inventory

**Files:**
- Create: `scripts/gen_i18n_backfill_inventory.py`
- Generate: `docs/superpowers/plans/i18n-backfill-inventory.md`(运行产物,不入库或入 .gitignore)

- [ ] **Step 1: 实现扫描脚本**

Create `scripts/gen_i18n_backfill_inventory.py`:

```python
#!/usr/bin/env python3
"""扫描源码硬编码中文(logger/异常),生成 i18n 补齐清单(markdown)。

供 Phase 2 补齐工作提供精确清单(file:line + 字符串 + 分类)。
排除:注释、docstring、translations/、i18n.py。

用法::

    python scripts/gen_i18n_backfill_inventory.py > docs/superpowers/plans/i18n-backfill-inventory.md
"""

from __future__ import annotations

import io
import re
import tokenize
from pathlib import Path

_CN = re.compile(r"[一-鿿]")
_SKIP = {"translations", "__pycache__"}
_LOG_METHODS = (".info", ".warning", ".error", ".debug", ".exception", ".critical")


def scan(root: Path) -> list[tuple[str, int, str, str]]:
    """返回 [(file, line, kind, source_text)],kind ∈ {'logger','exception'}。"""
    items: list[tuple[str, int, str, str]] = []
    for py in sorted(root.rglob("*.py")):
        if any(part in _SKIP for part in py.parts) or py.name == "i18n.py":
            continue
        src = py.read_text(encoding="utf-8")
        lines = src.splitlines()
        try:
            toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
        except tokenize.TokenError:
            continue
        for tok in toks:
            if tok.type != tokenize.STRING or not _CN.search(tok.string):
                continue
            srow = tok.start[0]
            line = lines[srow - 1] if srow - 1 < len(lines) else ""
            if '"""' in line or "'''" in line:  # 跳过 docstring
                continue
            stripped = line.strip()
            if "logger" in line and any(m in line for m in _LOG_METHODS):
                items.append((str(py), srow, "logger", stripped))
            elif "raise " in line or re.search(r"\b\w+(Error|Exception)\(", line):
                items.append((str(py), srow, "exception", stripped))
    return items


def main() -> None:
    items = scan(Path("src"))
    by_file: dict[str, list[tuple[int, str, str]]] = {}
    for f, lineno, kind, text in items:
        by_file.setdefault(f, []).append((lineno, kind, text))
    print(f"# i18n 补齐清单({len(items)} 处)\n")
    print("| 模块 | logger | 异常 |")
    print("|------|--------|------|")
    # 模块汇总省略,直接按文件列出
    print()
    for f in sorted(by_file):
        rows = by_file[f]
        log_n = sum(1 for _, k, _ in rows if k == "logger")
        exc_n = sum(1 for _, k, _ in rows if k == "exception")
        print(f"## `{f}` (logger {log_n} + 异常 {exc_n})\n")
        for lineno, kind, text in sorted(rows):
            print(f"- L{lineno} [{kind}] `{text}`")
        print()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 生成清单**

Run: `python scripts/gen_i18n_backfill_inventory.py > docs/superpowers/plans/i18n-backfill-inventory.md`
Expected: 生成清单,头部显示 `# i18n 补齐清单(166 处)`(logger 152 + 异常 14)。

- [ ] **Step 3: 提交脚本**

```bash
git add scripts/gen_i18n_backfill_inventory.py
git commit -m "feat(i18n): add backfill inventory scanner script"
```

---

## Task 10: 补齐协议(统一 before/after 代码模板)

本 Task 不改代码,确立后续 Task 11-18 的统一处理协议。处理每个模块时严格遵循。

### 协议 A:logger(单参数)

**Before:**
```python
logger.info("调度状态已保存到 %s", target)
```
**After:**
```python
logger.info(t("scheduler.log.state_saved", target=target))
```
**zh.json:** `"scheduler.log.state_saved": "调度状态已保存到 {target}"`
**en.json:** `"scheduler.log.state_saved": "Schedule state saved to {target}"`

### 协议 B:logger(多参数)

**Before:**
```python
logger.info("从 %s 加载了 %d 个调度", target, count)
```
**After:**
```python
logger.info(t("scheduler.log.loaded", target=target, count=count))
```
**zh.json:** `"scheduler.log.loaded": "从 {target} 加载了 {count} 个调度"`
**en.json:** `"scheduler.log.loaded": "Loaded {count} schedule(s) from {target}"`

### 协议 C:异常

**Before:**
```python
raise ValueError("缺少必需字段 'action_type'")
```
**After:**
```python
raise ValueError(t("serialization.exc.missing_field", field="action_type"))
```
**zh.json:** `"serialization.exc.missing_field": "缺少必需字段 '{field}'"`
**en.json:** `"serialization.exc.missing_field": "Missing required field '{field}'"`

### 每个模块 Task 的统一步骤(模板)

1. 查 `docs/superpowers/plans/i18n-backfill-inventory.md` 该模块小节,逐处按协议 A/B/C 转换
2. 为每处生成 key:`<module>.log.<verb>`(logger)或 `<module>.exc.<verb>`(异常),verb 用英文动词
3. zh.json/en.json 按**字母序**插入新 key(保持排序);占位符用语义化名(`target`/`count`/`error`/`field`,非 `arg0`)
4. 文件顶部若无 `from src.utils.i18n import t` 则补 import
5. 跑 `python scripts/lint_i18n_keys.py` 确认 missing=0
6. 跑该模块相关测试(若存在)确认无回归
7. 提交:`feat(i18n): internationalize <module> logs/exceptions`

### 复数场景(本计划 logger/异常通常无需,但若遇 "{n} 个")

若 logger 文本含计数且英文需单复数,用 Task 4 的复数约定:`<key>.one`/`<key>.other`(en) + `<key>`(zh),调用 `t(key, count=n)`。

---

## Task 11: 补齐 src/core/engine(40 logger + 2 异常)

**Files:**
- Modify: `src/core/engine/` 下含中文 logger/异常的文件(见 inventory;典型:graph_engine.py、fsm_engine.py、descriptors/*.py、execution_context.py 等)
- Modify: `src/utils/translations/{zh,en}.json`

- [ ] **Step 1**: 查 inventory 的 `src/core/engine` 小节(40 logger + 2 异常),逐处按 Task 10 协议转换
- [ ] **Step 2**: zh/en.json 插入新 key(命名空间 `engine.log.*` / `engine.exc.*`,按字母序)
- [ ] **Step 3**: 跑 `python scripts/lint_i18n_keys.py`,确认 missing=0
- [ ] **Step 4**: 跑 `pytest tests/unit/core/engine/ -v`(若存在)确认无回归
- [ ] **Step 5**: 提交

```bash
git add src/core/engine src/utils/translations/zh.json src/utils/translations/en.json
git commit -m "feat(i18n): internationalize src/core/engine logs/exceptions"
```

---

## Task 12: 补齐 src/core/plugins(19 logger + 3 异常)

**Files:** `src/core/plugins/`(plugin_loader.py、plugin_context.py、plugin_node_registry.py 等)、translations

- [ ] **Step 1**: 查 inventory `src/core/plugins` 小节(19 logger + 3 异常),按协议转换(命名空间 `plugins.log.*` / `plugins.exc.*`)
- [ ] **Step 2**: zh/en.json 插入新 key(字母序)
- [ ] **Step 3**: `python scripts/lint_i18n_keys.py` → missing=0
- [ ] **Step 4**: `pytest tests/unit/core/plugins/ -v`(若存在)无回归
- [ ] **Step 5**: 提交 `feat(i18n): internationalize src/core/plugins logs/exceptions`

---

## Task 13: 补齐 src/core/debug(12 logger)

**Files:** `src/core/debug/`(debugger.py、breakpoint_manager.py、ring_buffer_log.py)、translations

- [ ] **Step 1**: 查 inventory `src/core/debug` 小节(12 logger),按协议转换(`debug.log.*`)
- [ ] **Step 2**: zh/en.json 插入
- [ ] **Step 3**: lint missing=0
- [ ] **Step 4**: `pytest tests/unit/core/debug/ -v`(若存在)无回归
- [ ] **Step 5**: 提交 `feat(i18n): internationalize src/core/debug logs`

---

## Task 14: 补齐 src/core/input(11 logger)

**Files:** `src/core/input/`(hotkey_manager.py、global_hotkey_backend.py)、`src/core/input_controller.py`(若 logger 在此)、translations

- [ ] **Step 1**: 查 inventory `src/core/input` 小节(11 logger),按协议转换(`input.log.*`——注意 zh.json 已有部分 `input.log.*` key,新 key 不得重复)
- [ ] **Step 2**: zh/en.json 插入(去重:复用现有同语义 key)
- [ ] **Step 3**: lint missing=0
- [ ] **Step 4**: `pytest tests/unit/core/input/ -v`(若存在)无回归
- [ ] **Step 5**: 提交 `feat(i18n): internationalize src/core/input logs`

---

## Task 15: 补齐 src/recorder(10 logger)

**Files:** `src/recorder/recorder.py`、`src/recorder/event_merger.py`、translations

- [ ] **Step 1**: 查 inventory `src/recorder` 小节(10 logger),按协议转换(`recorder.log.*`)
- [ ] **Step 2**: zh/en.json 插入
- [ ] **Step 3**: lint missing=0
- [ ] **Step 4**: `pytest tests/unit/recorder/ -v`(若存在)无回归
- [ ] **Step 5**: 提交 `feat(i18n): internationalize src/recorder logs`

---

## Task 16: 补齐 src/core/layers + src/core/variables(16 logger + 2 异常)

**Files:** `src/core/layers/`(retry_layer.py、timing_layer.py 等,含 2 异常)、`src/core/variables/`(pool.py、scope.py 等)、translations

- [ ] **Step 1**: 查 inventory `src/core/layers`(8 logger + 2 异常)与 `src/core/variables`(8 logger),按协议转换(`layers.log.*`/`layers.exc.*`/`variables.log.*`)
- [ ] **Step 2**: zh/en.json 插入
- [ ] **Step 3**: lint missing=0
- [ ] **Step 4**: `pytest tests/unit/core/layers/ tests/unit/core/variables/ -v`(若存在)无回归
- [ ] **Step 5**: 提交 `feat(i18n): internationalize src/core/layers + variables`

---

## Task 17: 补齐 src/core/vision + src/plugins/builtin + src/core/editor(17 logger + 2 异常)

**Files:** `src/core/vision/`(7 logger + 2 异常)、`src/plugins/builtin/`(6 logger)、`src/core/editor/`(4 logger)、translations

- [ ] **Step 1**: 查 inventory 三小节(vision 7+2、builtin 6、editor 4),按协议转换(`vision.log.*`/`vision.exc.*`/`plugins.builtin.log.*`/`editor.log.*`——复用现有 `vision.log.*` key 去重)
- [ ] **Step 2**: zh/en.json 插入(去重)
- [ ] **Step 3**: lint missing=0
- [ ] **Step 4**: 相关测试无回归
- [ ] **Step 5**: 提交 `feat(i18n): internationalize vision + builtin plugins + editor`

---

## Task 18: 补齐 panel + 剩余小模块(全部剩余 logger + 7 异常)

**Files:** `src/panel/`(app.py 5、pages 3、controllers 3 logger + 3 异常、qt_backend 4、backend_selector 1)、`src/core/`(config 4、safe_eval 3、io 1 logger + 1 异常、events 1、serialization 1 异常)、`src/utils/restart.py`(1 logger)、translations

- [ ] **Step 1**: 查 inventory 剩余全部小节,按协议转换(panel 用 `panel.log.*`/`panel.exc.*`,config 用 `config.log.*` 等)
- [ ] **Step 2**: zh/en.json 插入(去重:复用现有 `panel.*`/`config.*` 同语义 key)
- [ ] **Step 3**: lint missing=0 + mismatch=0
- [ ] **Step 4**: `pytest tests/unit/panel/ -v` 无回归
- [ ] **Step 5**: 提交 `feat(i18n): internationalize panel + remaining modules`

---

## Task 19: 收尾验证

**Files:** 无(纯验证)

- [ ] **Step 1: key gate 通过**

Run: `pytest tests/unit/utils/test_i18n_keys.py -v`
Expected: PASS(missing=0, mismatch=0)

- [ ] **Step 2: CLI 全量校验**

Run: `python scripts/lint_i18n_keys.py`
Expected: `✅ OK`

- [ ] **Step 3: 硬编码中文归零验证**

Run:
```bash
python3 - <<'EOF'
import sys
from pathlib import Path
sys.path.insert(0, ".")
from scripts.gen_i18n_backfill_inventory import scan
items = scan(Path("src"))
print(f"剩余硬编码中文(logger/异常): {len(items)}")
assert not items, f"仍有 {len(items)} 处未补齐"
print("✅ 归零")
EOF
```
Expected: `剩余硬编码中文(logger/异常): 0` + `✅ 归零`

- [ ] **Step 4: 全量测试套件**

Run: `pytest tests/ -q`
Expected: 全部 PASS(无回归)

- [ ] **Step 5: 覆盖率检查**

Run: `pytest --cov=src/utils/i18n --cov=src/utils/i18n_lint --cov-report=term-missing tests/unit/utils/`
Expected: `i18n.py` / `i18n_lint.py` 覆盖率 ≥ 80%

- [ ] **Step 6: 清理 inventory 产物**

```bash
rm -f docs/superpowers/plans/i18n-backfill-inventory.md
```

- [ ] **Step 7: 总结提交(若有未提交的收尾改动)**

```bash
git add -A
git commit -m "chore(i18n): phase 2 backfill complete — 166 hardcoded strings internationalized"
```

---

## 完成标准(对应 spec §10)

- [ ] i18n.py 4 项能力(format 修复 / 可用语言列表 / locale 检测 / 复数)+ 单测通过
- [ ] i18n_lint.py(扫描 / 对比 / 动态前缀)+ 单测通过
- [ ] lint_i18n_keys.py CLI(--json / --strict)可用
- [ ] pytest gate 通过(missing=0, mismatch=0)
- [ ] 166 处硬编码中文全部补齐
- [ ] tokenize 复扫硬编码中文归零
- [ ] 全量测试套件通过
- [ ] 现有 778 key 与 t() 调用行为不变
- [ ] 核心模块覆盖率 ≥ 80%
