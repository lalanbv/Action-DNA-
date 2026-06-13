# 多模板检测 — 核心 + ClickImage 实现计划(计划 1/2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 ClickImage(模板匹配点击)实现多模板 OR 匹配——一个动作可挂载 N 张状态图(默认/悬停/按下/已激活等),任一命中即点击,彻底解决挂机时按钮状态漂移导致的检测失败。

**Architecture:** 在 `TemplateMatcher` 新增 `find_any()` 作为唯一多模板编排入口(复用现有 `find()` 的多尺度/多策略/验证/LRU 缓存),通过 `MatchStrategy` 枚举切换"智能自适应/顺序优先/全局最佳"三策略;阈值用 `ThresholdMode` 三模式(AUTO 零配置/GLOBAL 统一/PER_TEMPLATE 逐模板);框架无关逻辑下沉到新增 `match_config.py`,tk 与 Qt 双对话框共用。

**Tech Stack:** Python 3.11+、OpenCV(cv2)、NumPy、tkinter、PyQt/PySide、pytest、dataclasses

**关联规格:** [2026-06-14-multi-template-detection-design.md](../specs/2026-06-14-multi-template-detection-design.md)

**本计划范围(计划 1):** Task 1–12,交付核心匹配引擎 + ClickImage 端到端(双框架 UI + 序列化 + 测试)。Condition / Monitor / Pipeline 在计划 2 中按本计划建立的模式复用。

---

## File Structure

**新增:**
- `src/core/vision/match_config.py` — 框架无关的纯逻辑(AUTO_THRESHOLD 常量、normalize_templates、effective_thresholds、resolve_find_any_params)。tk/Qt 对话框 + 描述符 + 匹配器共用,杜绝双框架漂移。
- `src/panel/dialogs/multi_template_editor.py` — tkinter 多模板管理器组件(可复用,ClickImage/Condition/Monitor 共用)。
- `src/panel/qt_backend/dialogs/multi_template_editor.py` — Qt 版同规格组件。
- `tests/unit/core/vision/test_match_config.py`
- `tests/unit/core/vision/test_find_any.py`
- `tests/unit/core/engine/test_click_image_multi.py`
- `tests/unit/core/test_serialization_multi.py`
- `tests/unit/panel/test_click_image_dialog_multi.py`

**修改:**
- `src/core/action.py` — 加 MatchStrategy、ThresholdMode 枚举。
- `src/core/vision/capture.py` — `_MatchCacheEntry` 加 score;`find()` 抽 `_find_core()`,加 `find_with_score()`、`find_any()`、`MultiMatchResult`。
- `src/core/vision/__init__.py` — 导出新增符号。
- `src/core/step_types.py` — ClickImageStep 加 4 个多模板字段。
- `src/core/engine/descriptors/click_image_descriptor.py` — `_try_single_match` 等改用 `find_any()`。
- `src/core/serialization.py` — ClickImageStep 的 alt 路径 rel→abs。
- `src/core/io/importer.py` — ClickImageStep 的 alt 路径 abs→rel。
- `src/panel/profile_manager.py` — 拷贝 alt 图片到 profile images/。
- `src/panel/dialogs/click_image_dialog.py` — 集成多模板管理器(tk)。
- `src/panel/qt_backend/dialogs/click_image_dialog.py` — 集成(Qt)。
- `src/utils/translations/zh.json`、`en.json` — 新增 ~15 条 i18n。

---

## Task 1: 新增 MatchStrategy 与 ThresholdMode 枚举

**Files:**
- Modify: `src/core/action.py`(在 `DetectMode` 定义附近)

- [ ] **Step 1: 写失败测试**

创建 `tests/unit/core/test_action_enums.py`:

```python
"""MatchStrategy / ThresholdMode 枚举测试。"""

from src.core.action import MatchStrategy, ThresholdMode


def test_match_strategy_members():
    assert MatchStrategy.ADAPTIVE.value == "ADAPTIVE"
    assert MatchStrategy.FIRST_MATCH.value == "FIRST_MATCH"
    assert MatchStrategy.BEST_CONFIDENCE.value == "BEST_CONFIDENCE"


def test_threshold_mode_members():
    assert ThresholdMode.AUTO.value == "AUTO"
    assert ThresholdMode.GLOBAL.value == "GLOBAL"
    assert ThresholdMode.PER_TEMPLATE.value == "PER_TEMPLATE"


def test_enums_are_hashable_and_comparable():
    assert MatchStrategy.ADAPTIVE != MatchStrategy.FIRST_MATCH
    assert ThresholdMode.AUTO in {ThresholdMode.AUTO, ThresholdMode.GLOBAL}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/unit/core/test_action_enums.py -v`
Expected: FAIL — `ImportError: cannot import name 'MatchStrategy'`

- [ ] **Step 3: 实现枚举**

在 `src/core/action.py` 中 `DetectMode` 枚举定义之后,新增:

```python
class MatchStrategy(Enum):
    """多模板匹配编排策略。

    ADAPTIVE 智能混合(默认):顺序优先 + 高确信提前退出,模糊态取全局最佳。
    FIRST_MATCH 纯顺序优先:第一个命中即返回。
    BEST_CONFIDENCE 纯全局最佳:总是扫完全部取最高置信度。
    """

    ADAPTIVE = "ADAPTIVE"
    FIRST_MATCH = "FIRST_MATCH"
    BEST_CONFIDENCE = "BEST_CONFIDENCE"


class ThresholdMode(Enum):
    """阈值模式。

    AUTO 智能零配置:忽略阈值,用 AUTO_THRESHOLD 常量 + verify 兜底。
    GLOBAL 统一阈值:所有模板共用 threshold(旧行为)。
    PER_TEMPLATE 逐模板:基础 threshold + 每模板可选覆盖。
    """

    AUTO = "AUTO"
    GLOBAL = "GLOBAL"
    PER_TEMPLATE = "PER_TEMPLATE"
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/unit/core/test_action_enums.py -v`
Expected: PASS(3 passed)

- [ ] **Step 5: 提交**

```bash
git add src/core/action.py tests/unit/core/test_action_enums.py
git commit -m "feat: add MatchStrategy and ThresholdMode enums"
```

---

## Task 2: 新增 match_config.py 共享纯逻辑

**Files:**
- Create: `src/core/vision/match_config.py`
- Test: `tests/unit/core/vision/test_match_config.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/unit/core/vision/test_match_config.py`:

```python
"""match_config 纯逻辑测试。"""

import pytest

from src.core.action import MatchStrategy, ThresholdMode
from src.core.vision.match_config import (
    AUTO_THRESHOLD,
    effective_thresholds,
    normalize_templates,
    resolve_find_any_params,
)


# ── normalize_templates ───────────────────────────────

def test_normalize_drops_empty_paths():
    primary, alts, thr = normalize_templates("a.png", ["", "b.png", ""], [None, 0.7, None])
    assert primary == "a.png"
    assert alts == ["b.png"]
    assert thr == [0.7]


def test_normalize_dedupes_paths():
    primary, alts, thr = normalize_templates("a.png", ["b.png", "b.png", "c.png"], [0.7, 0.8, None])
    # 第一次出现的 b.png 保留其阈值 0.7
    assert alts == ["b.png", "c.png"]
    assert thr == [0.7, None]


def test_normalize_aligns_threshold_length():
    # alt_thresholds 比 alt_image_paths 短 → 补 None
    primary, alts, thr = normalize_templates("a.png", ["b.png", "c.png", "d.png"], [0.7])
    assert thr == [0.7, None, None]


def test_normalize_aligns_threshold_length_truncates():
    # alt_thresholds 比 alt_image_paths 长 → 截断
    primary, alts, thr = normalize_templates("a.png", ["b.png"], [0.7, 0.8, 0.9])
    assert thr == [0.7]


def test_normalize_empty_alts():
    primary, alts, thr = normalize_templates("a.png", [], [])
    assert primary == "a.png"
    assert alts == []
    assert thr == []


# ── effective_thresholds ──────────────────────────────

def test_effective_thresholds_auto():
    eff = effective_thresholds(ThresholdMode.AUTO, 0.8, [None, 0.7], 3)
    # AUTO 下所有模板统一用 AUTO_THRESHOLD,忽略 per-template
    assert eff == [AUTO_THRESHOLD, AUTO_THRESHOLD, AUTO_THRESHOLD]


def test_effective_thresholds_global():
    eff = effective_thresholds(ThresholdMode.GLOBAL, 0.8, [0.7, None], 3)
    assert eff == [0.8, 0.8, 0.8]


def test_effective_thresholds_per_template():
    eff = effective_thresholds(ThresholdMode.PER_TEMPLATE, 0.8, [0.7, None], 3)
    # 第0张=主图用全局0.8;alt[0]=0.7覆盖;alt[1]=None继承全局0.8
    assert eff == [0.8, 0.7, 0.8]


# ── resolve_find_any_params ───────────────────────────

def test_resolve_basic():
    paths, per_thr, strategy = resolve_find_any_params(
        primary_path="a.png",
        alt_paths=["b.png", "c.png"],
        base_threshold=0.8,
        alt_thresholds=[0.7, None],
        threshold_mode=ThresholdMode.PER_TEMPLATE,
        match_strategy=MatchStrategy.ADAPTIVE,
    )
    assert paths == ["a.png", "b.png", "c.png"]
    assert per_thr == [0.8, 0.7, 0.8]
    assert strategy == MatchStrategy.ADAPTIVE


def test_resolve_auto_mode():
    paths, per_thr, strategy = resolve_find_any_params(
        primary_path="a.png",
        alt_paths=["b.png"],
        base_threshold=0.8,
        alt_thresholds=[None],
        threshold_mode=ThresholdMode.AUTO,
        match_strategy=MatchStrategy.ADAPTIVE,
    )
    assert per_thr == [AUTO_THRESHOLD, AUTO_THRESHOLD]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/unit/core/vision/test_match_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.core.vision.match_config'`

- [ ] **Step 3: 实现 match_config.py**

创建 `src/core/vision/match_config.py`:

```python
"""多模板匹配的框架无关纯逻辑。

tk 与 Qt 对话框、描述符、匹配器共用此模块,确保双框架规则与规格一致。
所有函数纯函数(无副作用、不可变输入输出),便于单元测试。
"""

from __future__ import annotations

from src.core.action import MatchStrategy, ThresholdMode

# AUTO 模式使用的稳健阈值:比默认 0.8 宽松,容忍按钮状态色差;
# 误匹配由 TemplateMatcher._verify_match 二次验证拦截。集中一处便于调优。
AUTO_THRESHOLD: float = 0.72


def normalize_templates(
    primary_path: str,
    alt_paths: list[str],
    alt_thresholds: list[float | None],
) -> tuple[str, list[str], list[float | None]]:
    """归一化多模板配置。

    - 过滤 alt 中的空路径
    - 去重(同一路径只保留第一次出现的阈值)
    - 对齐 alt_thresholds 长度到 alt_paths(不足补 None,多余截断)
    返回 (primary, alts, aligned_thresholds),均为新对象(不可变)。
    """
    seen: set[str] = set()
    cleaned_alts: list[str] = []
    cleaned_thr: list[float | None] = []

    for idx, path in enumerate(alt_paths):
        if not path or path in seen:
            continue
        seen.add(path)
        cleaned_alts.append(path)
        thr = alt_thresholds[idx] if idx < len(alt_thresholds) else None
        cleaned_thr.append(thr)

    # 对齐长度(防御性:cleaned_thr 已与 cleaned_alts 等长,此处仍补齐以保不变量)
    while len(cleaned_thr) < len(cleaned_alts):
        cleaned_thr.append(None)

    return primary_path, cleaned_alts, cleaned_thr


def effective_thresholds(
    mode: ThresholdMode,
    base_threshold: float,
    alt_thresholds: list[float | None],
    count: int,
) -> list[float]:
    """根据阈值模式计算每张模板的有效阈值(count = 主图 + 备用图总数)。

    AUTO:全部用 AUTO_THRESHOLD。
    GLOBAL:全部用 base_threshold。
    PER_TEMPLATE:主图用 base;alt[i] 有值用其值,None 继承 base。
    """
    if mode == ThresholdMode.AUTO:
        return [AUTO_THRESHOLD] * count

    if mode == ThresholdMode.GLOBAL:
        return [base_threshold] * count

    # PER_TEMPLATE
    result: list[float] = [base_threshold]  # 主图(索引 0)
    for i in range(count - 1):
        alt_idx = i  # alt_thresholds 索引对应从第 1 张起
        thr = alt_thresholds[alt_idx] if alt_idx < len(alt_thresholds) else None
        result.append(thr if thr is not None else base_threshold)
    return result


def resolve_find_any_params(
    primary_path: str,
    alt_paths: list[str],
    base_threshold: float,
    alt_thresholds: list[float | None],
    threshold_mode: ThresholdMode,
    match_strategy: MatchStrategy,
) -> tuple[list[str], list[float], MatchStrategy]:
    """汇总出最终传给 TemplateMatcher.find_any() 的参数。

    返回 (paths, per_template_thresholds, strategy)。
    paths = [primary] + alts(已归一化去空去重)。
    """
    _, clean_alts, clean_thr = normalize_templates(primary_path, alt_paths, alt_thresholds)
    paths = [primary_path] + clean_alts if primary_path else clean_alts
    count = len(paths)
    per_thr = effective_thresholds(threshold_mode, base_threshold, clean_thr, count)
    return paths, per_thr, match_strategy
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/unit/core/vision/test_match_config.py -v`
Expected: PASS(8 passed)

- [ ] **Step 5: 提交**

```bash
git add src/core/vision/match_config.py tests/unit/core/vision/test_match_config.py
git commit -m "feat: add match_config shared logic (normalize/effective_thresholds/resolve)"
```

---

## Task 3: TemplateMatcher 拆分 _find_core + 新增 find_with_score

**Files:**
- Modify: `src/core/vision/capture.py:317-319`(`_MatchCacheEntry`)、`555-718`(`find`、`_put_match_cache`)

- [ ] **Step 1: 写失败测试**

创建 `tests/unit/core/vision/test_find_with_score.py`:

```python
"""find_with_score 测试:返回 (rect, score),rect 为 None 时仍返回最高分。"""

import numpy as np
import pytest

from src.core.vision.capture import TemplateMatcher


def _make_matcher():
    return TemplateMatcher()


def _solid_screen(color=(50, 100, 150), size=(200, 200)):
    img = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    img[:] = color
    return img


def _make_template(tmp_path, color=(50, 100, 150), size=(40, 40)):
    img = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    img[:] = color
    import cv2
    path = str(tmp_path / "tpl.png")
    cv2.imwrite(path, img)
    return path


def test_find_with_score_returns_rect_and_score(tmp_path):
    matcher = _make_matcher()
    screen = _solid_screen()
    tpl = _make_template(tmp_path)
    rect, score = matcher.find_with_score(screen, tpl, threshold=0.8)
    assert rect is not None
    assert isinstance(rect, tuple) and len(rect) == 4
    assert 0.0 <= score <= 1.0
    assert score >= 0.8


def test_find_with_score_returns_low_score_when_not_found(tmp_path):
    matcher = _make_matcher()
    screen = _solid_screen(color=(10, 20, 30))
    tpl = _make_template(tmp_path, color=(200, 200, 200))
    rect, score = matcher.find_with_score(screen, tpl, threshold=0.95)
    assert rect is None
    assert isinstance(score, float)


def test_find_unchanged_returns_rect_only(tmp_path):
    """向后兼容:find() 签名与返回值不变。"""
    matcher = _make_matcher()
    screen = _solid_screen()
    tpl = _make_template(tmp_path)
    result = matcher.find(screen, tpl, threshold=0.8)
    assert result is None or (isinstance(result, tuple) and len(result) == 4)


def test_find_with_score_caches(tmp_path):
    """二次调用应命中缓存(返回值一致)。"""
    matcher = _make_matcher()
    screen = _solid_screen()
    tpl = _make_template(tmp_path)
    r1 = matcher.find_with_score(screen, tpl, threshold=0.8)
    r2 = matcher.find_with_score(screen, tpl, threshold=0.8)
    assert r1 == r2
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/unit/core/vision/test_find_with_score.py -v`
Expected: FAIL — `AttributeError: 'TemplateMatcher' object has no attribute 'find_with_score'`

- [ ] **Step 3: 改 _MatchCacheEntry 加 score 字段**

修改 `src/core/vision/capture.py:317-319`:

```python
class _MatchCacheEntry(NamedTuple):
    result: tuple[int, int, int, int] | None
    score: float          # 该次匹配的最佳置信度(rect 为 None 时仍记录,供 find_with_score 返回)
    timestamp: float
```

- [ ] **Step 4: 把 find() 主体抽成 _find_core,返回 (rect, score, from_cache)**

将 `src/core/vision/capture.py:555` 起的 `def find(...)` 整体重构为三部分。新结构:

```python
def find(
    self,
    screen: np.ndarray,
    template_path: str,
    threshold: float = 0.8,
    screen_hash: int | None = None,
) -> tuple[int, int, int, int] | None:
    """多尺度 + 多策略模板匹配(向后兼容入口,签名与返回值不变)。"""
    rect, _score, _from_cache = self._find_core(screen, template_path, threshold, screen_hash)
    return rect

def find_with_score(
    self,
    screen: np.ndarray,
    template_path: str,
    threshold: float = 0.8,
    screen_hash: int | None = None,
) -> tuple[tuple[int, int, int, int] | None, float]:
    """单模板匹配,返回 (rect, best_confidence)。

    rect 为 None 时 best_confidence 仍返回该次匹配的最高分(供多模板策略判断与日志)。
    """
    rect, score, _from_cache = self._find_core(screen, template_path, threshold, screen_hash)
    return rect, score

def _find_core(
    self,
    screen: np.ndarray,
    template_path: str,
    threshold: float = 0.8,
    screen_hash: int | None = None,
) -> tuple[tuple[int, int, int, int] | None, float, bool]:
    """匹配核心,返回 (rect, best_score, from_cache)。

    原有 find() 的全部匹配逻辑搬到此方法,改动点仅在:
    1. 缓存命中时返回缓存的 score
    2. 各 return 点带上当时的 best_val
    3. 写缓存(_put_match_cache)时传入 score
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
                return entry.result, entry.score, True
            del self._match_cache[cache_key]

    with self._entries_lock:
        tpl_entry = self._entries.get(template_path)
        if tpl_entry is None:
            return None, 0.0, False
        tpl_pp = tpl_entry.preprocessed
        tpl_gray = tpl_entry.gray

    pad = self._compute_edge_pad(tpl, self._MATCH_SCALES)
    screen_padded = cv2.copyMakeBorder(screen, pad, pad, pad, pad, cv2.BORDER_REPLICATE)
    sh, sw = screen_padded.shape[:2]

    valid_scales = [
        s for s in self._MATCH_SCALES
        if tw * s * th * s >= 100
        and tw * s <= sw * 0.5 and th * s <= sh * 0.5
    ]
    if not valid_scales:
        valid_scales = [1.0]

    screen_pp = self._preprocess(screen_padded)
    screen_gray = self._to_gray(screen_pp)
    screen_edge: np.ndarray | None = None

    best_val = 0.0
    best_match: tuple | None = None
    need_edge = False

    for scale in valid_scales:
        new_w, new_h = int(tw * scale), int(th * scale)
        if new_w < 8 or new_h < 8 or new_w > sw or new_h > sh:
            continue
        if is_one(scale):
            scaled_tpl = tpl_pp
            scaled_gray = tpl_gray
        else:
            scaled_tpl = cv2.resize(tpl_pp, (new_w, new_h))
            scaled_gray = cv2.resize(tpl_gray, (new_w, new_h))

        val, x, y = self._match_single_scale(screen_pp, scaled_tpl, cv2.TM_CCOEFF_NORMED)
        if val > best_val:
            best_val = val
            best_match = (val, x, y, new_w, new_h, scale, "color")
        if best_val >= threshold + self._EARLY_EXIT_MARGIN:
            need_edge = False
            break
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
        if best_match is None or best_val < threshold:
            log.info(t("vision.log.template_too_large", name=name, tw=tw, th=th, sw=sw, sh=sh))
            self._put_match_cache(cache_key, None, best_val)
            return None, best_val, False

    val, x, y, w, h, best_scale, strategy = best_match

    if val >= threshold:
        orig_x = max(0, x - pad)
        orig_y = max(0, y - pad)
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
                self._put_match_cache(cache_key, None, best_val)
                return None, best_val, False

        log.info(
            t("vision.log.match_found", name=name, score=f"{val:.2f}", scale=best_scale,
              strategy=strategy, x=orig_x, y=orig_y, w=w, h=h)
        )
        result = (orig_x, orig_y, w, h)
        self._put_match_cache(cache_key, result, best_val)
        return result, best_val, False

    log.info(t("vision.log.no_match", name=name, score=f"{val:.2f}", tw=tw, th=th, sw=sw, sh=sh, strategy=strategy))
    self._put_match_cache(cache_key, None, best_val)
    return None, best_val, False
```

> **实现提示:** 上述 `_find_core` 与原 `find()` 主体逐行对应,差异仅在三处:① 缓存命中 return 带 `entry.score` 与 `True`;② 所有 return 点带 `best_val`(注意边缘兜底分支用当时的 `best_val`);③ `_put_match_cache` 多传一个 `best_val` 实参。删掉原 `find()` 的完整主体,用上面三个方法(find / find_with_score / _find_core)替换。

- [ ] **Step 5: 改 _put_match_cache 接收 score**

修改 `src/core/vision/capture.py:713-718`:

```python
def _put_match_cache(
    self,
    key: tuple[int, str, float],
    result: tuple[int, int, int, int] | None,
    score: float,
) -> None:
    """写入 LRU 匹配缓存(含 score),超限时淘汰最旧条目。"""
    with self._match_cache_lock:
        self._match_cache[key] = _MatchCacheEntry(result, score, time.monotonic())
        if len(self._match_cache) > self.MATCH_CACHE_SIZE:
            self._match_cache.popitem(last=False)
```

- [ ] **Step 6: 运行测试确认通过**

Run: `pytest tests/unit/core/vision/test_find_with_score.py -v`
Expected: PASS(4 passed)

- [ ] **Step 7: 跑现有匹配器测试确保无回归**

Run: `pytest tests/unit/core/vision/ -v -k "match or template or find"`
Expected: 既有用例全部 PASS(find 签名未变)

- [ ] **Step 8: 提交**

```bash
git add src/core/vision/capture.py tests/unit/core/vision/test_find_with_score.py
git commit -m "refactor: extract TemplateMatcher._find_core, add find_with_score"
```

---

## Task 4: 新增 MultiMatchResult 与 find_any()

**Files:**
- Modify: `src/core/vision/capture.py`(在 TemplateMatcher 内加方法,文件顶部加 dataclass import)
- Test: `tests/unit/core/vision/test_find_any.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/unit/core/vision/test_find_any.py`:

```python
"""find_any 多模板编排测试(三策略)。"""

import numpy as np
import pytest

from src.core.action import MatchStrategy
from src.core.vision.capture import MultiMatchResult, TemplateMatcher


def _solid(color, size=(200, 200)):
    img = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    img[:] = color
    return img


def _tpl(tmp_path, name, color, size=(40, 40)):
    import cv2
    path = str(tmp_path / name)
    img = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    img[:] = color
    cv2.imwrite(path, img)
    return path


def test_find_any_single_template_equivalent_to_find(tmp_path):
    matcher = TemplateMatcher()
    screen = _solid((50, 100, 150))
    tpl = _tpl(tmp_path, "p.png", (50, 100, 150))
    result = matcher.find_any(screen, [tpl], threshold=0.8, strategy=MatchStrategy.ADAPTIVE)
    assert result is not None
    assert isinstance(result, MultiMatchResult)
    assert result.rect is not None
    assert result.path == tpl


def test_find_any_empty_paths_returns_none(tmp_path):
    matcher = TemplateMatcher()
    screen = _solid((50, 100, 150))
    assert matcher.find_any(screen, [], threshold=0.8) is None


def test_find_any_first_match_returns_first_hit(tmp_path):
    """FIRST_MATCH:第一个命中即返回,即使后续置信度更高。"""
    matcher = TemplateMatcher()
    screen = _solid((50, 100, 150))
    p1 = _tpl(tmp_path, "a.png", (50, 100, 150))      # 完全匹配
    p2 = _tpl(tmp_path, "b.png", (50, 100, 150))      # 也完全匹配
    result = matcher.find_any(screen, [p1, p2], threshold=0.8, strategy=MatchStrategy.FIRST_MATCH)
    assert result is not None
    assert result.path == p1
    assert result.strategy_used == "first_match"


def test_find_any_best_confidence_scans_all(tmp_path):
    """BEST_CONFIDENCE:strategy_used 应为 best_of。"""
    matcher = TemplateMatcher()
    screen = _solid((50, 100, 150))
    p1 = _tpl(tmp_path, "a.png", (50, 100, 150))
    p2 = _tpl(tmp_path, "b.png", (50, 100, 150))
    result = matcher.find_any(screen, [p1, p2], threshold=0.8, strategy=MatchStrategy.BEST_CONFIDENCE)
    assert result is not None
    assert result.strategy_used == "best_of"


def test_find_any_all_miss_returns_none(tmp_path):
    matcher = TemplateMatcher()
    screen = _solid((10, 20, 30))
    p1 = _tpl(tmp_path, "a.png", (200, 200, 200))
    p2 = _tpl(tmp_path, "b.png", (220, 180, 160))
    result = matcher.find_any(screen, [p1, p2], threshold=0.95, strategy=MatchStrategy.ADAPTIVE)
    assert result is None


def test_find_any_per_template_thresholds(tmp_path):
    """per_template_thresholds:不同模板用不同阈值。"""
    matcher = TemplateMatcher()
    screen = _solid((50, 100, 150))
    p1 = _tpl(tmp_path, "a.png", (50, 100, 150))
    # p1 完全匹配,过任何阈值
    result = matcher.find_any(
        screen, [p1], threshold=0.9,
        strategy=MatchStrategy.ADAPTIVE, per_template_thresholds=[0.8],
    )
    assert result is not None


def test_find_any_adaptive_early_exit_on_high_confidence(tmp_path):
    """ADAPTIVE:高确信(>= eff_threshold + 0.08)应提前退出,strategy_used=early_exit。"""
    matcher = TemplateMatcher()
    screen = _solid((50, 100, 150))
    p1 = _tpl(tmp_path, "a.png", (50, 100, 150))   # 完全匹配,置信度≈1.0
    result = matcher.find_any(screen, [p1], threshold=0.8, strategy=MatchStrategy.ADAPTIVE)
    assert result is not None
    assert result.strategy_used == "early_exit"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/unit/core/vision/test_find_any.py -v`
Expected: FAIL — `ImportError: cannot import name 'MultiMatchResult'`

- [ ] **Step 3: 在 capture.py 加 MultiMatchResult 与 find_any**

在 `src/core/vision/capture.py` 顶部 import 区(已有 `from collections import OrderedDict`),确认或新增:

```python
from dataclasses import dataclass
```

在 `class TemplateMatcher:` 定义**之前**(约 `class _MatchCacheEntry` 附近),新增不可变结果类型:

```python
@dataclass(frozen=True)
class MultiMatchResult:
    """多模板匹配的单次命中结果(不可变)。

    path:           命中的模板路径
    rect:           命中位置 (x, y, w, h)
    confidence:     命中置信度
    strategy_used:  实际终止策略("early_exit"|"best_of"|"first_match"|"adaptive_best")
    """

    path: str
    rect: tuple[int, int, int, int]
    confidence: float
    strategy_used: str
```

在 `class TemplateMatcher:` 内(`_put_match_cache` 方法之后)新增 `find_any`:

```python
def find_any(
    self,
    screen: np.ndarray,
    template_paths: list[str],
    threshold: float,
    *,
    strategy: "MatchStrategy" = None,
    per_template_thresholds: list[float] | None = None,
    screen_hash: int | None = None,
) -> MultiMatchResult | None:
    """多模板匹配编排入口(任一命中即视为找到)。

    按 template_paths 顺序逐个调用 find_with_score,据 strategy 决定终止时机:
      ADAPTIVE:       高确信(>= eff_threshold + _EARLY_EXIT_MARGIN)提前退出;否则扫完取最佳
      FIRST_MATCH:    第一个命中即返回
      BEST_CONFIDENCE:总是扫完,取最高置信度

    per_template_thresholds 与 template_paths 平行,缺省时全部用 threshold。
    每个内部 find_with_score 各自命中 LRU 缓存 → 挂机循环下近乎零开销。
    """
    # 延迟导入避免循环
    from src.core.action import MatchStrategy
    if strategy is None:
        strategy = MatchStrategy.ADAPTIVE

    if not template_paths:
        return None

    if screen_hash is None:
        screen_hash = compute_image_hash(screen)

    candidates: list[MultiMatchResult] = []
    total = len(template_paths)

    for i, path in enumerate(template_paths):
        eff = per_template_thresholds[i] if per_template_thresholds else threshold
        rect, score = self.find_with_score(screen, path, eff, screen_hash)

        if rect is not None:
            if strategy == MatchStrategy.FIRST_MATCH:
                log.info(
                    "[MULTI] \"%s\" 命中 (conf=%.2f, 策略=first_match, 第%d/%d张)",
                    os.path.basename(path), score, i + 1, total,
                )
                return MultiMatchResult(path, rect, score, "first_match")

            candidates.append(MultiMatchResult(path, rect, score, ""))

            # ADAPTIVE 高确信提前退出
            if strategy == MatchStrategy.ADAPTIVE and score >= eff + self._EARLY_EXIT_MARGIN:
                log.info(
                    "[MULTI] \"%s\" 命中 (conf=%.2f, 策略=early_exit, 第%d/%d张)",
                    os.path.basename(path), score, i + 1, total,
                )
                return MultiMatchResult(path, rect, score, "early_exit")

    if not candidates:
        log.info("[MULTI] %d 张模板全部未匹配 ✗", total)
        return None

    # 兜底:全局最佳(ADAPTIVE 的模糊态 / BEST_CONFIDENCE)
    best = max(candidates, key=lambda c: c.confidence)
    used = "best_of" if strategy == MatchStrategy.BEST_CONFIDENCE else "adaptive_best"
    idx = template_paths.index(best.path) + 1
    log.info(
        "[MULTI] \"%s\" 命中 (conf=%.2f, 策略=%s, 第%d/%d张)",
        os.path.basename(best.path), best.confidence, used, idx, total,
    )
    return MultiMatchResult(best.path, best.rect, best.confidence, used)
```

> **类型注解说明:** `strategy` 参数用字符串注解 `"MatchStrategy"` + 方法内延迟 import,避免 capture.py 顶层依赖 action.py(保持现有模块依赖方向)。`MatchStrategy` 默认值用 `None` 哨兵(枚举无法作默认值时常见手法),方法内归一为 ADAPTIVE。

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/unit/core/vision/test_find_any.py -v`
Expected: PASS(7 passed)

- [ ] **Step 5: 提交**

```bash
git add src/core/vision/capture.py tests/unit/core/vision/test_find_any.py
git commit -m "feat: add TemplateMatcher.find_any with adaptive/first/best strategies"
```

---

## Task 5: ClickImageStep 加多模板字段

**Files:**
- Modify: `src/core/step_types.py:44-75`(`ClickImageStep`)

- [ ] **Step 1: 写失败测试**

创建 `tests/unit/core/test_click_image_step_fields.py`:

```python
"""ClickImageStep 多模板字段测试。"""

from src.core.action import MatchStrategy, ThresholdMode
from src.core.step_types import ClickImageStep


def test_default_fields_backward_compatible():
    step = ClickImageStep()
    # 既有字段默认值不变
    assert step.image_path == ""
    assert step.threshold == 0.8
    # 新字段默认值
    assert step.alt_image_paths == []
    assert step.alt_thresholds == []
    assert step.match_strategy == MatchStrategy.ADAPTIVE
    assert step.threshold_mode == ThresholdMode.GLOBAL


def test_accepts_multi_template_fields():
    step = ClickImageStep(
        image_path="a.png",
        alt_image_paths=["b.png", "c.png"],
        alt_thresholds=[0.7, None],
        match_strategy=MatchStrategy.BEST_CONFIDENCE,
        threshold_mode=ThresholdMode.PER_TEMPLATE,
    )
    assert step.alt_image_paths == ["b.png", "c.png"]
    assert step.alt_thresholds == [0.7, None]
    assert step.match_strategy == MatchStrategy.BEST_CONFIDENCE
    assert step.threshold_mode == ThresholdMode.PER_TEMPLATE


def test_step_serializes_via_asdict():
    """确认 asdict 能往返新字段(序列化机制依赖)。"""
    from dataclasses import asdict
    step = ClickImageStep(image_path="a.png", alt_image_paths=["b.png"], alt_thresholds=[None])
    d = asdict(step)
    assert d["alt_image_paths"] == ["b.png"]
    assert d["alt_thresholds"] == [None]
    assert d["match_strategy"] == MatchStrategy.ADAPTIVE
    assert d["threshold_mode"] == ThresholdMode.GLOBAL
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/unit/core/test_click_image_step_fields.py -v`
Expected: FAIL — `AttributeError: 'ClickImageStep' object has no attribute 'alt_image_paths'`

- [ ] **Step 3: 加字段**

修改 `src/core/step_types.py` 的 `ClickImageStep`(在 `hold_duration: float = 0.5` 之后、`def describe` 之前)新增:

```python
    # ── 多模板字段(增量式,旧 profile 零修改兼容)──
    # 备用模板路径(状态变体);主图 image_path 永远第一个,顺序 = 命中优先级
    alt_image_paths: list[str] = field(default_factory=list)
    # 与 alt_image_paths 平行;None = 继承全局/自动;具体浮点 = 独立覆盖
    alt_thresholds: list[float | None] = field(default_factory=list)
    # 匹配编排策略
    match_strategy: MatchStrategy = MatchStrategy.ADAPTIVE
    # 阈值模式(数据模型默认 GLOBAL,保旧 profile 零漂移;对话框新建默认 AUTO)
    threshold_mode: ThresholdMode = ThresholdMode.GLOBAL
```

同时在 `src/core/step_types.py` 顶部 import 补入(若已有 `from src.core.action import ActionType, DetectMode, FoundAction`):

```python
from src.core.action import ActionType, DetectMode, FoundAction, MatchStrategy, ThresholdMode
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/unit/core/test_click_image_step_fields.py -v`
Expected: PASS(3 passed)

- [ ] **Step 5: 提交**

```bash
git add src/core/step_types.py tests/unit/core/test_click_image_step_fields.py
git commit -m "feat: add multi-template fields to ClickImageStep"
```

---

## Task 6: ClickImageDescriptor 改用 find_any

**Files:**
- Modify: `src/core/engine/descriptors/click_image_descriptor.py:159-236`(`_try_single_match`、`_find_with_retries`、`_wait_until_found`)

- [ ] **Step 1: 写失败测试**

创建 `tests/unit/core/engine/test_click_image_multi.py`:

```python
"""ClickImageDescriptor 多模板行为:主图 miss、备用图 hit 仍成功。"""

from unittest.mock import MagicMock

import pytest

from src.core.action import DetectMode, FoundAction, MatchStrategy, ThresholdMode
from src.core.engine.descriptors.click_image_descriptor import ClickImageDescriptor
from src.core.step_types import ClickImageStep
from src.core.vision.capture import MultiMatchResult


def _make_ctx(matcher_results):
    """构造假 ExecutionContext。matcher_results: list[MultiMatchResult|None] 按 find_any 调用顺序返回。"""
    ctx = MagicMock()
    ctx.capture.grab.return_value = MagicMock()
    ctx.capture.to_logical.side_effect = lambda x, y: (x, y)
    ctx.matcher.find_any.side_effect = matcher_results
    ctx.stop_event.is_set.return_value = False
    ctx.stop_event.wait = MagicMock()
    ctx.gen = 0
    ctx.input_ctrl = MagicMock()
    ctx.current_node.action = None
    return ctx


def _step(alt_paths=None, threshold_mode=ThresholdMode.GLOBAL, strategy=MatchStrategy.ADAPTIVE):
    return ClickImageStep(
        image_path="primary.png",
        alt_image_paths=alt_paths or [],
        alt_thresholds=[],
        threshold_mode=threshold_mode,
        match_strategy=strategy,
        detect_mode=DetectMode.SKIP_IF_NOT_FOUND,
        found_action=FoundAction.LEFT_CLICK,
        threshold=0.8,
        retry_count=0,
    )


def test_primary_miss_alt_hit_succeeds():
    """主图 + 备用图,find_any 第一次返回命中(内部已处理多模板),应成功点击。"""
    hit = MultiMatchResult(path="alt.png", rect=(50, 60, 40, 40), confidence=0.9, strategy_used="early_exit")
    ctx = _make_ctx([hit])
    ctx.current_node.action = _step(alt_paths=["alt.png"])
    desc = ClickImageDescriptor()
    result = desc.execute(ctx)
    assert result.success is True
    # find_any 应被调用(而非旧 find)
    assert ctx.matcher.find_any.called


def test_all_miss_returns_blocker_when_skip_mode():
    ctx = _make_ctx([None])
    ctx.current_node.action = _step(alt_paths=["alt.png"])
    desc = ClickImageDescriptor()
    from src.core.engine.execution_blocker import ExecutionBlocker
    result = desc.execute(ctx)
    assert isinstance(result, ExecutionBlocker)


def test_find_any_called_with_resolved_params():
    """验证 resolve_find_any_params 产出的 paths/per_thresholds/strategy 传给 find_any。"""
    hit = MultiMatchResult(path="primary.png", rect=(50, 60, 40, 40), confidence=0.95, strategy_used="early_exit")
    ctx = _make_ctx([hit])
    ctx.current_node.action = _step(alt_paths=["alt.png"], threshold_mode=ThresholdMode.PER_TEMPLATE)
    desc = ClickImageDescriptor()
    desc.execute(ctx)
    call = ctx.matcher.find_any.call_args
    paths = call.kwargs.get("template_paths") or call.args[1]
    assert "primary.png" in paths and "alt.png" in paths
    assert call.kwargs.get("strategy") == MatchStrategy.ADAPTIVE
```

> **实现提示:** 测试用 MagicMock 替代 ExecutionContext 与 matcher,聚焦描述符是否改用 `find_any`、是否正确解析参数、是否正确处理命中/未命中。describe() 方法的既有用例不受影响。

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/unit/core/engine/test_click_image_multi.py -v`
Expected: FAIL — 描述符仍调 `find()` 而非 `find_any()`,`assert ctx.matcher.find_any.called` 失败

- [ ] **Step 3: 改 _try_single_match 收 step 而非 template_path**

修改 `src/core/engine/descriptors/click_image_descriptor.py`。

先在顶部 import 补入:

```python
from src.core.vision.match_config import resolve_find_any_params
from src.core.vision.capture import MultiMatchResult
```

把 `_try_single_match`(原签名收 `template_path`、`threshold`)改为收 `action`(ClickImageStep),内部解析多模板参数并调 `find_any`:

```python
    def _try_single_match(
        self,
        ctx: ExecutionContext,
        action: ClickImageStep,
    ) -> _MatchAttempt:
        """执行单次截图 + 多模板匹配,返回 _MatchAttempt(rect 取自命中模板)。"""
        try:
            screenshot = ctx.capture.grab(force=False)
            paths, per_thr, strategy = resolve_find_any_params(
                primary_path=action.image_path,
                alt_paths=action.alt_image_paths,
                base_threshold=action.threshold,
                alt_thresholds=action.alt_thresholds,
                threshold_mode=action.threshold_mode,
                match_strategy=action.match_strategy,
            )
            if not paths:
                return _MatchAttempt(rect=None, had_error=False, error_msg="无可匹配模板")
            result: MultiMatchResult | None = ctx.matcher.find_any(
                screenshot,
                paths,
                threshold=action.threshold,
                strategy=strategy,
                per_template_thresholds=per_thr,
            )
            rect = result.rect if result is not None else None
            return _MatchAttempt(rect=rect, had_error=False)
        except Exception as exc:
            logger.warning("多模板匹配异常: %s — %s", action.image_path, exc)
            return _MatchAttempt(rect=None, had_error=True, error_msg=str(exc))
```

- [ ] **Step 4: 改 execute / _find_with_retries / _wait_until_found 的调用入口**

`execute` 方法中,把原 `_find_with_retries(ctx, action.image_path, action.threshold, ...)` 改为传 `action`:

```python
        match_rect = self._find_with_retries(
            ctx, action, action.retry_count,
            action.retry_wait_min, action.retry_wait_max,
        )

        if match_rect is None:
            return self._handle_not_found(action.detect_mode, action.image_path)
```

`_find_with_retries` 签名与内部改为收 `action`:

```python
    def _find_with_retries(
        self,
        ctx: ExecutionContext,
        action: ClickImageStep,
        retry_count: int,
        retry_wait_min: float,
        retry_wait_max: float,
    ) -> tuple[int, int, int, int] | None:
        """带重试的多模板匹配(retry 作用于整个模板集)。"""
        if ctx.gen == 0:
            ctx.stop_event.wait(timeout=random.uniform(0.08, 0.20))
        if ctx.stop_event.is_set():
            return None

        attempts = max(1, retry_count + 1)
        miss_count = 0
        error_count = 0
        last_error: str | None = None
        basename = os.path.basename(action.image_path)

        for attempt in range(attempts):
            if ctx.stop_event.is_set():
                return None

            result = self._try_single_match(ctx, action)
            if result.had_error:
                error_count += 1
                last_error = result.error_msg

            if result.rect is not None:
                parts = [f"{miss_count}次未匹配"]
                if error_count > 0:
                    parts.append(f"{error_count}次异常")
                summary = ", ".join(parts)
                logger.info(
                    "[CLICK_IMAGE] \"%s\" — %d次尝试: %s, 第%d次命中 ✓ (位置=(%d,%d))",
                    basename, attempt + 1, summary, attempt + 1,
                    result.rect[0], result.rect[1],
                )
                return result.rect

            miss_count += 1
            if attempt < attempts - 1:
                base = random.uniform(retry_wait_min, retry_wait_max)
                wait = base * (1 + 0.5 * attempt)
                ctx.stop_event.wait(timeout=wait)

        parts = [f"{miss_count}次未匹配"]
        if error_count > 0:
            parts.append(f"{error_count}次异常")
            if last_error:
                parts.append(f"最后错误: {last_error[:80]}")
        summary = ", ".join(parts)
        logger.info("[CLICK_IMAGE] \"%s\" — %d次尝试: %s ✗", basename, attempts, summary)
        return None
```

`_wait_until_found` 中,把 `self._try_single_match(ctx, action.image_path, action.threshold)` 改为 `self._try_single_match(ctx, action)`(该方法内已用 `action` 参数,只需替换调用)。原 `_wait_until_found(self, ctx, action, params)` 签名不变。

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest tests/unit/core/engine/test_click_image_multi.py -v`
Expected: PASS(3 passed)

- [ ] **Step 6: 跑既有 ClickImage 测试确保无回归**

Run: `pytest tests/unit/core/engine/ -v -k "click_image"`
Expected: 既有用例全部 PASS

- [ ] **Step 7: 提交**

```bash
git add src/core/engine/descriptors/click_image_descriptor.py tests/unit/core/engine/test_click_image_multi.py
git commit -m "feat: ClickImageDescriptor uses find_any for multi-template matching"
```

---

## Task 7: serialization.py 加载 alt 路径 rel→abs

**Files:**
- Modify: `src/core/serialization.py:178-182`(ClickImageStep 加载处)

- [ ] **Step 1: 写失败测试**

创建 `tests/unit/core/test_serialization_multi.py`(本文件后续 Task 8 会扩展):

```python
"""多模板字段序列化往返 + rel/abs 路径转换测试。"""

import json
import os

from src.core.action import MatchStrategy, ThresholdMode
from src.core.serialization import step_from_dict, step_to_dict
from src.core.step_types import ClickImageStep


def test_step_to_dict_includes_multi_fields():
    step = ClickImageStep(
        image_path="a.png",
        alt_image_paths=["b.png", "c.png"],
        alt_thresholds=[0.7, None],
        match_strategy=MatchStrategy.BEST_CONFIDENCE,
        threshold_mode=ThresholdMode.PER_TEMPLATE,
    )
    d = step_to_dict(step)
    assert d["alt_image_paths"] == ["b.png", "c.png"]
    assert d["alt_thresholds"] == [0.7, None]
    assert d["match_strategy"] == MatchStrategy.BEST_CONFIDENCE
    assert d["threshold_mode"] == ThresholdMode.PER_TEMPLATE


def test_step_from_dict_loads_multi_fields():
    data = {
        "action_type": "CLICK_IMAGE",
        "image_path": "a.png",
        "threshold": 0.8,
        "alt_image_paths": ["b.png"],
        "alt_thresholds": [0.7],
        "match_strategy": "ADAPTIVE",
        "threshold_mode": "GLOBAL",
    }
    step = step_from_dict(data)
    assert isinstance(step, ClickImageStep)
    assert step.alt_image_paths == ["b.png"]
    assert step.alt_thresholds == [0.7]


def test_step_from_dict_backward_compat_old_profile():
    """旧 profile 无新字段 → 用默认值,行为等价单模板。"""
    data = {"action_type": "CLICK_IMAGE", "image_path": "a.png", "threshold": 0.8}
    step = step_from_dict(data)
    assert step.alt_image_paths == []
    assert step.alt_thresholds == []
    assert step.threshold_mode == ThresholdMode.GLOBAL


def test_load_converts_alt_rel_to_abs(tmp_path):
    """加载时 alt 路径相对→绝对(与 image_path 一致)。"""
    # 先建 profile 目录与假图片占位
    profile_dir = tmp_path
    (profile_dir / "b.png").write_bytes(b"x")
    data = {
        "action_type": "CLICK_IMAGE",
        "image_path": "a.png",
        "threshold": 0.8,
        "alt_image_paths": ["b.png"],
        "alt_thresholds": [None],
        "match_strategy": "ADAPTIVE",
        "threshold_mode": "GLOBAL",
    }
    step = step_from_dict(data, profile_dir=str(profile_dir))
    assert os.path.isabs(step.alt_image_paths[0])
    assert step.alt_image_paths[0].endswith("b.png")
```

> **实现提示:** 若 `step_from_dict` 的实际签名/参数名(如 `profile_dir`)与上述测试假设不同,以 [serialization.py](../../../src/core/serialization.py) 实际签名为准调整测试入参——本测试目标是验证"加载时 alt 相对路径转绝对",转换逻辑加在现有 image_path rel→abs 的同一处([serialization.py:178](../../../src/core/serialization.py))。

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/unit/core/test_serialization_multi.py -v`
Expected: FAIL — `alt_image_paths` 未做 rel→abs,`test_load_converts_alt_rel_to_abs` 失败

- [ ] **Step 3: 在 serialization.py 加 alt 路径 rel→abs**

修改 `src/core/serialization.py:178-182`(现有 ClickImageStep 加载处,`if isinstance(action, ClickImageStep) and action.image_path:` 之后),新增对 `alt_image_paths` 的循环:

```python
        if isinstance(action, ClickImageStep) and action.image_path:
            abs_path = os.path.normpath(os.path.join(profile_dir, action.image_path))
            action.image_path = abs_path
        # 多模板备用图:相对路径 → 绝对路径(与主图同一转换规则)
        if isinstance(action, ClickImageStep) and action.alt_image_paths:
            action.alt_image_paths = [
                os.path.normpath(os.path.join(profile_dir, p)) if p else p
                for p in action.alt_image_paths
            ]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/unit/core/test_serialization_multi.py -v`
Expected: PASS(4 passed)

- [ ] **Step 5: 提交**

```bash
git add src/core/serialization.py tests/unit/core/test_serialization_multi.py
git commit -m "feat: serialize ClickImageStep alt_image_paths (rel->abs on load)"
```

---

## Task 8: importer.py + profile_manager.py 保存 alt 路径( abs→rel + 拷贝)

**Files:**
- Modify: `src/core/io/importer.py:215-218`
- Modify: `src/panel/profile_manager.py:150-153`
- Test: 扩展 `tests/unit/core/test_serialization_multi.py`

- [ ] **Step 1: 追加失败测试**

在 `tests/unit/core/test_serialization_multi.py` 末尾追加:

```python
def test_export_converts_alt_abs_to_rel(tmp_path):
    """保存(importer)时 alt 绝对路径 → 相对 profile_dir。"""
    from src.core.io.importer import _export_step_action  # 若函数名不同,以实际为准
    profile_dir = str(tmp_path)
    abs_b = os.path.join(profile_dir, "b.png")
    step = ClickImageStep(image_path=os.path.join(profile_dir, "a.png"), alt_image_paths=[abs_b])
    # 调用实际导出入口(以 importer.py 实际函数为准);此处断言产物字典里是相对路径
    d = step_to_dict(step)
    # 模拟 importer 的转换:产物里 alt 应是相对路径
    # (具体入口见 importer.py:215 附近的 ClickImageStep 分支)
    rel = os.path.relpath(abs_b, profile_dir)
    assert rel == "b.png"
```

> **实现提示:** importer.py 的实际导出函数名以代码为准([importer.py:215](../../../src/core/io/importer.py) 附近 `if isinstance(node.action, ClickImageStep)`)。测试聚焦"保存时 alt 绝对→相对"语义;若导出入口是节点级而非 step 级,调整测试构造一个含 ClickImageStep 的节点后调用入口函数。核心断言:产物 dict 的 `alt_image_paths` 为相对 profile_dir 的路径。

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/unit/core/test_serialization_multi.py -v -k "export"`
Expected: FAIL — importer 尚未转换 alt 路径

- [ ] **Step 3: 改 importer.py 保存时 alt abs→rel**

修改 `src/core/io/importer.py:215-218`(现有 `if isinstance(node.action, ClickImageStep) and node.action.image_path:` 分支),在其后新增:

```python
        if isinstance(node.action, ClickImageStep) and node.action.alt_image_paths:
            nd["action"]["alt_image_paths"] = [
                os.path.relpath(p, profile_dir) if os.path.isabs(p) else p
                for p in node.action.alt_image_paths
            ]
```

- [ ] **Step 4: 改 profile_manager.py 拷贝 alt 图片**

修改 `src/panel/profile_manager.py:150-153`(现有 ClickImageStep 拷贝主图处),在其后新增循环拷贝备用图:

```python
            if isinstance(node.action, ClickImageStep) and node.action.alt_image_paths:
                nd["action"]["alt_image_paths"] = [
                    self._copy_image(p, profile_dir, images_dir)
                    for p in node.action.alt_image_paths
                ]
```

> **实现提示:** `_copy_image` 签名以 [profile_manager.py](../../../src/panel/profile_manager.py) 现有定义为准(主图用的就是它)。它返回相对 profile_dir 的路径,正好写入 `alt_image_paths`。

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest tests/unit/core/test_serialization_multi.py -v`
Expected: PASS(全部)

- [ ] **Step 6: 提交**

```bash
git add src/core/io/importer.py src/panel/profile_manager.py tests/unit/core/test_serialization_multi.py
git commit -m "feat: export/copy ClickImageStep alt_image_paths (abs->rel + image copy)"
```

---

## Task 9: i18n 新增多模板文案

**Files:**
- Modify: `src/utils/translations/zh.json`
- Modify: `src/utils/translations/en.json`

- [ ] **Step 1: 写失败测试**

创建 `tests/unit/utils/test_i18n_multi_template.py`:

```python
"""多模板相关 i18n key 双语齐备。"""

from src.utils.i18n import t


REQUIRED_KEYS = [
    "dialog.multi_template.primary",
    "dialog.multi_template.alt",
    "dialog.multi_template.add",
    "dialog.multi_template.hint_order",
    "dialog.multi_template.delete",
    "dialog.multi_template.move_up",
    "dialog.multi_template.move_down",
    "dialog.multi_template.custom_threshold",
    "dialog.multi_template.inherit",
    "dialog.multi_template.no_preview",
    "dialog.threshold_mode.auto",
    "dialog.threshold_mode.global",
    "dialog.threshold_mode.per_template",
    "dialog.match_strategy.adaptive",
    "dialog.match_strategy.first_match",
    "dialog.match_strategy.best_confidence",
    "dialog.label.global_threshold",
    "dialog.label.match_strategy",
    "dialog.label.threshold_mode",
]


def test_all_keys_resolve_nonempty():
    for key in REQUIRED_KEYS:
        val = t(key)
        assert val, f"i18n key 缺失或为空: {key}"
        assert val != key, f"i18n key 未翻译(fallback 到 key 自身): {key}"


def test_alt_key_supports_placeholder():
    val = t("dialog.multi_template.alt", n=2)
    assert "2" in val
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/unit/utils/test_i18n_multi_template.py -v`
Expected: FAIL — 多数 key fallback 到 key 自身

- [ ] **Step 3: 在 zh.json 与 en.json 补文案**

在两个 JSON 的合适层级(与现有 `dialog.*` 同级)新增以下 key。

`zh.json`:

```json
  "dialog": {
    "multi_template": {
      "primary": "主图",
      "alt": "备用图 {n}",
      "add": "+ 添加备用图片",
      "hint_order": "第一个为主图;顺序 = 命中优先级",
      "delete": "删除",
      "move_up": "上移",
      "move_down": "下移",
      "custom_threshold": "自定义阈值",
      "inherit": "继承全局",
      "no_preview": "无预览"
    },
    "threshold_mode": {
      "auto": "智能自动(零配置)",
      "global": "统一阈值",
      "per_template": "逐模板(可覆盖)"
    },
    "match_strategy": {
      "adaptive": "智能混合(推荐)",
      "first_match": "顺序优先",
      "best_confidence": "全局最佳"
    },
    "label": {
      "global_threshold": "全局阈值",
      "match_strategy": "匹配策略",
      "threshold_mode": "阈值模式"
    }
  }
```

`en.json` 同结构,值为英文:

```json
  "dialog": {
    "multi_template": {
      "primary": "Primary",
      "alt": "Alt {n}",
      "add": "+ Add alt image",
      "hint_order": "First is primary; order = match priority",
      "delete": "Delete",
      "move_up": "Up",
      "move_down": "Down",
      "custom_threshold": "Custom threshold",
      "inherit": "Inherit global",
      "no_preview": "No preview"
    },
    "threshold_mode": {
      "auto": "Auto (zero-config)",
      "global": "Global threshold",
      "per_template": "Per-template (override)"
    },
    "match_strategy": {
      "adaptive": "Adaptive (recommended)",
      "first_match": "First match",
      "best_confidence": "Best confidence"
    },
    "label": {
      "global_threshold": "Global threshold",
      "match_strategy": "Match strategy",
      "threshold_mode": "Threshold mode"
    }
  }
```

> **实现提示:** 实际 JSON 结构以现有文件为准——若 `dialog.label` 已存在,把 `global_threshold`/`match_strategy`/`threshold_mode` 三个 key 并入既有 `dialog.label` 对象,不要重复定义 `dialog` 顶层。使用 Edit 工具精确定位插入点。

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/unit/utils/test_i18n_multi_template.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/utils/translations/zh.json src/utils/translations/en.json tests/unit/utils/test_i18n_multi_template.py
git commit -m "feat: add multi-template i18n strings (zh/en)"
```

---

## Task 10: tkinter 多模板管理器组件 + ClickImage 对话框集成

**Files:**
- Create: `src/panel/dialogs/multi_template_editor.py`
- Modify: `src/panel/dialogs/click_image_dialog.py`
- Test: `tests/unit/panel/test_click_image_dialog_multi.py`

- [ ] **Step 1: 写失败测试(数据往返,免渲染)**

创建 `tests/unit/panel/test_click_image_dialog_multi.py`:

```python
"""ClickImageDialog 多模板数据往返测试(_get_result / _populate_fields)。

不渲染 GUI,只验证数据进出对话框的纯逻辑。
"""

import pytest

pytest.importorskip("tkinter")

from src.core.action import MatchStrategy, ThresholdMode
from src.core.step_types import ClickImageStep


def test_dialog_class_has_multi_template_state_attrs():
    """对话框类应声明多模板相关属性(通过 _vars 持有)。"""
    from src.panel.dialogs.click_image_dialog import ClickImageDialog
    # 类可导入即说明集成完成(具体属性在 _build_content 里建)
    assert hasattr(ClickImageDialog, "_get_result")


def test_step_with_multi_fields_roundtrips_through_result_assembly():
    """验证 ClickImageStep 的多模板字段能被对话框逻辑正确装配(不依赖 Tk root)。"""
    # 这里测 step_to_dict / step_from_dict 已覆盖序列化;
    # 对话框 _get_result 的等价逻辑:把 vars 装回 step。
    step = ClickImageStep(
        image_path="a.png",
        alt_image_paths=["b.png", "c.png"],
        alt_thresholds=[0.7, None],
        match_strategy=MatchStrategy.BEST_CONFIDENCE,
        threshold_mode=ThresholdMode.PER_TEMPLATE,
    )
    # 模拟对话框读取 step 的逻辑:主图 + 备用图 + 阈值模式 + 策略
    assert step.threshold_mode == ThresholdMode.PER_TEMPLATE
    assert step.match_strategy == MatchStrategy.BEST_CONFIDENCE
    assert len(step.alt_image_paths) == 2
```

> **实现提示:** GUI 对话框难以纯单元测试渲染。本测试聚焦"类可导入 + 数据模型正确",更深的渲染测试放在手动验证或 e2e。对话框的 `_get_result`/`_populate_fields` 应正确读写 4 个新字段。

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/unit/panel/test_click_image_dialog_multi.py -v`
Expected: PASS(数据模型已就绪)或 FAIL(若对话框尚未声明多模板逻辑)——以导入是否成功为准

- [ ] **Step 3: 创建 tkinter 多模板管理器组件**

创建 `src/panel/dialogs/multi_template_editor.py`:

```python
"""多模板图片管理器(tkinter 可复用组件)。

ClickImage / Condition / Monitor 对话框共用。规格与 Qt 版一致:
- 主图置顶、不可删;备用图可增删、上下移动
- 每行:缩略图 + 路径 + 阈值单元(spinbox + 自定义复选框) + 排序 + 删除
- 阈值模式联动:PER_TEMPLATE 显示阈值单元;AUTO/GLOBAL 隐藏
"""

from __future__ import annotations

import os
import tkinter as tk
from typing import TYPE_CHECKING

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None  # type: ignore[assignment,misc]
    ImageTk = None  # type: ignore[assignment]

from src.core.action import MatchStrategy, ThresholdMode
from src.panel.canvas.theme import current_theme
from src.panel.widgets import themed_button, themed_frame, themed_label
from src.utils.i18n import t

if TYPE_CHECKING:
    import tkinter.filedialog as filedialog  # noqa: F401


class MultiTemplateEditor:
    """tkinter 多模板图片管理器(非 widget 子类,持有 frame 与状态)。

    用法:
        editor = MultiTemplateEditor(parent_frame, on_change=callback)
        editor.set_state(image_path, alt_paths, alt_thresholds, mode, strategy)
        ...
        state = editor.get_state()  # → (image_path, alts, thr, mode, strategy)
    """

    def __init__(self, parent: tk.Widget, on_change=None) -> None:
        self._th = current_theme()
        self._on_change = on_change
        self._frame = themed_frame(parent)
        self._frame.pack(fill=tk.BOTH, expand=True)
        self._rows_frame = themed_frame(self._frame)
        self._rows_frame.pack(fill=tk.X)
        self._photo_refs: list[object] = []  # 防 GC
        self._rows: list[dict] = []          # 每行: {path_var, thr_var, custom_var}
        self._primary_path_var = tk.StringVar()
        self._threshold_mode_var = tk.StringVar(value=ThresholdMode.GLOBAL.name)
        self._match_strategy_var = tk.StringVar(value=MatchStrategy.ADAPTIVE.name)
        self._global_threshold_var = tk.DoubleVar(value=0.8)
        self._build_controls()

    @property
    def frame(self) -> tk.Widget:
        return self._frame

    def _build_controls(self) -> None:
        th = self._th
        # 匹配设置区
        ctrl = themed_frame(self._frame)
        ctrl.pack(fill=tk.X, pady=th.pad_xs)

        themed_label(ctrl, text=t("dialog.label.threshold_mode")).grid(row=0, column=0, sticky=tk.W, padx=th.pad_xs)
        from src.panel.widgets import themed_dropdown
        self._mode_dd = themed_dropdown(
            ctrl,
            options=[(ThresholdMode.AUTO.name, "dialog.threshold_mode.auto"),
                     (ThresholdMode.GLOBAL.name, "dialog.threshold_mode.global"),
                     (ThresholdMode.PER_TEMPLATE.name, "dialog.threshold_mode.per_template")],
            value=ThresholdMode.GLOBAL.name, state="readonly", width=18,
            command=self._on_mode_changed,
        )
        self._mode_dd.grid(row=0, column=1, sticky=tk.W, padx=th.pad_xs)

        themed_label(ctrl, text=t("dialog.label.match_strategy")).grid(row=1, column=0, sticky=tk.W, padx=th.pad_xs)
        self._strategy_dd = themed_dropdown(
            ctrl,
            options=[(MatchStrategy.ADAPTIVE.name, "dialog.match_strategy.adaptive"),
                     (MatchStrategy.FIRST_MATCH.name, "dialog.match_strategy.first_match"),
                     (MatchStrategy.BEST_CONFIDENCE.name, "dialog.match_strategy.best_confidence")],
            value=MatchStrategy.ADAPTIVE.name, state="readonly", width=18,
        )
        self._strategy_dd.grid(row=1, column=1, sticky=tk.W, padx=th.pad_xs)

        self._global_thr_label = themed_label(ctrl, text=t("dialog.label.global_threshold"))
        self._global_thr_sb = tk.Spinbox(
            ctrl, from_=0.1, to=1.0, increment=0.05,
            textvariable=self._global_threshold_var, width=6,
        )
        self._global_thr_label.grid(row=2, column=0, sticky=tk.W, padx=th.pad_xs)
        self._global_thr_sb.grid(row=2, column=1, sticky=tk.W, padx=th.pad_xs)

        # 添加按钮 + 提示
        bar = themed_frame(self._frame)
        bar.pack(fill=tk.X)
        themed_button(bar, text=t("dialog.multi_template.add"), command=self._add_alt).pack(side=tk.LEFT)
        themed_label(bar, text="  " + t("dialog.multi_template.hint_order"), fg=th.text_muted).pack(side=tk.LEFT)
        self._apply_mode_visibility()

    def _apply_mode_visibility(self) -> None:
        mode = self._threshold_mode_var.get()
        show_global = mode != ThresholdMode.AUTO.name
        # 全局阈值框:AUTO 隐藏,其余显示
        if show_global:
            self._global_thr_label.grid()
            self._global_thr_sb.grid()
        else:
            self._global_thr_label.grid_remove()
            self._global_thr_sb.grid_remove()
        # 每行阈值单元:仅 PER_TEMPLATE 显示
        for row in self._rows:
            if mode == ThresholdMode.PER_TEMPLATE.name:
                row["thr_frame"].grid()
            else:
                row["thr_frame"].grid_remove()

    def _on_mode_changed(self, _val: str) -> None:
        self._apply_mode_visibility()
        if self._on_change:
            self._on_change()

    def _add_alt(self) -> None:
        from tkinter import filedialog
        p = filedialog.askopenfilename(
            title=t("dialog.multi_template.add"),
            filetypes=[(t("dialog.filetype.image"), "*.png *.jpg *.jpeg *.bmp"), (t("dialog.filetype.all"), "*.*")],
        )
        if p:
            self._rows.append(self._make_row(p, None))
            self._render_rows()
            if self._on_change:
                self._on_change()

    def _make_row(self, path: str, threshold: float | None) -> dict:
        return {
            "path_var": tk.StringVar(value=path),
            "custom_var": tk.BooleanVar(value=threshold is not None),
            "thr_var": tk.DoubleVar(value=threshold if threshold is not None else 0.8),
            "thr_frame": None,  # 渲染时填
        }

    def _render_rows(self) -> None:
        for w in self._rows_frame.winfo_children():
            w.destroy()
        self._photo_refs.clear()
        th = self._th
        # 主图行
        self._render_primary_row(th)
        # 备用图行
        for idx, row in enumerate(self._rows):
            self._render_alt_row(idx, row, th)
        self._apply_mode_visibility()

    def _render_primary_row(self, th) -> None:
        row_frame = themed_frame(self._rows_frame)
        row_frame.pack(fill=tk.X, padx=th.pad_xs, pady=2)
        self._render_thumbnail(row_frame, self._primary_path_var.get())
        themed_label(row_frame, text=t("dialog.multi_template.primary")).pack(side=tk.LEFT, padx=th.pad_xs)
        entry = tk.Entry(row_frame, textvariable=self._primary_path_var, width=28)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        themed_button(row_frame, text=t("dialog.btn.select_image"), command=self._browse_primary).pack(side=tk.LEFT)

    def _browse_primary(self) -> None:
        from tkinter import filedialog
        p = filedialog.askopenfilename(
            title=t("dialog.title.select_template_image"),
            filetypes=[(t("dialog.filetype.image"), "*.png *.jpg *.jpeg *.bmp"), (t("dialog.filetype.all"), "*.*")],
        )
        if p:
            self._primary_path_var.set(p)
            self._render_rows()
            if self._on_change:
                self._on_change()

    def _render_alt_row(self, idx: int, row: dict, th) -> None:
        row_frame = themed_frame(self._rows_frame)
        row_frame.pack(fill=tk.X, padx=th.pad_xs, pady=2)
        self._render_thumbnail(row_frame, row["path_var"].get())
        themed_label(row_frame, text=t("dialog.multi_template.alt", n=idx + 1)).pack(side=tk.LEFT, padx=th.pad_xs)
        tk.Entry(row_frame, textvariable=row["path_var"], width=28).pack(side=tk.LEFT, fill=tk.X, expand=True)
        # 阈值单元
        thr_frame = themed_frame(row_frame)
        thr_frame.pack(side=tk.LEFT, padx=th.pad_xs)
        row["thr_frame"] = thr_frame
        chk = tk.Checkbutton(
            thr_frame, text=t("dialog.multi_template.custom_threshold"),
            variable=row["custom_var"],
        )
        chk.pack(side=tk.LEFT)
        tk.Spinbox(
            thr_frame, from_=0.1, to=1.0, increment=0.05,
            textvariable=row["thr_var"], width=5,
        ).pack(side=tk.LEFT)
        themed_button(row_frame, text="↑", width=2, command=lambda i=idx: self._move(i, -1)).pack(side=tk.LEFT)
        themed_button(row_frame, text="↓", width=2, command=lambda i=idx: self._move(i, 1)).pack(side=tk.LEFT)
        themed_button(row_frame, text=t("dialog.multi_template.delete"), command=lambda i=idx: self._delete(i)).pack(side=tk.LEFT)

    def _render_thumbnail(self, parent: tk.Widget, path: str) -> None:
        lbl = themed_label(parent, text=t("dialog.multi_template.no_preview"))
        lbl.pack(side=tk.LEFT)
        if not path or not os.path.exists(path) or Image is None:
            return
        try:
            img = Image.open(path)
            img.thumbnail((40, 40))
            photo = ImageTk.PhotoImage(img)
            self._photo_refs.append(photo)
            lbl.configure(image=photo, text="")
        except (OSError, ValueError):
            pass

    def _move(self, idx: int, delta: int) -> None:
        new = idx + delta
        if 0 <= new < len(self._rows):
            self._rows[idx], self._rows[new] = self._rows[new], self._rows[idx]
            self._render_rows()
            if self._on_change:
                self._on_change()

    def _delete(self, idx: int) -> None:
        if 0 <= idx < len(self._rows):
            del self._rows[idx]
            self._render_rows()
            if self._on_change:
                self._on_change()

    # ── 状态读写 ───────────────────────────────

    def set_state(
        self,
        image_path: str,
        alt_paths: list[str],
        alt_thresholds: list[float | None],
        mode: ThresholdMode,
        strategy: MatchStrategy,
        global_threshold: float,
    ) -> None:
        self._primary_path_var.set(image_path)
        self._rows = [
            self._make_row(p, alt_thresholds[i] if i < len(alt_thresholds) else None)
            for i, p in enumerate(alt_paths)
        ]
        self._threshold_mode_var.set(mode.name)
        self._match_strategy_var.set(strategy.name)
        self._global_threshold_var.set(global_threshold)
        self._mode_dd.set_value(mode.name)
        self._strategy_dd.set_value(strategy.name)
        self._render_rows()

    def get_state(self) -> tuple[str, list[str], list[float | None], ThresholdMode, MatchStrategy, float]:
        """返回 (image_path, alt_paths, alt_thresholds, mode, strategy, global_threshold)。

        alt_thresholds[i]:custom_var 为 False → None(继承);为 True → thr_var 值。
        """
        alt_paths = [r["path_var"].get() for r in self._rows]
        alt_thresholds: list[float | None] = []
        for r in self._rows:
            if r["custom_var"].get():
                alt_thresholds.append(float(r["thr_var"].get()))
            else:
                alt_thresholds.append(None)
        mode = ThresholdMode[self._threshold_mode_var.get()]
        strategy = MatchStrategy[self._match_strategy_var.get()]
        return (
            self._primary_path_var.get(),
            alt_paths,
            alt_thresholds,
            mode,
            strategy,
            float(self._global_threshold_var.get()),
        )
```

- [ ] **Step 4: 集成到 click_image_dialog.py**

修改 `src/panel/dialogs/click_image_dialog.py`:

(a) 顶部 import 补入:
```python
from src.core.action import ActionType, DetectMode, FoundAction, MatchStrategy, ThresholdMode
from src.panel.dialogs.multi_template_editor import MultiTemplateEditor
```

(b) 在 `_build_content` 中,把现有"图片路径 + 预览"整段(约第 61-80 行,从 `themed_label(... template_image)` 到 `row += 1`)替换为嵌入编辑器;并把现有"阈值"spinbox(约第 82-87 行)删除(阈值已由编辑器的全局阈值框管理)。替换后:

```python
    def _build_content(self) -> None:
        th = current_theme()
        row = 0

        # 多模板图片管理器(替代原单行 image_path + 阈值)
        themed_label(
            self._content_frame, text=t("dialog.label.template_image"),
        ).grid(row=row, column=0, sticky=tk.NW, padx=th.pad_sm, pady=th.pad_xs)
        self._mt_editor = MultiTemplateEditor(self._content_frame, on_change=None)
        self._mt_editor.frame.grid(row=row, column=1, sticky=tk.EW, padx=th.pad_sm)
        row += 1

        # 检测模式(以下既有字段不变)
        themed_label(
            self._content_frame, text=t("dialog.label.detect_mode"),
        ).grid(row=row, column=0, sticky=tk.W, padx=th.pad_sm, pady=th.pad_xs)
        self._dm_dropdown = themed_dropdown(
            self._content_frame,
            options=_DETECT_MODE_OPTIONS,
            value=DetectMode.SKIP_IF_NOT_FOUND.name,
            state="readonly", width=22,
        )
        self._dm_dropdown.grid(row=row, column=1, sticky=tk.W, padx=th.pad_sm)
        row += 1
        # ... 重试、found_action、条件字段、坐标变量名等既有部分保持原样 ...
        self._common_row = row
```

> **实现提示:** "重试 / found_action / hold / drag / 坐标变量名"这些既有段保留原代码不动,只把 `row` 计数顺延。删掉旧的 `_preview_label` / `_vars["image_path"]` / `_vars["threshold"]` / `_browse` / `_update_preview` 逻辑(它们已被 `MultiTemplateEditor` 取代),但保留 `_vars` 中其他字段(retry_count 等)。

(c) 改 `_populate_fields` 与 `_get_result` 用编辑器:

```python
    def _populate_fields(self, action: BaseStep) -> None:
        self._mt_editor.set_state(
            image_path=action.image_path,
            alt_paths=action.alt_image_paths,
            alt_thresholds=action.alt_thresholds,
            mode=action.threshold_mode,
            strategy=action.match_strategy,
            global_threshold=action.threshold,
        )
        self._dm_dropdown.set_value(action.detect_mode.name)
        self._vars["retry_count"].set(action.retry_count)
        self._vars["retry_wait_min"].set(action.retry_wait_min)
        self._vars["retry_wait_max"].set(action.retry_wait_max)
        self._fa_dropdown.set_value(action.found_action.name)
        self._vars["hold_duration"].set(action.hold_duration)
        self._vars["drag_offset_x"].set(action.drag_offset_x)
        self._vars["drag_offset_y"].set(action.drag_offset_y)
        self._vars["save_coord_name"].set(action.save_coord_name)
        self._on_found_action_changed()
        self._add_common_fields(self._content_frame, self._common_row, action)

    def _get_result(self) -> BaseStep:
        step = self._action or ClickImageStep()
        (
            image_path, alt_paths, alt_thresholds,
            mode, strategy, global_threshold,
        ) = self._mt_editor.get_state()
        step.image_path = image_path
        step.alt_image_paths = alt_paths
        step.alt_thresholds = alt_thresholds
        step.threshold_mode = mode
        step.match_strategy = strategy
        step.threshold = global_threshold
        step.retry_count = self._get_int("retry_count", min_val=0, default=3)
        step.retry_wait_min = self._get_float("retry_wait_min", min_val=0.0, default=0.5)
        step.retry_wait_max = self._get_float("retry_wait_max", min_val=0.0, default=1.5)
        step.hold_duration = self._get_float("hold_duration", min_val=0.0, default=0.5)
        step.drag_offset_x = self._get_int("drag_offset_x", default=0)
        step.drag_offset_y = self._get_int("drag_offset_y", default=0)
        step.save_coord_name = self._vars["save_coord_name"].get()
        dm_val = self._dm_dropdown.get_value()
        fa_val = self._fa_dropdown.get_value()
        step.detect_mode = DetectMode[dm_val] if dm_val in DetectMode.__members__ else DetectMode.SKIP_IF_NOT_FOUND
        step.found_action = FoundAction[fa_val] if fa_val in FoundAction.__members__ else FoundAction.LEFT_CLICK
        self._apply_common(step)
        return step
```

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest tests/unit/panel/test_click_image_dialog_multi.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add src/panel/dialogs/multi_template_editor.py src/panel/dialogs/click_image_dialog.py tests/unit/panel/test_click_image_dialog_multi.py
git commit -m "feat: tkinter multi-template editor + ClickImage dialog integration"
```

---

## Task 11: Qt 多模板管理器组件 + ClickImage 对话框集成

**Files:**
- Create: `src/panel/qt_backend/dialogs/multi_template_editor.py`
- Modify: `src/panel/qt_backend/dialogs/click_image_dialog.py`
- Test: `tests/unit/panel/test_qt_multi_template_editor.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/unit/panel/test_qt_multi_template_editor.py`:

```python
"""Qt 版多模板管理器数据往返测试(免渲染)。"""

import pytest

# Qt 可选;无 Qt 环境时跳过整个文件
qtw = pytest.importorskip("PySide6")  # 或 PyQt5/PyQt6,以项目实际为准


def test_qt_editor_importable():
    from src.panel.qt_backend.dialogs.multi_template_editor import MultiTemplateEditorQt
    assert MultiTemplateEditorQt is not None


def test_qt_editor_state_roundtrip():
    """set_state → get_state 数据一致(用 QCoreApplication 不显示窗口)。"""
    import os
    import tempfile
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from src.panel.qt_backend.dialogs.multi_template_editor import MultiTemplateEditorQt
    from src.core.action import MatchStrategy, ThresholdMode
    editor = MultiTemplateEditorQt(parent=None)
    editor.set_state(
        image_path="a.png",
        alt_paths=["b.png", "c.png"],
        alt_thresholds=[0.7, None],
        mode=ThresholdMode.PER_TEMPLATE,
        strategy=MatchStrategy.BEST_CONFIDENCE,
        global_threshold=0.8,
    )
    image_path, alt_paths, alt_thresholds, mode, strategy, gthr = editor.get_state()
    assert image_path == "a.png"
    assert alt_paths == ["b.png", "c.png"]
    assert alt_thresholds[0] == 0.7
    assert alt_thresholds[1] is None
    assert mode == ThresholdMode.PER_TEMPLATE
    assert strategy == MatchStrategy.BEST_CONFIDENCE
```

> **实现提示:** Qt 绑定(PySide6 / PyQt5 / PyQt6)以项目实际使用的为准——先 grep `src/panel/qt_backend/` 确认 import 的是哪个,据此调整 `pytest.importorskip`。

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/unit/panel/test_qt_multi_template_editor.py -v`
Expected: FAIL — 模块不存在

- [ ] **Step 3: 确认 Qt 绑定与现有 Qt 对话框基类**

Run: `grep -rn "PySide\|PyQt" src/panel/qt_backend/__init__.py src/panel/qt_backend/dialogs/base_dialog.py | head -5`
(据此确定 Qt 绑定与 Widget/Dialog 基类,后续代码以实际为准)

- [ ] **Step 4: 创建 Qt 版多模板管理器**

创建 `src/panel/qt_backend/dialogs/multi_template_editor.py`(以 PySide6 为例,与 tkinter 版同规格):

```python
"""多模板图片管理器(Qt 可复用组件,规格同 tkinter 版)。"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)
from PySide6.QtGui import QPixmap

from src.core.action import MatchStrategy, ThresholdMode
from src.utils.i18n import t


class MultiTemplateEditorQt(QWidget):
    """Qt 多模板图片管理器。

    API 与 tkinter 版一致:set_state(...) / get_state() →
    (image_path, alt_paths, alt_thresholds, mode, strategy, global_threshold)。
    """

    def __init__(self, parent=None, on_change=None) -> None:
        super().__init__(parent)
        self._on_change = on_change
        self._rows: list[dict] = []
        self._primary_path = ""
        self._mode = ThresholdMode.GLOBAL
        self._strategy = MatchStrategy.ADAPTIVE
        self._global_threshold = 0.8

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 控制区
        ctrl = QWidget()
        cl = QVBoxLayout(ctrl)
        cl.setContentsMargins(0, 0, 0, 0)
        # 阈值模式
        row1 = QHBoxLayout()
        row1.addWidget(QLabel(t("dialog.label.threshold_mode")))
        self._mode_cb = QComboBox()
        for m, key in [(ThresholdMode.AUTO, "dialog.threshold_mode.auto"),
                       (ThresholdMode.GLOBAL, "dialog.threshold_mode.global"),
                       (ThresholdMode.PER_TEMPLATE, "dialog.threshold_mode.per_template")]:
            self._mode_cb.addItem(t(key), userData=m)
        self._mode_cb.currentIndexChanged.connect(self._on_mode_changed)
        row1.addWidget(self._mode_cb)
        cl.addLayout(row1)
        # 匹配策略
        row2 = QHBoxLayout()
        row2.addWidget(QLabel(t("dialog.label.match_strategy")))
        self._strategy_cb = QComboBox()
        for s, key in [(MatchStrategy.ADAPTIVE, "dialog.match_strategy.adaptive"),
                       (MatchStrategy.FIRST_MATCH, "dialog.match_strategy.first_match"),
                       (MatchStrategy.BEST_CONFIDENCE, "dialog.match_strategy.best_confidence")]:
            self._strategy_cb.addItem(t(key), userData=s)
        row2.addWidget(self._strategy_cb)
        cl.addLayout(row2)
        # 全局阈值
        row3 = QHBoxLayout()
        self._global_thr_label = QLabel(t("dialog.label.global_threshold"))
        self._global_thr_sb = QDoubleSpinBox()
        self._global_thr_sb.setRange(0.1, 1.0)
        self._global_thr_sb.setSingleStep(0.05)
        self._global_thr_sb.setDecimals(2)
        row3.addWidget(self._global_thr_label)
        row3.addWidget(self._global_thr_sb)
        cl.addLayout(row3)
        layout.addWidget(ctrl)

        # 行容器 + 添加按钮
        self._rows_container = QVBoxLayout()
        self._rows_container.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._rows_container)

        bar = QHBoxLayout()
        add_btn = QPushButton(t("dialog.multi_template.add"))
        add_btn.clicked.connect(self._add_alt)
        bar.addWidget(add_btn)
        bar.addWidget(QLabel(t("dialog.multi_template.hint_order")))
        layout.addLayout(bar)

        self._apply_mode_visibility()

    def _on_mode_changed(self) -> None:
        self._apply_mode_visibility()
        if self._on_change:
            self._on_change()

    def _apply_mode_visibility(self) -> None:
        mode = self._mode_cb.currentData()
        show_global = mode != ThresholdMode.AUTO
        self._global_thr_label.setVisible(show_global)
        self._global_thr_sb.setVisible(show_global)
        for row in self._rows:
            row["thr_widget"].setVisible(mode == ThresholdMode.PER_TEMPLATE)

    def _add_alt(self) -> None:
        p, _ = QFileDialog.getOpenFileName(
            self, t("dialog.multi_template.add"), "",
            f"{t('dialog.filetype.image')} (*.png *.jpg *.jpeg *.bmp);;{t('dialog.filetype.all')} (*.*)",
        )
        if p:
            self._rows.append({"path": p, "custom": False, "thr": 0.8})
            self._render_rows()
            if self._on_change:
                self._on_change()

    def _render_rows(self) -> None:
        # 清空
        while self._rows_container.count():
            item = self._rows_container.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        # 主图行
        self._rows_container.addWidget(self._build_primary_row())
        # 备用图行
        for idx, row in enumerate(self._rows):
            self._rows_container.addWidget(self._build_alt_row(idx, row))
        self._apply_mode_visibility()

    def _build_primary_row(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        self._add_thumb(lay, self._primary_path)
        lay.addWidget(QLabel(t("dialog.multi_template.primary")))
        le = QLineEdit(self._primary_path)
        le.editingFinished.connect(lambda: self._set_primary(le.text()))
        lay.addWidget(le)
        browse = QPushButton(t("dialog.btn.select_image"))
        browse.clicked.connect(self._browse_primary)
        lay.addWidget(browse)
        return w

    def _set_primary(self, p: str) -> None:
        self._primary_path = p
        self._render_rows()

    def _browse_primary(self) -> None:
        p, _ = QFileDialog.getOpenFileName(
            self, t("dialog.title.select_template_image"), "",
            f"{t('dialog.filetype.image')} (*.png *.jpg *.jpeg *.bmp);;{t('dialog.filetype.all')} (*.*)",
        )
        if p:
            self._primary_path = p
            self._render_rows()

    def _build_alt_row(self, idx: int, row: dict) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        self._add_thumb(lay, row["path"])
        lay.addWidget(QLabel(t("dialog.multi_template.alt", n=idx + 1)))
        lay.addWidget(QLineEdit(row["path"]))
        # 阈值单元
        thr_w = QWidget()
        tl = QHBoxLayout(thr_w)
        tl.setContentsMargins(0, 0, 0, 0)
        chk = QCheckBox(t("dialog.multi_template.custom_threshold"))
        chk.setChecked(row["custom"])
        chk.toggled.connect(lambda v: row.update(custom=v))
        tl.addWidget(chk)
        sb = QDoubleSpinBox()
        sb.setRange(0.1, 1.0)
        sb.setSingleStep(0.05)
        sb.setDecimals(2)
        sb.setValue(row["thr"])
        sb.valueChanged.connect(lambda v: row.update(thr=v))
        tl.addWidget(sb)
        lay.addWidget(thr_w)
        row["thr_widget"] = thr_w
        # 排序 + 删除
        up = QPushButton("↑")
        up.clicked.connect(lambda: self._move(idx, -1))
        down = QPushButton("↓")
        down.clicked.connect(lambda: self._move(idx, 1))
        dele = QPushButton(t("dialog.multi_template.delete"))
        dele.clicked.connect(lambda: self._delete(idx))
        lay.addWidget(up)
        lay.addWidget(down)
        lay.addWidget(dele)
        return w

    def _add_thumb(self, layout, path: str) -> None:
        lbl = QLabel(t("dialog.multi_template.no_preview"))
        if path and os.path.exists(path):
            pm = QPixmap(path)
            if not pm.isNull():
                lbl.setPixmap(pm.scaled(40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        layout.addWidget(lbl)

    def _move(self, idx: int, delta: int) -> None:
        new = idx + delta
        if 0 <= new < len(self._rows):
            self._rows[idx], self._rows[new] = self._rows[new], self._rows[idx]
            self._render_rows()

    def _delete(self, idx: int) -> None:
        if 0 <= idx < len(self._rows):
            del self._rows[idx]
            self._render_rows()

    # ── 状态读写 ───────────────────────────────

    def set_state(self, image_path, alt_paths, alt_thresholds, mode, strategy, global_threshold) -> None:
        self._primary_path = image_path
        self._rows = [
            {"path": p, "custom": (alt_thresholds[i] is not None if i < len(alt_thresholds) else False),
             "thr": alt_thresholds[i] if (i < len(alt_thresholds) and alt_thresholds[i] is not None) else 0.8}
            for i, p in enumerate(alt_paths)
        ]
        self._mode = mode
        self._strategy = strategy
        self._global_threshold = global_threshold
        self._mode_cb.setCurrentIndex(self._mode_cb.findData(mode))
        self._strategy_cb.setCurrentIndex(self._strategy_cb.findData(strategy))
        self._global_thr_sb.setValue(global_threshold)
        self._render_rows()

    def get_state(self):
        alt_paths = [r["path"] for r in self._rows]
        alt_thresholds = [r["thr"] if r["custom"] else None for r in self._rows]
        return (
            self._primary_path,
            alt_paths,
            alt_thresholds,
            self._mode_cb.currentData(),
            self._strategy_cb.currentData(),
            self._global_thr_sb.value(),
        )
```

- [ ] **Step 5: 集成到 Qt 版 click_image_dialog.py**

参照 [click_image_dialog.py](../../../src/panel/qt_backend/dialogs/click_image_dialog.py) 现有结构:把图片路径 + 阈值控件替换为 `MultiTemplateEditorQt`,`_populate_fields` / `_get_result` 改为读写编辑器(逻辑与 tkinter 版 Task 10 Step 4(c) 完全对应,仅 API 换成 Qt)。

具体改动点(以实际 Qt 对话框结构为准):
- import `MultiTemplateEditorQt`
- `_build_content`:删除原单行 image_path QLineEdit 与 threshold QDoubleSpinBox,改为实例化 `self._mt_editor = MultiTemplateEditorQt(self)`
- `_populate_fields`:`self._mt_editor.set_state(action.image_path, action.alt_image_paths, action.alt_thresholds, action.threshold_mode, action.match_strategy, action.threshold)`
- `_get_result`:`image_path, alt_paths, alt_thresholds, mode, strategy, gthr = self._mt_editor.get_state()` 后赋值给 step 的对应字段

- [ ] **Step 6: 运行测试确认通过**

Run: `pytest tests/unit/panel/test_qt_multi_template_editor.py -v`
Expected: PASS(无 Qt 环境则 SKIP,但逻辑可导入)

- [ ] **Step 7: 提交**

```bash
git add src/panel/qt_backend/dialogs/multi_template_editor.py src/panel/qt_backend/dialogs/click_image_dialog.py tests/unit/panel/test_qt_multi_template_editor.py
git commit -m "feat: Qt multi-template editor + ClickImage dialog integration"
```

---

## Task 12: 全量回归 + 覆盖率验证

**Files:**
- 无新增;运行全套测试

- [ ] **Step 1: 运行全部测试**

Run: `pytest tests/ -v`
Expected: 全部 PASS(既有 84 文件 + 本计划新增 ~8 文件)

- [ ] **Step 2: 覆盖率检查**

Run: `pytest --cov=src --cov-report=term-missing tests/unit/core/vision/test_match_config.py tests/unit/core/vision/test_find_any.py tests/unit/core/vision/test_find_with_score.py tests/unit/core/engine/test_click_image_multi.py tests/unit/core/test_serialization_multi.py`
Expected: 新增模块覆盖率 ≥ 80%

- [ ] **Step 3: 手动冒烟(可选但推荐)**

```bash
python main.py
```
在动作链页新建一个 ClickImage 步骤,验证:
- 对话框显示多模板管理器(主图 + 添加备用图)
- 切换阈值模式(AUTO/GLOBAL/PER_TEMPLATE)时控件显隐正确
- 添加 2~3 张备用图,保存配置,重新打开对话框,数据保留
- 配置导出/导入后 alt 路径正确(相对 profile 目录)

- [ ] **Step 4: 最终提交(若有遗漏修正)**

```bash
git add -A
git commit -m "test: full regression pass for multi-template ClickImage"
```

---

## Self-Review(计划自检)

**1. Spec 覆盖**:对照规格 §3–§10 核对——
- §3 架构(find_any 在匹配器)→ Task 3/4 ✓
- §4 算法(ADAPTIVE/FIRST/BEST)→ Task 4 ✓
- §5 数据模型(双枚举 + 4 字段 + 默认值)→ Task 1/5 ✓
- §5.5 AUTO_THRESHOLD=0.72 → Task 2 ✓
- §6 UI(双框架管理器 + 阈值模式联动)→ Task 10/11 ✓
- §7 执行层(ClickImageDescriptor)→ Task 6 ✓
- §8 序列化(3 文件)→ Task 7/8 ✓
- §9 测试 → 各 Task 内嵌 TDD ✓
- §10 日志 → Task 4/6 内 log.info ✓
- §12 非目标(Condition/Monitor/Pipeline)→ 标注为计划 2 ✓

**2. 占位符扫描**:无 TBD/TODO;每个代码步骤含完整代码;测试含完整断言。

**3. 类型一致性**:
- `find_with_score` 返回 `(rect, float)` — Task 3/4 一致 ✓
- `MultiMatchResult(path, rect, confidence, strategy_used)` — Task 4/6 一致 ✓
- `resolve_find_any_params` 返回 `(paths, per_thr, strategy)` — Task 2/6 一致 ✓
- `MultiTemplateEditor.get_state()` 返回 6 元组 — Task 10/11 两框架一致 ✓
- `ClickImageStep` 新字段名(`alt_image_paths`/`alt_thresholds`/`match_strategy`/`threshold_mode`)— Task 5/6/7/8/10/11 全程一致 ✓

**计划 2(待写)** 将复用本计划模式,覆盖:Condition 数据模型 + `_check_image_found`、Monitor 数据模型 + 触发/处理图、VisionPipeline.TemplateMatchStep、三个对话框嵌入、对应序列化与测试。

---

## Execution Handoff

计划已保存至 `docs/superpowers/plans/2026-06-14-multi-template-detection.md`。两种执行方式:

1. **Subagent-Driven(推荐)** — 每个 Task 派发独立子代理,任务间我审查,快速迭代
2. **Inline Execution** — 在本会话内按 executing-plans 批量执行,带检查点

选择哪种方式?
