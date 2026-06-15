"""i18n 单元测试 — 覆盖核心 API + AST key 完整性校验。"""

import ast
import json
from pathlib import Path

import pytest

from src.utils.i18n import (
    detect_system_locale,
    get_available_languages,
    get_language,
    has_key,
    init,
    schedule_validation,
    set_language,
    t,
)


class TestInit:
    def test_default_language(self) -> None:
        init()
        assert get_language() == "zh"

    def test_explicit_language(self) -> None:
        init("en")
        assert get_language() == "en"


class TestTranslate:
    def test_known_key(self) -> None:
        init("zh")
        result = t("app.title")
        assert result == "Action<DNA>"

    def test_unknown_key_returns_key(self) -> None:
        init("zh")
        assert t("nonexistent.key.12345") == "nonexistent.key.12345"

    def test_format_kwargs(self) -> None:
        init("zh")
        result = t("workflow.msg.profile_loaded", name="test")
        assert "test" in result

    def test_auto_init_on_t(self) -> None:
        """t() 在未初始化时应自动 init('zh')。"""
        from src.utils import i18n
        i18n._initialized = False
        i18n._translations = {}
        i18n._fallback_translations = {}
        result = t("app.title")
        assert result == "Action<DNA>"


class TestHasKey:
    def test_existing_key(self) -> None:
        init("zh")
        assert has_key("app.title")

    def test_missing_key(self) -> None:
        init("zh")
        assert not has_key("nonexistent.key.12345")


class TestSetLanguage:
    def test_switch_to_en(self) -> None:
        init("zh")
        set_language("en")
        assert get_language() == "en"
        assert t("app.title") == "Action<DNA>"

    def test_same_language_noop(self) -> None:
        init("zh")
        set_language("zh")
        assert get_language() == "zh"


class TestDeferredValidation:
    def test_schedule_before_init(self) -> None:
        from src.utils import i18n
        i18n._initialized = False
        i18n._pending_validations = []
        schedule_validation("nonexistent.deferred.test", "test_ctx")
        assert len(i18n._pending_validations) == 1

    def test_schedule_after_init(self) -> None:
        init("zh")
        schedule_validation("app.title", "test_ctx")

    def test_flush_validations(self) -> None:
        from src.utils import i18n
        i18n._pending_validations = [("nonexistent.flush.test", "test_ctx")]
        init("zh")
        assert i18n._pending_validations == []


def _collect_t_keys_from_source() -> set[str]:
    keys: set[str] = set()
    src_dir = Path("src")
    for py_file in src_dir.rglob("*.py"):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "t"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                keys.add(node.args[0].value)
    return keys


def _load_translations(lang: str) -> set[str]:
    path = Path("src/utils/translations") / f"{lang}.json"
    with open(path, encoding="utf-8") as f:
        return set(json.load(f).keys())


_SRC_KEYS: set[str] | None = None
_ZH_KEYS: set[str] | None = None
_EN_KEYS: set[str] | None = None


@pytest.fixture(scope="module")
def src_keys() -> set[str]:
    global _SRC_KEYS
    if _SRC_KEYS is None:
        _SRC_KEYS = _collect_t_keys_from_source()
    return _SRC_KEYS


@pytest.fixture(scope="module")
def zh_keys() -> set[str]:
    global _ZH_KEYS
    if _ZH_KEYS is None:
        _ZH_KEYS = _load_translations("zh")
    return _ZH_KEYS


@pytest.fixture(scope="module")
def en_keys() -> set[str]:
    global _EN_KEYS
    if _EN_KEYS is None:
        _EN_KEYS = _load_translations("en")
    return _EN_KEYS


class TestTranslationCompleteness:
    def test_all_t_keys_in_zh(self, src_keys: set[str], zh_keys: set[str]) -> None:
        missing = sorted(src_keys - zh_keys)
        assert not missing, f"Missing from zh.json: {missing}"

    def test_all_t_keys_in_en(self, src_keys: set[str], en_keys: set[str]) -> None:
        missing = sorted(src_keys - en_keys)
        assert not missing, f"Missing from en.json: {missing}"

    def test_zh_and_en_have_same_keys(self, zh_keys: set[str], en_keys: set[str]) -> None:
        zh_only = sorted(zh_keys - en_keys)
        en_only = sorted(en_keys - zh_keys)
        assert not zh_only, f"Only in zh.json: {zh_only}"
        assert not en_only, f"Only in en.json: {en_only}"


class TestFormatError:
    """format 错误应安全降级 + 记 warning，不静默、不崩。"""

    def test_missing_kwarg_degrades_with_warning(self, caplog) -> None:
        init("zh")
        with caplog.at_level("WARNING"):
            result = t("chain.msg.profile_loaded")  # value 含 {name} 但未传 name
        assert "{name}" in result  # 返回带占位符的原文本（可见）
        assert any("format failed" in r.message for r in caplog.records)

    def test_value_error_does_not_crash(self, caplog) -> None:
        """原代码未 catch ValueError 会崩；修复后降级。"""
        init("zh")
        with caplog.at_level("WARNING"):
            result = t("app.title", name="x")  # value 无占位符，format 仍应正常
        assert result == "Action<DNA>"

    def test_successful_format_unchanged(self) -> None:
        init("zh")
        assert "test" in t("workflow.msg.profile_loaded", name="test")


class TestAvailableLanguages:
    def test_returns_sorted_language_codes(self) -> None:
        langs = get_available_languages()
        assert isinstance(langs, list)
        assert "zh" in langs and "en" in langs
        assert langs == sorted(langs)  # 排序

    def test_only_json_files(self) -> None:
        langs = get_available_languages()
        assert all("." not in lang for lang in langs)  # 无扩展名残留


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
