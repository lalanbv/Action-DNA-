"""可组合视觉检测管线"""

import hashlib
import logging
import threading
import time
from abc import ABC, abstractmethod
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np

from src.core.vision.ocr_result import OCRMultiResult
from src.core.vision.pixel_result import PixelSearchResult
from src.utils.float_utils import is_one

logger = logging.getLogger(__name__)


def compute_image_hash(image: np.ndarray) -> int:
    """快速截图哈希 — 降采样均值量化 + C 级哈希。

    使用步幅降采样（每 32 行/列取一块），量化到 8 级灰度，
    对轻微像素变化鲁棒。被 VisionCache 和 TemplateMatcher 共用。

    使用 xxhash 风格的 hashlib 替代纯 Python FNV-1a 循环，
    确定性且利用 C 实现，比逐字节 Python 循环快数十倍。
    """
    h, w = image.shape[:2]
    step_h = max(1, h // 32)
    step_w = max(1, w // 32)
    small = image[::step_h, ::step_w]
    vals = (small.mean(axis=-1) * 0.03125).astype(np.int32) if small.ndim == 3 else (small * 0.03125).astype(np.int32)
    return int.from_bytes(hashlib.xxh3_64(vals.tobytes()).digest(), "little")


class VisionCache:
    """截图哈希 → 检测结果的 TTL 缓存。

    使用降采样 + 均值量化快速哈希，容忍轻微像素变化。
    适用于同一画面反复检测同一目标的场景。
    """

    def __init__(self, ttl_ms: int = 200, max_entries: int = 50) -> None:
        self._ttl_ms = ttl_ms
        self._max_entries = max_entries
        self._cache: OrderedDict[int, tuple[float, dict[str, Any]]] = OrderedDict()
        self._lock = threading.Lock()

    def get(
        self, image: np.ndarray,
    ) -> tuple[int, dict[str, Any]] | tuple[int, None]:
        """查找缓存。返回 (key, result)；未命中或过期时 result 为 None。"""
        key = compute_image_hash(image)
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return key, None
            ts, result = entry
            if (time.monotonic() - ts) * 1000 > self._ttl_ms:
                del self._cache[key]
                return key, None
            self._cache.move_to_end(key)
            return key, result

    def put(self, key: int, result: dict[str, Any]) -> None:
        """存入缓存。超出容量时淘汰最旧的条目。"""
        with self._lock:
            self._cache[key] = (time.monotonic(), result)
            self._cache.move_to_end(key)
            while len(self._cache) > self._max_entries:
                self._cache.popitem(last=False)

    def invalidate(self) -> None:
        """清空缓存。"""
        with self._lock:
            self._cache.clear()


@dataclass(frozen=True)
class VisionOutput:
    """视觉管线输出（不可变）— 汇总管线中所有步骤的检测结果。"""

    success: bool
    primary_result: Any | None = None
    template_result: Any | None = None
    pixel_result: PixelSearchResult | None = None
    ocr_result: OCRMultiResult | None = None
    metadata: dict[str, Any] | None = None


class VisionStep(ABC):
    """视觉检测步骤抽象基类"""

    @abstractmethod
    def execute(
        self,
        screenshot: np.ndarray,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """执行检测步骤。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """步骤名称"""


class PreprocessStep(VisionStep):
    """图像预处理步骤 — 去噪/锐化/对比度增强/二值化。

    插入到 VisionPipeline 中，在模板匹配之前使用可提高匹配率。
    所有处理可选开启，默认全部关闭。
    """

    def __init__(
        self,
        *,
        denoise: bool = False,
        sharpen: bool = False,
        threshold: bool = False,
        threshold_value: int = 127,
        adaptive_threshold: bool = False,
        contrast_enhance: bool = False,
    ) -> None:
        self._denoise = denoise
        self._sharpen = sharpen
        self._threshold = threshold
        self._threshold_value = threshold_value
        self._adaptive_threshold = adaptive_threshold
        self._contrast_enhance = contrast_enhance

    @property
    def name(self) -> str:
        return "preprocess"

    def execute(self, screenshot: np.ndarray, context: dict) -> dict:
        from src.core.vision._cv2_guard import cv2

        needs_color_ops = self._denoise or self._sharpen or self._contrast_enhance

        if self._threshold:
            gray = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
            if self._adaptive_threshold:
                processed = cv2.adaptiveThreshold(
                    gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                    cv2.THRESH_BINARY, 11, 2,
                )
                processed = cv2.cvtColor(processed, cv2.COLOR_GRAY2BGR)
            else:
                _, binary = cv2.threshold(gray, self._threshold_value, 255, cv2.THRESH_BINARY)
                processed = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
        elif needs_color_ops:
            processed = screenshot.copy()
        else:
            processed = screenshot

        if self._denoise:
            processed = cv2.fastNlMeansDenoisingColored(processed, None, 10, 10, 7, 21)

        if self._sharpen:
            kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
            processed = cv2.filter2D(processed, -1, kernel)

        if self._contrast_enhance:
            processed = cv2.convertScaleAbs(processed, alpha=1.2, beta=10)

        out = {**context}
        out["preprocessed_image"] = processed
        out["_preprocessed"] = True
        return out


def _make_template_result(
    x: int, y: int, w: int, h: int, **extra: Any,
) -> dict[str, Any]:
    return {
        "found": True,
        "x": x, "y": y, "w": w, "h": h,
        "center": (x + w // 2, y + h // 2),
        "region": (x, y, w, h),
        **extra,
    }


_NOT_FOUND: dict[str, Any] = {"found": False}

_default_matcher: Any = None


def _get_default_matcher() -> Any:
    """模块级懒加载 TemplateMatcher 单例，避免每次执行创建新实例。"""
    global _default_matcher
    if _default_matcher is None:
        from src.core.vision import TemplateMatcher
        _default_matcher = TemplateMatcher()
    return _default_matcher


class TemplateMatchStep(VisionStep):
    """模板匹配步骤 — 支持多尺度搜索。

    scales=None 时使用原始尺度（兼容现有行为）。
    scales=[0.8, 0.9, 1.0, 1.1, 1.2] 时在多个缩放下搜索，
    取最佳匹配结果。
    """

    def __init__(
        self,
        template_path: str,
        threshold: float = 0.8,
        region: tuple[int, int, int, int] | None = None,
        scales: list[float] | None = None,
        alt_template_paths: list[str] | None = None,
        match_strategy: "MatchStrategy | None" = None,
    ) -> None:
        self._template_path = template_path
        self._threshold = threshold
        self._region = region
        self._scales = scales
        # 多模板备用图(任一命中即视为找到);为空则走单模板/多尺度原路径(向后兼容)
        self._alt_template_paths = list(alt_template_paths) if alt_template_paths else []
        # 多模板编排策略;None → 默认 ADAPTIVE(在 _execute_multi 内归一)
        self._match_strategy = match_strategy

    @property
    def name(self) -> str:
        return "template_match"

    def execute(self, screenshot: np.ndarray, context: dict) -> dict:
        matcher = context.get("_matcher")
        if matcher is None:
            logger.warning("VisionPipeline 上下文缺少 _matcher，使用模块级懒加载实例")
            matcher = _get_default_matcher()

        # 多模板:任一命中即视为找到(向后兼容:无 alt 时走单模板/多尺度原路径)
        if self._alt_template_paths:
            return self._execute_multi(screenshot, context, matcher)

        if self._scales is None:
            result = matcher.find(
                screen=screenshot,
                template_path=self._template_path,
                threshold=self._threshold,
            )
            out = {**context}
            if result is not None:
                x, y, w, h = result
                out["template_result"] = _make_template_result(x, y, w, h)
            else:
                out["template_result"] = _NOT_FOUND
            out["last_match"] = out["template_result"]
            return out

        return self._execute_multiscale(screenshot, context, matcher)

    def _execute_multi(self, screenshot: np.ndarray, context: dict, matcher: Any) -> dict:
        """多模板匹配:主图 + 备用图 OR 匹配,命中即返回其位置。

        在原始尺度匹配(不与多尺度叠加;符合规格 §7.1"多模板时走 find_any")。
        """
        from src.core.action import MatchStrategy, ThresholdMode
        from src.core.vision.match_config import resolve_find_any_params

        strategy = self._match_strategy if self._match_strategy is not None else MatchStrategy.ADAPTIVE
        paths, per_thr, resolved_strategy = resolve_find_any_params(
            primary_path=self._template_path,
            alt_paths=self._alt_template_paths,
            base_threshold=self._threshold,
            alt_thresholds=[None] * len(self._alt_template_paths),
            threshold_mode=ThresholdMode.GLOBAL,
            match_strategy=strategy,
        )
        out = {**context}
        if not paths:
            out["template_result"] = _NOT_FOUND
            out["last_match"] = _NOT_FOUND
            return out
        result = matcher.find_any(
            screenshot, paths,
            threshold=self._threshold,
            strategy=resolved_strategy,
            per_template_thresholds=per_thr,
        )
        if result is not None:
            x, y, w, h = result.rect
            out["template_result"] = _make_template_result(x, y, w, h)
        else:
            out["template_result"] = _NOT_FOUND
        out["last_match"] = out["template_result"]
        return out

    def _execute_multiscale(
        self,
        screenshot: np.ndarray,
        context: dict,
        matcher: Any,
    ) -> dict:
        """多尺度模板匹配 — 缩放截图后在多个尺度搜索，取最佳结果。"""
        from src.core.vision._cv2_guard import cv2

        out = {**context}
        best_result = None
        best_scale = 1.0
        h_orig, w_orig = screenshot.shape[:2]

        assert self._scales is not None
        for scale in self._scales:
            if is_one(scale):
                scaled = screenshot
            else:
                new_w, new_h = int(w_orig * scale), int(h_orig * scale)
                if new_w < 1 or new_h < 1:
                    continue
                scaled = cv2.resize(screenshot, (new_w, new_h))

            result = matcher.find(
                screen=scaled,
                template_path=self._template_path,
                threshold=self._threshold,
            )
            if result is not None:
                x, y, w, h = result
                if not is_one(scale):
                    inv = 1.0 / scale
                    x, y = int(x * inv), int(y * inv)
                    w, h = int(w * inv), int(h * inv)
                best_result = (x, y, w, h)
                best_scale = scale
                break

        if best_result is not None:
            x, y, w, h = best_result
            out["template_result"] = _make_template_result(
                x, y, w, h, match_scale=best_scale,
            )
        else:
            out["template_result"] = _NOT_FOUND
        out["last_match"] = out["template_result"]
        return out


class PixelSearchStep(VisionStep):
    """像素搜索步骤"""

    def __init__(
        self,
        target_color: tuple[int, int, int],
        tolerance: int = 10,
        region: tuple[int, int, int, int] | None = None,
    ) -> None:
        self._target_color = target_color
        self._tolerance = tolerance
        self._region = region

    @property
    def name(self) -> str:
        return "pixel_search"

    def execute(self, screenshot: np.ndarray, context: dict) -> dict:
        from src.core.vision.pixel_searcher import PixelSearcher

        searcher = context.get("_searcher", PixelSearcher())
        result = searcher.search(
            screenshot=screenshot,
            target_color=self._target_color,
            tolerance=self._tolerance,
            region=self._region,
        )
        out = {**context, "pixel_result": result, "last_search": result}
        return out


class OCRStep(VisionStep):
    """OCR 文字识别步骤"""

    def __init__(
        self,
        region: tuple[int, int, int, int] | None = None,
        target_text: str | None = None,
    ) -> None:
        self._region = region
        self._target_text = target_text

    @property
    def name(self) -> str:
        return "ocr"

    def execute(self, screenshot: np.ndarray, context: dict) -> dict:
        from src.core.vision.ocr_recognizer import OCRRecognizer

        recognizer = context.get("_recognizer", OCRRecognizer())
        result = recognizer.recognize(screenshot, region=self._region)

        out = {**context}
        if self._target_text:
            matched = result.find_text(self._target_text)
            if matched:
                out["ocr_result"] = OCRMultiResult.from_list([matched])
            else:
                out["ocr_result"] = OCRMultiResult.empty()
        else:
            out["ocr_result"] = result

        out["last_ocr"] = out["ocr_result"]
        return out


class VisionPipeline:
    """可组合视觉检测管线。

    将多个 VisionStep 串联执行，每步的输出作为下一步的输入。
    支持：
    - 顺序执行：Step1 -> Step2 -> Step3
    - 条件跳过：某步失败后跳过后续步骤
    - 缓存：对同一截图缓存检测结果（可选）

    使用方式：
        pipeline = VisionPipeline()
        pipeline.add_step(TemplateMatchStep("enemy.png", threshold=0.8))
        pipeline.add_step(PixelSearchStep((0, 200, 0), tolerance=15))
        pipeline.add_step(OCRStep(region=(100, 50, 200, 30)))
        output = pipeline.execute(screenshot)
    """

    def __init__(
        self,
        stop_on_failure: bool = False,
        cache_ttl_ms: int = 0,
        on_stage_begin: Callable[[str], None] | None = None,
        on_stage_end: Callable[[str, float], None] | None = None,
        on_stage_error: Callable[[str, Exception], None] | None = None,
    ) -> None:
        self._steps: list[VisionStep] = []
        self._stop_on_failure = stop_on_failure
        self._cache: VisionCache | None = None
        self._on_stage_begin = on_stage_begin
        self._on_stage_end = on_stage_end
        self._on_stage_error = on_stage_error
        if cache_ttl_ms > 0:
            self._cache = VisionCache(ttl_ms=cache_ttl_ms)

    def add_step(self, step: VisionStep) -> "VisionPipeline":
        """添加检测步骤（链式调用）"""
        self._steps.append(step)
        return self

    def clear_steps(self) -> None:
        """清空所有步骤"""
        self._steps.clear()

    def execute(
        self,
        screenshot: np.ndarray,
        shared_services: dict[str, Any] | None = None,
    ) -> VisionOutput:
        """执行管线。

        参数：
            screenshot:      截图
            shared_services: 共享服务实例（"_matcher", "_searcher", "_recognizer"）

        返回：
            VisionOutput — 汇总所有步骤的检测结果
        """
        # 缓存查找
        cache_key: int | None = None
        if self._cache is not None:
            cache_key, cached = self._cache.get(screenshot)
            if cached is not None:
                return VisionOutput(
                    success=cached.get("success", False),
                    primary_result=cached.get("primary_result"),
                    template_result=cached.get("template_result"),
                    pixel_result=cached.get("pixel_result"),
                    ocr_result=cached.get("ocr_result"),
                    metadata=cached.get("metadata"),
                )

        context: dict[str, Any] = {}
        if shared_services:
            context.update(shared_services)

        template_result = None
        pixel_result: PixelSearchResult | None = None
        ocr_result: OCRMultiResult | None = None

        for step in self._steps:
            t0 = time.monotonic()
            try:
                if self._on_stage_begin:
                    self._on_stage_begin(step.name)

                # 如果有预处理结果，传递预处理图像给后续步骤
                working_image = context.get("preprocessed_image", screenshot)
                context = step.execute(working_image, context)

                if "template_result" in context:
                    template_result = context["template_result"]
                if "pixel_result" in context:
                    pixel_result = context["pixel_result"]
                if "ocr_result" in context:
                    ocr_result = context["ocr_result"]

                elapsed_ms = (time.monotonic() - t0) * 1000
                if self._on_stage_end:
                    self._on_stage_end(step.name, elapsed_ms)

                if self._stop_on_failure:
                    last = context.get("last_match")
                    if isinstance(last, dict) and not last.get("found", True):
                        break
                    last_pxl = context.get("last_search")
                    if isinstance(last_pxl, PixelSearchResult) and not last_pxl.found:
                        break
                    last_ocr = context.get("last_ocr")
                    if isinstance(last_ocr, OCRMultiResult) and not last_ocr.results:
                        break

            except Exception as e:
                elapsed_ms = (time.monotonic() - t0) * 1000
                logger.error("管线步骤 '%s' 执行失败 (%.1fms): %s", step.name, elapsed_ms, e)
                if self._on_stage_error:
                    self._on_stage_error(step.name, e)
                if self._stop_on_failure:
                    break

        primary = None
        tpl_found = isinstance(template_result, dict) and template_result.get("found", False)
        pxl_found = pixel_result is not None and pixel_result.found
        ocr_found = ocr_result is not None and len(ocr_result.results) > 0

        if tpl_found:
            primary = template_result
        elif pxl_found:
            primary = pixel_result
        elif ocr_found:
            primary = ocr_result.best

        success = tpl_found or pxl_found or ocr_found

        output = VisionOutput(
            success=success,
            primary_result=primary,
            template_result=template_result,
            pixel_result=pixel_result,
            ocr_result=ocr_result,
            metadata=context.get("_metadata"),
        )

        # 缓存存储
        if self._cache is not None and cache_key is not None:
            self._cache.put(cache_key, {
                "success": success,
                "primary_result": primary,
                "template_result": template_result,
                "pixel_result": pixel_result,
                "ocr_result": ocr_result,
                "metadata": context.get("_metadata"),
            })

        return output
