"""OCR 文字识别器 — rapidocr 集成 + 优雅降级"""

import logging
import threading
from difflib import SequenceMatcher

import numpy as np

from src.core.vision.ocr_result import OCRResult, OCRMultiResult

logger = logging.getLogger(__name__)

# 模块级可用性标志，外部可快速检查 OCR 是否可用
try:
    from rapidocr_onnxruntime import RapidOCR

    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False


class OCRRecognizer:
    """OCR 文字识别器。

    使用 rapidocr-onnxruntime 进行文字检测和识别。
    支持：
    - 预定义 ROI（Region of Interest）的文字识别
    - 模糊文本匹配（处理 OCR 噪声）
    - 数值提取（HP、金币等）
    - 多行文本识别
    - 优雅降级：rapidocr 未安装时 OCR_AVAILABLE=False，所有方法安全返回空结果
    """

    def __init__(self) -> None:
        self._engine: RapidOCR | None = None
        self._roi_presets: dict[str, tuple[int, int, int, int]] = {}
        self._initialized = False
        self._init_lock = threading.Lock()

    def _ensure_initialized(self) -> None:
        """懒初始化 OCR 引擎（线程安全，双重检查锁定）"""
        if self._initialized:
            return
        with self._init_lock:
            if self._initialized:
                return
            if not OCR_AVAILABLE:
                logger.warning(
                    "rapidocr-onnxruntime 未安装，OCR 功能不可用。"
                    "安装命令: pip install rapidocr-onnxruntime"
                )
                self._initialized = True
                return
            try:
                self._engine = RapidOCR()
                logger.info("OCR 引擎初始化成功 (rapidocr-onnxruntime)")
            except Exception as e:
                logger.error("OCR 引擎初始化失败: %s", e)
            finally:
                self._initialized = True

    # ---- ROI 管理 ----

    def register_roi(self, name: str, region: tuple[int, int, int, int]) -> None:
        """注册预定义 ROI。

        参数：
            name:   ROI 名称，如 "hp", "gold", "quest_text"
            region: 区域 (x, y, w, h)
        """
        self._roi_presets[name] = region

    def get_roi(self, name: str) -> tuple[int, int, int, int] | None:
        """获取预定义 ROI"""
        return self._roi_presets.get(name)

    # ---- 识别接口 ----

    def recognize(
        self,
        screenshot: np.ndarray,
        region: tuple[int, int, int, int] | None = None,
    ) -> OCRMultiResult:
        """对截图进行 OCR 识别。

        参数：
            screenshot: 截图 (H, W, 3) BGR
            region:     识别区域 (x, y, w, h)，None 表示全图

        返回：
            OCRMultiResult — 包含所有识别出的文本行
        """
        self._ensure_initialized()

        if self._engine is None:
            return OCRMultiResult.empty()

        # 裁剪区域
        image = screenshot
        if region:
            x, y, w, h = region
            x = max(0, x)
            y = max(0, y)
            y2 = min(y + h, screenshot.shape[0])
            x2 = min(x + w, screenshot.shape[1])
            image = screenshot[y:y2, x:x2]

        # 执行 OCR
        try:
            results, _ = self._engine(image)
        except Exception as e:
            logger.error("OCR 识别失败: %s", e)
            return OCRMultiResult.empty()

        if results is None:
            return OCRMultiResult.empty()

        # 转换为 OCRResult
        ocr_results: list[OCRResult] = []
        for item in results:
            box_points, text, confidence = item
            xs = [p[0] for p in box_points]
            ys = [p[1] for p in box_points]
            bx = int(min(xs))
            by = int(min(ys))
            bw = int(max(xs) - bx)
            bh = int(max(ys) - by)

            if region:
                bx += region[0]
                by += region[1]

            ocr_results.append(OCRResult(
                text=text,
                confidence=float(confidence),
                bounding_box=(bx, by, bw, bh),
                raw_box=tuple(tuple(int(p) for p in pt) for pt in box_points),
            ))

        return OCRMultiResult.from_list(ocr_results)

    def recognize_roi(
        self,
        screenshot: np.ndarray,
        roi_name: str,
    ) -> OCRMultiResult:
        """使用预定义 ROI 进行 OCR。"""
        region = self._roi_presets.get(roi_name)
        if region is None:
            logger.warning("未注册的 ROI: '%s'", roi_name)
            return OCRMultiResult.empty()
        return self.recognize(screenshot, region)

    def extract_number(
        self,
        screenshot: np.ndarray,
        region: tuple[int, int, int, int],
    ) -> int | None:
        """从指定区域提取数字（适用于 HP、金币等数值读取）。"""
        result = self.recognize(screenshot, region)

        for ocr_item in result.results:
            digits = "".join(c for c in ocr_item.text if c.isdigit() or c in ",.-")
            if not digits:
                continue

            # 移除千分位逗号
            digits = digits.replace(",", "")

            # 小数点：取整数部分（"12,500" → "12500"，"3.14" → "3"）
            dot_pos = digits.find(".")
            if dot_pos >= 0:
                digits = digits[:dot_pos]

            if not digits or digits == "-":
                continue

            try:
                return int(digits)
            except ValueError:
                continue

        return None

    def find_text(
        self,
        screenshot: np.ndarray,
        target_text: str,
        region: tuple[int, int, int, int] | None = None,
        fuzzy_threshold: float = 0.6,
    ) -> OCRResult | None:
        """在截图中搜索指定文本，支持模糊匹配。"""
        result = self.recognize(screenshot, region)

        best_match: OCRResult | None = None
        best_ratio = 0.0

        for ocr_item in result.results:
            if target_text in ocr_item.text:
                return ocr_item

            ratio = SequenceMatcher(None, target_text, ocr_item.text).ratio()
            if ratio > best_ratio and ratio >= fuzzy_threshold:
                best_ratio = ratio
                best_match = ocr_item

        return best_match

    def find_text_position(
        self,
        screenshot: np.ndarray,
        target_text: str,
        region: tuple[int, int, int, int] | None = None,
    ) -> tuple[int, int] | None:
        """在截图中搜索文本并返回其中心位置。"""
        result = self.find_text(screenshot, target_text, region)
        if result is None:
            return None
        x, y, w, h = result.bounding_box
        return (x + w // 2, y + h // 2)
