"""OCR 识别结果数据结构"""

from dataclasses import dataclass


@dataclass(frozen=True)
class OCRResult:
    """OCR 单行识别结果（不可变）"""

    text: str
    confidence: float
    bounding_box: tuple[int, int, int, int]  # (x, y, w, h)
    raw_box: tuple[tuple[int, int], ...] = ()  # 原始四角坐标

    @classmethod
    def empty(cls) -> "OCRResult":
        return cls(text="", confidence=0.0, bounding_box=(0, 0, 0, 0))


@dataclass(frozen=True)
class OCRMultiResult:
    """多行 OCR 识别结果（不可变）"""

    results: tuple[OCRResult, ...]

    @classmethod
    def empty(cls) -> "OCRMultiResult":
        return cls(results=())

    @classmethod
    def from_list(cls, results: list[OCRResult]) -> "OCRMultiResult":
        return cls(results=tuple(results))

    @property
    def texts(self) -> list[str]:
        """所有识别文本"""
        return [r.text for r in self.results]

    @property
    def best(self) -> OCRResult | None:
        """置信度最高的结果"""
        if not self.results:
            return None
        return max(self.results, key=lambda r: r.confidence)

    def find_text(self, keyword: str, fuzzy: bool = True) -> OCRResult | None:
        """查找包含关键词的识别结果。

        参数：
            keyword: 搜索关键词
            fuzzy:   是否模糊匹配（包含即可）
        """
        for result in self.results:
            if fuzzy:
                if keyword in result.text:
                    return result
            else:
                if result.text == keyword:
                    return result
        return None
