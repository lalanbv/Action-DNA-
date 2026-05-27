"""OCRResult / OCRMultiResult 单元测试。

覆盖: empty()、best 属性、find_text() 模糊/精确匹配。
"""

from src.core.vision.ocr_result import OCRMultiResult, OCRResult


def _make_result(text: str, confidence: float = 0.9) -> OCRResult:
    return OCRResult(text=text, confidence=confidence, bounding_box=(10, 20, 80, 30))


# ============================================================
# OCRResult
# ============================================================


class TestOCRResult:
    def test_empty(self):
        r = OCRResult.empty()
        assert r.text == ""
        assert r.confidence == 0.0
        assert r.bounding_box == (0, 0, 0, 0)

    def test_frozen(self):
        r = _make_result("hello")
        try:
            r.text = "changed"
            assert False, "should be frozen"
        except AttributeError:
            pass


# ============================================================
# OCRMultiResult.empty
# ============================================================


class TestOCRMultiResultEmpty:
    def test_empty_has_no_results(self):
        m = OCRMultiResult.empty()
        assert m.results == ()
        assert m.texts == []

    def test_empty_best_is_none(self):
        m = OCRMultiResult.empty()
        assert m.best is None

    def test_empty_find_text_returns_none(self):
        m = OCRMultiResult.empty()
        assert m.find_text("anything") is None


# ============================================================
# OCRMultiResult.best
# ============================================================


class TestOCRMultiResultBest:
    def test_best_returns_highest_confidence(self):
        m = OCRMultiResult.from_list([
            _make_result("low", 0.5),
            _make_result("high", 0.95),
            _make_result("mid", 0.7),
        ])
        assert m.best is not None
        assert m.best.text == "high"
        assert m.best.confidence == 0.95

    def test_best_single_result(self):
        r = _make_result("only", 0.8)
        m = OCRMultiResult.from_list([r])
        assert m.best == r


# ============================================================
# OCRMultiResult.find_text
# ============================================================


class TestOCRMultiResultFindText:
    def test_fuzzy_match_found(self):
        m = OCRMultiResult.from_list([
            _make_result("开始游戏"),
            _make_result("设置"),
        ])
        result = m.find_text("开始", fuzzy=True)
        assert result is not None
        assert result.text == "开始游戏"

    def test_fuzzy_match_not_found(self):
        m = OCRMultiResult.from_list([_make_result("退出")])
        assert m.find_text("开始", fuzzy=True) is None

    def test_exact_match_found(self):
        m = OCRMultiResult.from_list([
            _make_result("开始游戏"),
            _make_result("开始"),
        ])
        result = m.find_text("开始", fuzzy=False)
        assert result is not None
        assert result.text == "开始"

    def test_exact_match_not_found_when_only_partial(self):
        m = OCRMultiResult.from_list([_make_result("开始游戏")])
        result = m.find_text("开始", fuzzy=False)
        assert result is None

    def test_find_text_returns_first_match(self):
        m = OCRMultiResult.from_list([
            _make_result("第一行开始"),
            _make_result("第二行开始"),
        ])
        result = m.find_text("开始", fuzzy=True)
        assert result.text == "第一行开始"

    def test_texts_property(self):
        m = OCRMultiResult.from_list([
            _make_result("A"),
            _make_result("B"),
        ])
        assert m.texts == ["A", "B"]
