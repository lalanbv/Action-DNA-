"""i18n 单元测试 — 覆盖核心 API。

key 完整性校验(missing/mismatch/redundant/dynamic)已由 ``src/utils/i18n_lint.py``
统一提供,pytest gate 见 ``test_i18n_keys.py``。本文件只覆盖核心运行时 API。
"""

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
