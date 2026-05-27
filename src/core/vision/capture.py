"""屏幕截图与图像识别模块"""

import os
import threading
import time
from collections import OrderedDict
from typing import NamedTuple

import mss
import numpy as np

from src.utils.platform import IS_MACOS

from src.core.vision._cv2_guard import cv2, require_cv2
from src.core.vision.buffer_pool import BufferPool
from src.core.vision.vision_pipeline import compute_image_hash
from src.core.logger import log
from src.utils.float_utils import is_one
from src.utils.i18n import t


class ScreenCapture:
    """基于 mss 的高速屏幕截图，支持锁定区域和全屏

    macOS Retina 显示器上，mss 截图返回物理像素（2x），
    而 pyautogui 操作使用逻辑像素。本类自动处理缩放转换。

    Windows 上 mss 使用线程局部 GDI 资源，因此 _sct 按线程
    惰性创建，确保后台线程调用 grab() 时不会因缺少 srcdc 而崩溃。
    """

    def __init__(self):
        require_cv2("screen capture and template matching")
        self._tls = threading.local()  # 按线程存储 mss 实例
        self._monitor = None  # None 表示全屏（虚拟屏幕）
        self._pool = BufferPool()
        self._is_fullscreen = True
        self._region_logical: tuple[int, int] | None = None  # (left, top) 逻辑像素
        self._last_monitor_key: tuple | None = None  # 缓存显示器关键尺寸
        self._last_scale_check: float = 0.0  # 上次缩放检测时间戳
        self._virtual_offset: tuple[int, int] = (0, 0)  # monitors[0] 逻辑偏移缓存
        self._scale = self._detect_scale()
        self._update_virtual_offset()
        # 截图 TTL 缓存：50ms 内复用同一截图，避免多节点重复截图
        self._last_screenshot: np.ndarray | None = None
        self._last_screenshot_time: float = 0.0
        self._last_screenshot_hash: int = 0
        self._cache_ttl: float = 0.05
        self._cache_lock = threading.Lock()  # 保护 TTL 缓存的读写
        self._closed = False  # 防止 __del__ 在解释器关闭时崩溃
        log.info(t("vision.log.scale_factor", scale=self._scale))

    @property
    def _sct(self):
        """获取当前线程的 mss 实例（Windows GDI 资源是线程局部的）

        threading.local 为每个线程提供独立槽位，无需额外锁保护。
        """
        sct = getattr(self._tls, 'sct', None)
        if sct is None:
            sct = mss.mss()
            self._tls.sct = sct
        return sct

    def _detect_scale(self) -> float:
        """检测缩放因子：mss 截图像素 / 逻辑像素（pyautogui 坐标）

        macOS + mss 10.x：mss 返回逻辑像素，scale = 1.0
        macOS + mss <10 ：mss 返回物理像素，scale = backingScaleFactor (2.0)
        Windows：mss 返回物理像素，scale = DPI/96

        使用主显示器的 NSScreen.backingScaleFactor（macOS）
        或 CGDisplayMode 物理像素宽度（Quartz fallback）
        或 pyautogui 逻辑尺寸（其他平台）来确定 mss 返回的是物理还是逻辑像素。
        """
        try:
            scale = self._detect_scale_macos()
            if scale is not None:
                return scale
        except Exception as e:
            log.debug(t("vision.log.scale_detect_failed", error=e))

        # 非 macOS 回退：比较 mss 尺寸与 pyautogui 逻辑尺寸
        try:
            import pyautogui
            monitors = self._sct.monitors
            # 主显示器是 monitors[1]（如果存在多个显示器），否则是 monitors[0]
            primary = monitors[1] if len(monitors) > 1 else monitors[0]
            primary_mss_w = primary["width"]
            logical_w = pyautogui.size()[0]
            if logical_w > 0 and primary_mss_w > 0:
                scale = round(primary_mss_w / logical_w, 1)
                if scale > 0.5:
                    return scale
        except Exception as e:
            log.debug(t("vision.log.scale_detect_failed", error=e))
        return 1.0

    def _detect_scale_macos(self) -> float | None:
        """macOS 专用缩放检测 — 直接获取 backingScaleFactor。

        使用 NSScreen（最可靠），回退到 Quartz CGDisplayMode 比较物理/逻辑像素。
        """
        if not IS_MACOS:
            return None

        # 方法 1：NSScreen — 比较 mss 宽度与屏幕逻辑宽度
        try:
            from AppKit import NSScreen
            main_screen = NSScreen.mainScreen()
            mss_w = self._sct.monitors[1]["width"] if len(self._sct.monitors) > 1 else self._sct.monitors[0]["width"]
            screen_frame = main_screen.frame()
            logical_w = int(screen_frame.size.width)
            if logical_w > 0:
                return round(mss_w / logical_w, 1)
        except Exception:
            pass

        # 方法 2：Quartz CGDisplayMode — 比较模式点宽度与 mss 宽度
        try:
            import Quartz
            main_display = Quartz.CGMainDisplayID()
            mode = Quartz.CGDisplayCopyDisplayMode(main_display)
            if mode:
                point_w = Quartz.CGDisplayModeGetWidth(mode)
                if point_w > 0:
                    mss_w = self._sct.monitors[1]["width"] if len(self._sct.monitors) > 1 else self._sct.monitors[0]["width"]
                    return round(mss_w / point_w, 1)
        except Exception:
            pass

        return None

    def _refresh_scale(self) -> None:
        """检查显示器配置是否变化，变化则重新检测缩放因子（节流：最多每 30s 检查一次）

        仅在显示器配置实际变化时才关闭/重建 mss 实例，避免不必要的资源释放
        导致瞬时的 grab() 失败。
        """
        now = time.monotonic()
        if now - self._last_scale_check < 30.0:
            return
        self._last_scale_check = now
        try:
            monitors = self._sct.monitors
            key = tuple(
                (m.get("left", 0), m.get("top", 0), m.get("width"), m.get("height"))
                for m in monitors
            )
            if key != self._last_monitor_key:
                # 显示器配置变化 — 需要重建 mss 并重新检测缩放
                if hasattr(self._tls, 'sct') and self._tls.sct is not None:
                    self._tls.sct.close()
                    self._tls.sct = None
                old_scale = self._scale
                self._scale = self._detect_scale()
                self._last_monitor_key = key
                if self._scale != old_scale:
                    log.info(t("vision.log.scale_updated", old=old_scale, new=self._scale))
                self._update_virtual_offset()
        except Exception as e:
            log.debug(t("vision.log.refresh_failed", error=e))

    def _update_virtual_offset(self) -> None:
        """缓存虚拟屏幕左上角的逻辑偏移，全屏模式下同步写入 _region_logical"""
        m = self._sct.monitors[0]
        self._virtual_offset = (
            int(m.get("left", 0) / self._scale),
            int(m.get("top", 0) / self._scale),
        )
        if self._is_fullscreen:
            self._region_logical = self._virtual_offset

    @property
    def scale_factor(self) -> float:
        """物理像素到逻辑像素的缩放因子（Retina 上通常为 2.0）"""
        return self._scale

    @property
    def virtual_desktop_offset(self) -> tuple[int, int]:
        """虚拟桌面左上角的逻辑像素偏移（多显示器时可能非零）。"""
        return self._virtual_offset

    def to_logical(self, x: int, y: int) -> tuple[int, int]:
        """将截图上的物理像素坐标转换为屏幕逻辑像素坐标（pyautogui 使用逻辑坐标）"""
        lx, ly = int(x / self._scale), int(y / self._scale)
        if self._region_logical:
            lx += self._region_logical[0]
            ly += self._region_logical[1]
        return lx, ly

    def to_logical_rect(self, rect: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        """将截图上的物理像素矩形转换为屏幕逻辑像素矩形（含区域偏移）"""
        x, y, w, h = rect
        lx, ly = self.to_logical(x, y)
        lw, lh = int(w / self._scale), int(h / self._scale)
        return (lx, ly, lw, lh)

    def set_region(self, left: int, top: int, width: int, height: int) -> None:
        """设置截图区域（逻辑像素坐标），自动转换为物理像素给 mss"""
        s = self._scale
        self._monitor = {
            "left": int(left * s), "top": int(top * s),
            "width": int(width * s), "height": int(height * s),
        }
        self._region_logical = (left, top)
        self._is_fullscreen = False
        self._invalidate_cache()
        log.info(t("vision.log.region_set", left=left, top=top, width=width, height=height, scale=f"{s:.1f}"))

    def set_fullscreen(self) -> None:
        self._monitor = None
        self._is_fullscreen = True
        self._update_virtual_offset()
        self._invalidate_cache()
        log.info(t("vision.log.fullscreen"))

    def _invalidate_cache(self) -> None:
        """清除截图缓存（区域切换后立即失效，防止返回旧截图）"""
        with self._cache_lock:
            self._last_screenshot = None
            self._last_screenshot_hash = 0

    def _is_cache_valid(self) -> bool:
        """TTL 缓存是否仍有效。调用方必须持有 _cache_lock。"""
        return (
            self._last_screenshot is not None
            and time.monotonic() - self._last_screenshot_time < self._cache_ttl
        )

    def _grab_fresh(self) -> np.ndarray:
        """截取新帧并更新 TTL 缓存，返回拥有的副本。"""
        self._refresh_scale()
        monitor = self._monitor or self._sct.monitors[0]
        raw = self._pool.grab_into(self._sct, monitor)
        owned = raw.copy()
        with self._cache_lock:
            self._last_screenshot = owned
            self._last_screenshot_time = time.monotonic()
            self._last_screenshot_hash = 0
        return owned

    def get_cached_hash(self, screen: np.ndarray) -> int:
        """返回截图的哈希值，TTL 缓存命中时复用上次计算的哈希。"""
        with self._cache_lock:
            if screen is self._last_screenshot and self._last_screenshot_hash != 0:
                return self._last_screenshot_hash
        h = compute_image_hash(screen)
        with self._cache_lock:
            if screen is self._last_screenshot:
                self._last_screenshot_hash = h
        return h

    def grab(self, force: bool = False) -> np.ndarray:
        """截取屏幕，返回 BGR numpy 数组（可安全存储）

        使用 BufferPool 预分配缓冲区减少 GC 压力，返回副本确保安全。

        参数:
            force: 为 True 时绕过缓存，强制重新截图
        """
        if not force:
            with self._cache_lock:
                if self._is_cache_valid():
                    return self._last_screenshot.copy()
        return self._grab_fresh()

    def grab_reuse(self) -> np.ndarray:
        """零分配截屏（TTL 缓存命中时），返回缓存引用。

        调用方不得修改返回的数组，否则会破坏缓存。
        如需修改请使用 grab() 代替。
        """
        with self._cache_lock:
            if self._is_cache_valid():
                return self._last_screenshot
        return self._grab_fresh()

    def get_screen_size(self) -> tuple[int, int]:
        """获取当前截图区域的物理像素尺寸"""
        if self._monitor:
            return self._monitor["width"], self._monitor["height"]
        m = self._sct.monitors[0]
        return m["width"], m["height"]

    def close(self) -> None:
        """关闭当前线程的 mss 资源"""
        if self._closed:
            return
        self._closed = True
        try:
            sct = getattr(self._tls, 'sct', None)
            if sct is not None:
                sct.close()
                self._tls.sct = None
        except Exception:
            pass

    @staticmethod
    def is_screen_black(screen: np.ndarray, threshold: float = 5.0) -> bool:
        """检测屏幕是否为黑屏（休眠/息屏状态）

        休眠/息屏的截图几乎全黑，像素均值接近 0。
        threshold: 像素均值阈值（0-255），低于此值判定为黑屏。
        """
        return float(screen.mean()) < threshold

    def __del__(self):
        if not getattr(self, '_closed', True):
            self._closed = True
            try:
                self.close()
            except Exception:
                pass


class _MatchCacheEntry(NamedTuple):
    result: tuple[int, int, int, int] | None
    timestamp: float


# 匹配结果缓存的 TTL：成功结果 2s，失败结果 (None) 仅 200ms
_MATCH_CACHE_TTL_SUCCESS = 2.0  # 匹配命中缓存 2s
_MATCH_CACHE_TTL_MISS = 0.2     # 匹配未命中缓存仅 0.2s



class _TemplateEntry(NamedTuple):
    raw: np.ndarray
    mtime: float
    last_check: float
    preprocessed: np.ndarray
    gray: np.ndarray


class TemplateMatcher:
    """模板匹配（带文件缓存，多尺度 + 灰度/边缘多策略匹配）"""

    # LRU 匹配结果缓存大小
    MATCH_CACHE_SIZE = 32
    # 模板条目最大数量（防止内存无限增长）
    TEMPLATE_ENTRY_MAX = 128

    def __init__(self):
        require_cv2("screen capture and template matching")
        self._entries: OrderedDict[str, _TemplateEntry] = OrderedDict()
        self._entries_lock = threading.Lock()
        # LRU 匹配结果缓存：相同截图+模板时直接返回缓存结果
        self._match_cache: OrderedDict[tuple[int, str, float], _MatchCacheEntry] = OrderedDict()
        self._match_cache_lock = threading.Lock()

    _MTIME_CHECK_INTERVAL = 5.0

    @staticmethod
    def _imread_unicode(path: str) -> np.ndarray | None:
        """cv2.imread 的 Unicode 安全替代：Windows 上 cv2.imread 无法读取含中文的路径"""
        try:
            buf = np.fromfile(path, dtype=np.uint8)
            return cv2.imdecode(buf, cv2.IMREAD_COLOR)
        except Exception:
            return None

    def load_template(self, path: str) -> np.ndarray:
        now = time.monotonic()
        with self._entries_lock:
            entry = self._entries.get(path)
            need_stat = entry is not None and (now - entry.last_check) >= self._MTIME_CHECK_INTERVAL

        if entry is not None and not need_stat:
            with self._entries_lock:
                self._entries.move_to_end(path)
            return entry.raw

        if entry is not None:
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                mtime = 0.0
            if mtime == entry.mtime:
                with self._entries_lock:
                    self._entries[path] = entry._replace(last_check=now)
                    self._entries.move_to_end(path)
                return entry.raw
        else:
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                raise FileNotFoundError(t("vision.log.template_not_found", path=path))

        img = self._imread_unicode(path)
        if img is None:
            raise ValueError(t("vision.log.image_read_failed", path=path))
        pp = self._preprocess(img)

        with self._entries_lock:
            self._entries[path] = _TemplateEntry(
                raw=img, mtime=mtime, last_check=now,
                preprocessed=pp, gray=self._to_gray(pp),
            )
            self._entries.move_to_end(path)
            while len(self._entries) > self.TEMPLATE_ENTRY_MAX:
                self._entries.popitem(last=False)
        return img

    def clear_cache(self) -> None:
        with self._entries_lock:
            self._entries.clear()
        with self._match_cache_lock:
            self._match_cache.clear()

    def invalidate(self, path: str) -> None:
        with self._entries_lock:
            self._entries.pop(path, None)
        with self._match_cache_lock:
            keys_to_remove = [k for k in self._match_cache if k[1] == path]
            for k in keys_to_remove:
                del self._match_cache[k]

    # 优先常用缩放，减少极端缩放以降低误匹配和 CPU 开销
    _MATCH_SCALES = [1.0, 1.5, 2.0, 0.75, 1.25, 0.5, 0.8]
    # 高置信度早退阈值：超过 threshold + 此值时跳过剩余缩放/策略
    _EARLY_EXIT_MARGIN = 0.08

    @staticmethod
    def _to_gray(img: np.ndarray) -> np.ndarray:
        """BGR → 灰度（单通道已是灰度的直接返回）"""
        if img.ndim == 2:
            return img
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    @staticmethod
    def _to_edges(gray: np.ndarray) -> np.ndarray:
        """Canny 边缘图（用于结构匹配，对亮度变化鲁棒）"""
        return cv2.Canny(gray, 50, 150)

    @staticmethod
    def _preprocess(img: np.ndarray) -> np.ndarray:
        """轻微高斯模糊降噪，提升匹配稳定性"""
        return cv2.GaussianBlur(img, (3, 3), 0)

    _MAX_VALID_SCALE = max(s for s in _MATCH_SCALES if s <= 4.0)

    @staticmethod
    def _compute_edge_pad(tpl: np.ndarray, scales: list[float]) -> int:
        """计算边缘填充量，确保模板在屏幕边缘仍可匹配

        padding = max(tw, th) * max_scale - 1，使滑窗能到达原始图像的坐标 0。
        """
        th, tw = tpl.shape[:2]
        max_dim = max(tw, th)
        max_scale = max((s for s in scales if s <= 4.0), default=max(scales) if scales else 1.0)
        return int(max_dim * max_scale) - 1

    def _match_single_scale(
        self,
        screen: np.ndarray,
        tpl: np.ndarray,
        method: int,
    ) -> tuple[float, int, int]:
        """单次模板匹配，返回 (置信度, x, y)"""
        result = cv2.matchTemplate(screen, tpl, method)
        _, val, _, loc = cv2.minMaxLoc(result)
        return val, loc[0], loc[1]

    # 验证搜索半径：补偿高斯模糊引起的峰值偏移
    _VERIFY_RADIUS = 5
    _VERIFY_MIN_SIZE = 16
    _VERIFY_ABS_REJECT_MARGIN = 0.20
    _VERIFY_REL_REJECT_MARGIN = 0.25

    def _verify_match(
        self,
        screen_original: np.ndarray,
        tpl_original: np.ndarray,
        x: int,
        y: int,
        w: int,
        h: int,
        scale: float,
        blurred_score: float,
        threshold: float,
        name: str,
    ) -> bool:
        """用未模糊图像验证候选匹配，对文字差异更敏感

        GaussianBlur 会平滑文字细节，导致外形相同但汉字不同的按钮
        产生高置信度误匹配。此方法跳过模糊，直接对比原始像素。

        在候选位置 ±_VERIFY_RADIUS 邻域内搜索最佳对齐，
        补偿模糊引起的 1-2px 峰值偏移，防止偶现验证假拒绝。

        拒绝条件：
          1. 绝对拒绝：未模糊分数 < threshold - 0.20
          2. 相对拒绝：模糊分数 - 未模糊分数 > 0.25

        性能：仅对匹配到的小区域运行一次 matchTemplate，
        相比全屏多尺度匹配的开销可忽略。
        """
        sh, sw = screen_original.shape[:2]

        # 过小的模板跳过验证（像素太少，区分度不足）
        if w < self._VERIFY_MIN_SIZE or h < self._VERIFY_MIN_SIZE:
            return True

        # 扩展搜索区域 ±_VERIFY_RADIUS，允许 matchTemplate 滑窗
        # 补偿高斯模糊导致的峰值偏移（通常 1-2px）
        r = self._VERIFY_RADIUS
        x1 = max(0, x - r)
        y1 = max(0, y - r)
        x2 = min(sw, x + w + r)
        y2 = min(sh, y + h + r)
        rw, rh = x2 - x1, y2 - y1

        # 扩展后区域仍过小则跳过验证
        if rw < max(6, w // 2) or rh < max(6, h // 2):
            return True

        # 从原始（未模糊、未填充）截图中提取扩展区域
        region = screen_original[y1:y2, x1:x2]

        # 准备原始模板（未模糊），缩放到匹配尺寸
        if is_one(scale):
            tpl_unblurred = tpl_original
        else:
            tpl_unblurred = cv2.resize(tpl_original, (w, h))

        # 若因边界裁剪导致区域小于模板，同步裁剪模板
        if rw < w or rh < h:
            tpl_unblurred = tpl_unblurred[0:rh, 0:rw]

        # 对未模糊的灰度图计算 NCC（扩展区域允许 ±r 滑窗补偿偏移）
        region_gray = self._to_gray(region)
        tpl_gray = self._to_gray(tpl_unblurred)
        result = cv2.matchTemplate(region_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
        unblurred_score = float(cv2.minMaxLoc(result)[1])

        # 绝对拒绝：未模糊分数过低（放宽 0.05 防止因灰度/彩色通道差异误拒）
        abs_reject = unblurred_score < (threshold - self._VERIFY_ABS_REJECT_MARGIN)
        rel_reject = (blurred_score - unblurred_score) > self._VERIFY_REL_REJECT_MARGIN

        if abs_reject or rel_reject:
            reason = t("vision.log.verify_reason_absolute") if abs_reject else t("vision.log.verify_reason_relative")
            log.info(
                t("vision.log.verify_rejected", name=name, blurred=f"{blurred_score:.3f}",
                  unblurred=f"{unblurred_score:.3f}", threshold=f"{threshold:.2f}",
                  reason=reason, scale=scale)
            )
            return False

        log.debug(
            t("vision.log.verify_passed", name=name, blurred=f"{blurred_score:.3f}", unblurred=f"{unblurred_score:.3f}")
        )
        return True

    def find(
        self,
        screen: np.ndarray,
        template_path: str,
        threshold: float = 0.8,
        screen_hash: int | None = None,
    ) -> tuple[int, int, int, int] | None:
        """多尺度 + 多策略模板匹配（彩色 → 灰度 → 边缘），返回最佳匹配

        使用边缘填充 (BORDER_REPLICATE) 确保屏幕边缘的 UI 元素也能被匹配。
        带 LRU 缓存：相同截图+模板时直接返回缓存结果。
        """
        tpl = self.load_template(template_path)
        th, tw = tpl.shape[:2]
        name = os.path.basename(template_path)

        if screen_hash is None:
            screen_hash = compute_image_hash(screen)
        cache_key = (screen_hash, template_path, round(threshold, 2))
        now = time.monotonic()
        with self._match_cache_lock:
            entry = self._match_cache.get(cache_key)
            if entry is not None:
                ttl = _MATCH_CACHE_TTL_SUCCESS if entry.result is not None else _MATCH_CACHE_TTL_MISS
                if now - entry.timestamp < ttl:
                    self._match_cache.move_to_end(cache_key)
                    log.debug(t("vision.log.cache_hit", name=name))
                    return entry.result
                # TTL 过期，淘汰旧条目
                del self._match_cache[cache_key]

        with self._entries_lock:
            tpl_entry = self._entries.get(template_path)
            if tpl_entry is None:
                return None
            tpl_pp = tpl_entry.preprocessed
            tpl_gray = tpl_entry.gray

        # 计算边缘填充量，使屏幕边缘的模板也能匹配
        pad = self._compute_edge_pad(tpl, self._MATCH_SCALES)
        screen_padded = cv2.copyMakeBorder(screen, pad, pad, pad, pad, cv2.BORDER_REPLICATE)
        sh, sw = screen_padded.shape[:2]

        # 模板尺寸感知缩放过滤 — 跳过使模板过大或过小的无效缩放
        valid_scales = [
            s for s in self._MATCH_SCALES
            if tw * s * th * s >= 100  # 缩放后面积 >= 100px²
            and tw * s <= sw * 0.5 and th * s <= sh * 0.5  # 不超过截图 50%
        ]
        if not valid_scales:
            valid_scales = [1.0]  # 保底至少尝试 1.0

        screen_pp = self._preprocess(screen_padded)
        screen_gray = self._to_gray(screen_pp)
        # 边缘图延迟计算，仅在需要时生成
        screen_edge: np.ndarray | None = None

        # 直接追踪最佳匹配，避免构建 candidates 列表
        best_val = 0.0
        best_match: tuple | None = None
        need_edge = False

        for scale in valid_scales:
            new_w, new_h = int(tw * scale), int(th * scale)
            if new_w < 8 or new_h < 8 or new_w > sw or new_h > sh:
                continue

            # 缩放模板（scale==1.0 时直接使用缓存）
            if is_one(scale):
                scaled_tpl = tpl_pp
                scaled_gray = tpl_gray
            else:
                scaled_tpl = cv2.resize(tpl_pp, (new_w, new_h))
                scaled_gray = cv2.resize(tpl_gray, (new_w, new_h))

            # 策略 1：彩色匹配
            val, x, y = self._match_single_scale(screen_pp, scaled_tpl, cv2.TM_CCOEFF_NORMED)
            if val > best_val:
                best_val = val
                best_match = (val, x, y, new_w, new_h, scale, "color")

            # 高置信度早退：彩色匹配已远超阈值时跳过灰度和后续缩放
            if best_val >= threshold + self._EARLY_EXIT_MARGIN:
                need_edge = False
                break

            # 策略 2：灰度匹配（仅在彩色未达阈值时）
            if val < threshold:
                val_g, x_g, y_g = self._match_single_scale(screen_gray, scaled_gray, cv2.TM_CCOEFF_NORMED)
                if val_g > best_val:
                    best_val = val_g
                    best_match = (val_g, x_g, y_g, new_w, new_h, scale, "gray")
                if val_g >= threshold + self._EARLY_EXIT_MARGIN:
                    need_edge = False
                    break

            if val < threshold and best_match and best_match[0] < threshold:
                need_edge = True

        # 策略 3：边缘匹配（延迟计算，仅在彩色和灰度都未达阈值时）
        if need_edge:
            screen_edge = self._to_edges(screen_gray)
            if screen_edge.any():
                for scale in valid_scales:
                    new_w, new_h = int(tw * scale), int(th * scale)
                    if new_w < 8 or new_h < 8 or new_w > sw or new_h > sh:
                        continue
                    scaled_gray = tpl_gray if is_one(scale) else cv2.resize(tpl_gray, (new_w, new_h))
                    tpl_edge = self._to_edges(scaled_gray)
                    if tpl_edge.any():
                        val_e, x_e, y_e = self._match_single_scale(screen_edge, tpl_edge, cv2.TM_CCOEFF_NORMED)
                        if val_e > best_val:
                            best_val = val_e
                            best_match = (val_e, x_e, y_e, new_w, new_h, scale, "edge")

            # 边缘匹配后仍未找到
            if best_match is None or best_val < threshold:
                log.info(t("vision.log.template_too_large", name=name, tw=tw, th=th, sw=sw, sh=sh))
                self._put_match_cache(cache_key, None)
                return None

        val, x, y, w, h, best_scale, strategy = best_match

        if val >= threshold:
            orig_x = max(0, x - pad)
            orig_y = max(0, y - pad)

            # 阶段 2：用未模糊图像验证，防止外形相似但文字不同的按钮误匹配
            if strategy in ("color", "gray"):
                verified = self._verify_match(
                    screen_original=screen,
                    tpl_original=tpl,
                    x=orig_x, y=orig_y,
                    w=w, h=h,
                    scale=best_scale,
                    blurred_score=val,
                    threshold=threshold,
                    name=name,
                )
                if not verified:
                    log.info(
                        t("vision.log.no_match_verify", name=name, score=f"{val:.2f}", strategy=strategy)
                    )
                    self._put_match_cache(cache_key, None)
                    return None

            log.info(
                t("vision.log.match_found", name=name, score=f"{val:.2f}", scale=best_scale,
                  strategy=strategy, x=orig_x, y=orig_y, w=w, h=h)
            )
            result = (orig_x, orig_y, w, h)
            self._put_match_cache(cache_key, result)
            return result

        log.info(t("vision.log.no_match", name=name, score=f"{val:.2f}", tw=tw, th=th, sw=sw, sh=sh, strategy=strategy))
        self._put_match_cache(cache_key, None)
        return None

    def _put_match_cache(self, key: tuple[int, str, float], result: tuple[int, int, int, int] | None) -> None:
        """写入 LRU 匹配缓存，超限时淘汰最旧条目。"""
        with self._match_cache_lock:
            self._match_cache[key] = _MatchCacheEntry(result, time.monotonic())
            if len(self._match_cache) > self.MATCH_CACHE_SIZE:
                self._match_cache.popitem(last=False)

    def find_all(
        self,
        screen: np.ndarray,
        template_path: str,
        threshold: float = 0.8,
    ) -> list[tuple[int, int, int, int]]:
        """多尺度查找所有匹配，返回最佳缩放下所有命中位置

        使用边缘填充 (BORDER_REPLICATE) 确保屏幕边缘的模板也能被匹配。
        """
        tpl = self.load_template(template_path)
        th, tw = tpl.shape[:2]

        # 使用缓存的预处理模板
        entry = self._entries[template_path]
        tpl_pp = entry.preprocessed

        # 计算边缘填充量
        pad = self._compute_edge_pad(tpl, self._MATCH_SCALES)
        screen_padded = cv2.copyMakeBorder(screen, pad, pad, pad, pad, cv2.BORDER_REPLICATE)
        sh, sw = screen_padded.shape[:2]

        screen_pp = self._preprocess(screen_padded)

        best_results: list[tuple[int, int, int, int]] = []
        best_val = 0.0

        for scale in self._MATCH_SCALES:
            new_w, new_h = int(tw * scale), int(th * scale)
            if new_w < 8 or new_h < 8 or new_w > sw or new_h > sh:
                continue
            scaled_tpl = tpl_pp if is_one(scale) else cv2.resize(tpl_pp, (new_w, new_h))
            result = cv2.matchTemplate(screen_pp, scaled_tpl, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(result)
            if max_val > best_val:
                locations = np.where(result >= threshold)
                if len(locations[0]) > 0:
                    best_val = max_val
                    # 将填充图像上的坐标转换回原始截图坐标
                    best_results = [
                        (max(0, int(pt[0]) - pad), max(0, int(pt[1]) - pad), new_w, new_h)
                        for pt in zip(*locations[::-1], strict=False)
                    ]
                    if max_val >= threshold + self._EARLY_EXIT_MARGIN:
                        break

        return best_results

    def match_multiscale(
        self,
        screenshot: np.ndarray,
        template: np.ndarray,
        scales: list[float] | None = None,
        threshold: float = 0.8,
    ) -> tuple[bool, tuple[int, int] | None, float]:
        """在多个缩放级别尝试匹配，返回最佳结果。

        比 find() 轻量：直接接受 numpy 数组模板，不经过文件缓存/验证流程。
        适用于需要精细控制缩放范围的场景。

        参数:
            screenshot: BGR 截图
            template: BGR 模板图像
            scales: 缩放级别列表，默认 [0.9, 1.0, 1.1]
            threshold: 匹配置信度阈值

        返回:
            (是否匹配, 匹配位置(x,y)或None, 最佳置信度)
        """
        if scales is None:
            scales = [0.9, 1.0, 1.1]
        best_val = 0.0
        best_loc = None
        th, tw = template.shape[:2]
        for scale in scales:
            new_w, new_h = int(tw * scale), int(th * scale)
            if new_w == 0 or new_h == 0:
                continue
            if new_w > screenshot.shape[1] or new_h > screenshot.shape[0]:
                continue
            scaled = template if is_one(scale) else cv2.resize(template, (new_w, new_h))
            result = cv2.matchTemplate(screenshot, scaled, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            if max_val > best_val:
                best_val = max_val
                best_loc = max_loc
        if best_val >= threshold and best_loc is not None:
            return True, best_loc, best_val
        return False, None, best_val
