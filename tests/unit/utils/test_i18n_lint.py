"""i18n_lint 单元测试。"""
import ast
import json
from pathlib import Path

from src.utils.i18n_lint import (
    LintFinding,
    LintReport,
    collect_used_keys,
    lint_i18n,
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

    def test_plural_asymmetry_not_mismatch(self, tmp_path):
        """复数变体:en .one/.other vs zh base 不算 mismatch。"""
        src, trans = self._setup(tmp_path, "pass\n",
            {"_test.plural": "{count} 步"},
            {"_test.plural.one": "{count} step", "_test.plural.other": "{count} steps"})
        r = lint_i18n(src, trans)
        plural_findings = [f for f in r.mismatch if f.key.startswith("_test.plural")]
        assert plural_findings == []  # 复数不对称豁免
