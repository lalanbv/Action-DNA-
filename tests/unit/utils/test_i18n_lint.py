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
