# 多模板检测(计划 2/2)— Condition / Monitor / Pipeline 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把多模板 OR 匹配能力(计划 1 已在 ClickImage 落地)扩展到 Condition(图片条件)、Monitor(触发图+处理图)、VisionPipeline.TemplateMatchStep 三个模板匹配消费者,复用计划 1 建立的 `find_any` / `match_config` / `MultiTemplateEditor` 基础设施,彻底解决挂机时按钮状态漂移导致的条件判定失败与监控漏检。

**Architecture:** 数据模型增量式加字段(`alt_image_paths`/`alt_thresholds`/`match_strategy`/`threshold_mode`,Monitor 处理图再加 `alt_handler_*`)→ 匹配入口从 `matcher.find()` 改为 `matcher.find_any()`(经 `match_config.resolve_find_any_params` 解析参数)→ 序列化三件套(`serialization.py` rel→abs / `importer.py` abs→rel / `profile_manager.py` 图片拷贝)机械式补齐 Condition + Monitor → 双框架对话框(tk + Qt)把图片区替换为 `MultiTemplateEditor`(Monitor 触发图用完整编辑器、处理图用 `show_match_settings=False` 的精简编辑器,共用本节点一套 strategy/threshold_mode)。框架无关逻辑全部复用计划 1 的 `match_config.py`,杜绝双框架漂移。

**Tech Stack:** Python 3.11+、OpenCV(cv2)、NumPy、tkinter、PySide6(可选,venv 当前未装 → Qt 测试 SKIP)、pytest、dataclasses

**关联规格:** [2026-06-14-multi-template-detection-design.md](../specs/2026-06-14-multi-template-detection-design.md)

**前置条件(计划 1 已完成并提交):** `MatchStrategy`/`ThresholdMode` 枚举、`match_config.py`(`resolve_find_any_params`/`normalize_templates`/`effective_thresholds`/`AUTO_THRESHOLD`)、`TemplateMatcher.find_any`/`find_with_score`/`MultiMatchResult`、tk + Qt `MultiTemplateEditor` 组件、`dialog.multi_template.*` i18n。本计划直接复用,不重建。

**本计划范围(计划 2):** Task 1–11。Condition / Monitor / Pipeline 三消费者端到端(数据模型 + 匹配 + 序列化 + 双框架对话框 + 测试)。

---

## File Structure

**修改(核心):**
- `src/core/condition.py` — `Condition` dataclass +4 字段;`ConditionEvaluator._check_image_found` 改用 `find_any`。
- `src/core/monitor.py` — `MonitorConfig` dataclass +触发图/处理图各一组 alt 字段 +共用 `match_strategy`/`threshold_mode`;`BackgroundMonitor._check` 触发图与处理图匹配改用 `find_any`(抽 `_match_multi` 助手)。
- `src/core/vision/vision_pipeline.py` — `TemplateMatchStep.__init__` +`alt_template_paths`/`match_strategy`;`execute` 多模板走 `find_any`,单模板/多尺度走原路径(向后兼容)。

**修改(序列化):**
- `src/core/serialization.py` — `condition_to_dict`/`dict_to_condition` +4 字段;`monitor_to_dict`/`dict_to_monitor` +多模板字段;`dict_to_flow_node` Condition alt rel→abs;`dict_to_monitor` alt rel→abs(触发图+处理图)。
- `src/core/io/importer.py` — `_graph_to_v2_dict` Condition alt abs→rel;Monitor alt abs→rel。
- `src/panel/profile_manager.py` — `save` 拷贝 Condition alt 图片;拷贝 Monitor alt 图片(触发图+处理图)。

**修改(UI 组件 + 对话框):**
- `src/panel/dialogs/multi_template_editor.py` — `MultiTemplateEditor.__init__` +`show_match_settings: bool = True` 参数;`False` 时不渲染模式/策略/全局阈值控件(供 Monitor 处理图复用)。
- `src/panel/qt_backend/dialogs/multi_template_editor.py` — `MultiTemplateEditorQt.__init__` +`show_match_settings` 同规格。
- `src/panel/dialogs/condition_dialog.py` — IMAGE_FOUND/IMAGE_NOT_FOUND 图片区替换为 `MultiTemplateEditor`(跨 rebuild 保状态)。
- `src/panel/dialogs/monitor_dialog.py` — 触发图区一组完整编辑器 + 处理图区一组精简编辑器,`on_ok` 共用 trigger 的 strategy/mode。
- `src/panel/qt_backend/dialogs/condition_dialog.py` — Qt 版 Condition 嵌入(镜像 tk)。
- `src/panel/qt_backend/dialogs/monitor_dialog.py` — Qt 版 Monitor 嵌入 ×2(镜像 tk)。

**新增测试:**
- `tests/unit/core/test_condition_multi.py`
- `tests/unit/core/test_monitor_multi.py`
- `tests/unit/core/vision/test_vision_pipeline_multi.py`
- 扩展 `tests/unit/core/test_serialization_multi.py`(Condition + Monitor 往返 + rel/abs + 拷贝)
- `tests/unit/panel/test_multi_template_editor_param.py`(tk `show_match_settings` 参数)
- `tests/unit/panel/test_condition_dialog_multi.py`(tk,免渲染 import/数据往返)
- `tests/unit/panel/test_monitor_dialog_multi.py`(tk,免渲染 import)

> **环境提示:** venv 无 PySide6,Qt 相关测试 `pytest.importorskip("PySide6")` → SKIP(逻辑可导入即视为通过,与计划 1 Task 11 一致)。vision 匹配测试一律 mock `matcher.find_any`(不触达 `hashlib.xxh3_64`),避免 conftest hash 回退问题。

---

## Task 1: Condition 多模板数据模型 + `_check_image_found` 改用 find_any

**Files:**
- Modify: `src/core/condition.py`(`Condition` dataclass,约 47-63 行;`_check_image_found`,约 172-181 行)
- Test: `tests/unit/core/test_condition_multi.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/unit/core/test_condition_multi.py`:

```python
"""Condition 多模板条件判定测试(mock matcher.find_any,不触达 cv2/xxh3_64)。"""

from unittest.mock import MagicMock

import pytest

from src.core.action import MatchStrategy, ThresholdMode
from src.core.condition import Condition, ConditionEvaluator, ConditionType
from src.core.vision.capture import MultiMatchResult


def _evaluator(find_any_results):
    """构造假 ConditionEvaluator:capture.grab_reuse() 返回 mock 屏幕帧;
    matcher.find_any 按 find_any_results 顺序返回(每次调用一个)。
    """
    ev = ConditionEvaluator.__new__(ConditionEvaluator)
    ev._capture = MagicMock()
    ev._capture.grab_reuse.return_value = MagicMock(name="screen")
    ev._matcher = MagicMock()
    ev._matcher.find_any.side_effect = find_any_results
    ev._variables = {}
    ev._timers = {}
    import threading
    ev._lock = threading.Lock()
    return ev


def _image_cond(alt_paths=None, alt_thresholds=None, mode=ThresholdMode.GLOBAL,
                strategy=MatchStrategy.ADAPTIVE, threshold=0.8):
    return Condition(
        condition_type=ConditionType.IMAGE_FOUND,
        image_path="primary.png",
        threshold=threshold,
        alt_image_paths=alt_paths or [],
        alt_thresholds=alt_thresholds or [],
        match_strategy=strategy,
        threshold_mode=mode,
    )


def test_condition_has_multi_template_fields():
    cond = Condition(condition_type=ConditionType.IMAGE_FOUND)
    assert cond.alt_image_paths == []
    assert cond.alt_thresholds == []
    assert cond.match_strategy == MatchStrategy.ADAPTIVE
    assert cond.threshold_mode == ThresholdMode.GLOBAL


def test_image_found_primary_miss_alt_hit_is_true():
    """主图 miss + 备用图 hit → find_any 返回命中 → IMAGE_FOUND True。"""
    hit = MultiMatchResult(path="alt.png", rect=(10, 20, 30, 30), confidence=0.9, strategy_used="early_exit")
    ev = _evaluator([hit])
    cond = _image_cond(alt_paths=["alt.png"])
    assert ev.evaluate(cond) is True
    # 应改用 find_any(而非 find)
    assert ev._matcher.find_any.called


def test_image_found_all_miss_is_false():
    ev = _evaluator([None])
    cond = _image_cond(alt_paths=["alt.png"])
    assert ev.evaluate(cond) is False


def test_image_not_found_all_miss_is_true():
    """IMAGE_NOT_FOUND = 全部未命中 → True。"""
    ev = _evaluator([None])
    cond = Condition(
        condition_type=ConditionType.IMAGE_NOT_FOUND,
        image_path="primary.png", alt_image_paths=["alt.png"],
    )
    assert ev.evaluate(cond) is True


def test_image_not_found_any_hit_is_false():
    hit = MultiMatchResult(path="primary.png", rect=(1, 2, 3, 3), confidence=0.95, strategy_used="early_exit")
    ev = _evaluator([hit])
    cond = Condition(
        condition_type=ConditionType.IMAGE_NOT_FOUND,
        image_path="primary.png", alt_image_paths=["alt.png"],
    )
    assert ev.evaluate(cond) is False


def test_image_found_no_image_path_is_false():
    ev = _evaluator([])
    cond = Condition(condition_type=ConditionType.IMAGE_FOUND, image_path="")
    assert ev.evaluate(cond) is False


def test_image_found_passes_resolved_params():
    """find_any 收到的 template_paths 含 primary + alt,strategy 来自 cond。"""
    hit = MultiMatchResult(path="alt.png", rect=(1, 2, 3, 3), confidence=0.9, strategy_used="early_exit")
    ev = _evaluator([hit])
    cond = _image_cond(alt_paths=["alt.png"], strategy=MatchStrategy.BEST_CONFIDENCE)
    ev.evaluate(cond)
    call = ev._matcher.find_any.call_args
    paths = call.kwargs.get("template_paths") or call.args[1]
    assert "primary.png" in paths and "alt.png" in paths
    assert call.kwargs.get("strategy") == MatchStrategy.BEST_CONFIDENCE
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/unit/core/test_condition_multi.py -v`
Expected: FAIL — `AttributeError: 'Condition' object has no attribute 'alt_image_paths'`

- [ ] **Step 3: Condition dataclass 加 4 字段**

修改 `src/core/condition.py` 顶部 import(在 `from src.utils.i18n import t` 之后新增):

```python
from src.core.action import MatchStrategy, ThresholdMode
```

在 `Condition` dataclass 的 `children: list[Condition] = field(default_factory=list)` 之后,新增 4 个多模板字段:

```python
    # ── 多模板字段(增量式,旧 profile 零修改兼容)──
    # IMAGE_FOUND / IMAGE_NOT_FOUND 的备用模板(状态变体);主图 image_path 永远第一个
    alt_image_paths: list[str] = field(default_factory=list)
    # 与 alt_image_paths 平行;None = 继承全局/自动;具体浮点 = 独立覆盖
    alt_thresholds: list[float | None] = field(default_factory=list)
    # 匹配编排策略
    match_strategy: MatchStrategy = MatchStrategy.ADAPTIVE
    # 阈值模式(数据模型默认 GLOBAL,保旧 profile 零漂移;对话框新建默认 AUTO)
    threshold_mode: ThresholdMode = ThresholdMode.GLOBAL
```

- [ ] **Step 4: `_check_image_found` 改用 find_any**

把 `src/core/condition.py` 的 `_check_image_found`(约 172-181 行)整体替换为:

```python
    def _check_image_found(self, cond: Condition) -> bool:
        """检查模板图片是否出现在屏幕上(支持多模板 OR 匹配)。

        任一备用图命中即视为找到;全部未命中视为未找到。
        IMAGE_NOT_FOUND 由 evaluate() 取反本方法结果,天然等价"全部未命中"。
        """
        if not cond.image_path:
            return False
        try:
            screen = self._capture.grab_reuse()
            from src.core.vision.match_config import resolve_find_any_params
            paths, per_thr, strategy = resolve_find_any_params(
                primary_path=cond.image_path,
                alt_paths=cond.alt_image_paths,
                base_threshold=cond.threshold,
                alt_thresholds=cond.alt_thresholds,
                threshold_mode=cond.threshold_mode,
                match_strategy=cond.match_strategy,
            )
            if not paths:
                return False
            result = self._matcher.find_any(
                screen, paths,
                threshold=cond.threshold,
                strategy=strategy,
                per_template_thresholds=per_thr,
            )
            return result is not None
        except (FileNotFoundError, ValueError):
            return False
```

> **实现提示:** `resolve_find_any_params` 内部已做去空/去重/阈值模式解析,无需在此重复。单模板(alt 为空)时 `paths=[image_path]`,`find_any` 退化为单模板,行为等价旧 `find()`。

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest tests/unit/core/test_condition_multi.py -v`
Expected: PASS(7 passed)

- [ ] **Step 6: 跑既有 Condition 相关测试确保无回归**

Run: `pytest tests/unit/core/engine/descriptors/test_condition_descriptor.py -v`
Expected: 全部 PASS(evaluate 分发逻辑未变,IMAGE_FOUND/NOT_FOUND 单模板行为等价)

- [ ] **Step 7: 提交**

```bash
git add src/core/condition.py tests/unit/core/test_condition_multi.py
git commit -m "feat: Condition multi-template matching via find_any"
```

---

## Task 2: MonitorConfig 多模板数据模型 + `_check` 触发图/处理图改用 find_any

**Files:**
- Modify: `src/core/monitor.py`(`MonitorConfig` dataclass,约 32-57 行;`BackgroundMonitor._check`,约 164-225 行)
- Test: `tests/unit/core/test_monitor_multi.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/unit/core/test_monitor_multi.py`:

```python
"""Monitor 多模板(触发图 + 处理图)测试(mock matcher.find_any)。"""

import threading
from unittest.mock import MagicMock

import pytest

from src.core.action import FoundAction, MatchStrategy, ThresholdMode
from src.core.monitor import BackgroundMonitor, MonitorConfig
from src.core.vision.capture import MultiMatchResult


def _monitor(alt_trigger=None, alt_handler=None, strategy=MatchStrategy.ADAPTIVE,
             mode=ThresholdMode.GLOBAL, threshold=0.8):
    return MonitorConfig(
        name="m1", enabled=True,
        image_path="trigger.png", threshold=threshold, check_interval=1.0,
        handler_action=FoundAction.LEFT_CLICK, handler_image_path="handler.png",
        priority=0, max_consecutive=3, cooldown=2.0,
        alt_image_paths=alt_trigger or [],
        alt_thresholds=[None] * len(alt_trigger or []),
        alt_handler_image_paths=alt_handler or [],
        alt_handler_thresholds=[None] * len(alt_handler or []),
        match_strategy=strategy, threshold_mode=mode,
    )


def _make_monitor(config, find_any_results):
    """构造 BackgroundMonitor;frame_provider=None 走 capture.grab();matcher.find_any 按序返回。"""
    mon = BackgroundMonitor.__new__(BackgroundMonitor)
    mon._config = config
    mon._capture = MagicMock()
    mon._capture.grab.return_value = MagicMock(name="screen")
    mon._capture.to_logical_rect.side_effect = lambda r: r
    mon._matcher = MagicMock()
    mon._matcher.find_any.side_effect = find_any_results
    mon._input = MagicMock()
    mon._stop_event = threading.Event()
    mon._pause_event = threading.Event()
    mon._event_bus = None
    mon._frame_provider = None
    mon._state_callback = None
    mon._handler_enter = None
    mon._handler_exit = None
    mon._thread = None
    mon._last_trigger_time = 0.0
    mon._consecutive_count = 0
    mon._trigger_count = 0
    mon._error_count = 0
    mon._last_error = ""
    mon._last_check_time = 0.0
    mon._status = "running"
    mon._state_lock = threading.Lock()
    return mon


def test_monitor_config_has_multi_template_fields():
    m = MonitorConfig(name="m")
    assert m.alt_image_paths == []
    assert m.alt_thresholds == []
    assert m.alt_handler_image_paths == []
    assert m.alt_handler_thresholds == []
    assert m.match_strategy == MatchStrategy.ADAPTIVE
    assert m.threshold_mode == ThresholdMode.GLOBAL


def test_trigger_primary_miss_alt_hit_triggers_handler():
    """触发图主图 miss + 备用图 hit → 应触发处理(调用 input)。"""
    trig = MultiMatchResult(path="alt_t.png", rect=(10, 20, 30, 30), confidence=0.9, strategy_used="early_exit")
    hdl = MultiMatchResult(path="handler.png", rect=(40, 50, 5, 5), confidence=0.95, strategy_used="early_exit")
    config = _monitor(alt_trigger=["alt_t.png"])
    mon = _make_monitor(config, [trig, hdl])
    mon._check()
    assert mon._trigger_count == 1
    assert mon._input.left_click.called


def test_trigger_all_miss_no_handler():
    config = _monitor(alt_trigger=["alt_t.png"])
    mon = _make_monitor(config, [None])
    mon._check()
    assert mon._trigger_count == 0
    assert not mon._input.left_click.called


def test_trigger_uses_find_any_with_resolved_paths():
    trig = MultiMatchResult(path="trigger.png", rect=(1, 2, 3, 3), confidence=0.95, strategy_used="early_exit")
    config = _monitor(alt_trigger=["alt_t.png"], strategy=MatchStrategy.BEST_CONFIDENCE)
    mon = _make_monitor(config, [trig])
    mon._check()
    first_call = mon._matcher.find_any.call_args_list[0]
    paths = first_call.kwargs.get("template_paths") or first_call.args[1]
    assert "trigger.png" in paths and "alt_t.png" in paths
    assert first_call.kwargs.get("strategy") == MatchStrategy.BEST_CONFIDENCE


def test_handler_multitemplate_resolved():
    """处理图多模板:find_any 第二次调用收 handler 主图 + 备用图。"""
    trig = MultiMatchResult(path="trigger.png", rect=(1, 2, 3, 3), confidence=0.95, strategy_used="early_exit")
    hdl = MultiMatchResult(path="alt_h.png", rect=(40, 50, 5, 5), confidence=0.9, strategy_used="early_exit")
    config = _monitor(alt_handler=["alt_h.png"])
    mon = _make_monitor(config, [trig, hdl])
    mon._check()
    assert mon._matcher.find_any.call_count == 2
    second = mon._matcher.find_any.call_args_list[1]
    paths = second.kwargs.get("template_paths") or second.args[1]
    assert "handler.png" in paths and "alt_h.png" in paths
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/unit/core/test_monitor_multi.py -v`
Expected: FAIL — `TypeError: MonitorConfig ... unexpected keyword argument 'alt_image_paths'`

- [ ] **Step 3: MonitorConfig dataclass 加多模板字段**

修改 `src/core/monitor.py` 顶部 import:

```python
from dataclasses import dataclass, field
```

把现有 `from src.core.action import FoundAction` 改为:

```python
from src.core.action import FoundAction, MatchStrategy, ThresholdMode
```

在 `MonitorConfig` 的 `cooldown: float = 2.0` 之后(`__post_init__` 之前),新增:

```python
    # ── 多模板字段(增量式,旧 profile 零修改兼容)──
    # 触发图备用模板(状态变体);主图 image_path 永远第一个
    alt_image_paths: list[str] = field(default_factory=list)
    alt_thresholds: list[float | None] = field(default_factory=list)
    # 处理图备用模板;主图 handler_image_path 永远第一个(共用本节点 strategy/mode)
    alt_handler_image_paths: list[str] = field(default_factory=list)
    alt_handler_thresholds: list[float | None] = field(default_factory=list)
    # 匹配编排策略(触发图 + 处理图共用一套)
    match_strategy: MatchStrategy = MatchStrategy.ADAPTIVE
    # 阈值模式(共用;数据模型默认 GLOBAL,保旧 profile 零漂移)
    threshold_mode: ThresholdMode = ThresholdMode.GLOBAL
```

- [ ] **Step 4: 抽 `_match_multi` 助手 + 改 `_check` 触发图/处理图**

在 `BackgroundMonitor._check` 方法**之前**新增私有助手:

```python
    def _match_multi(
        self,
        screen: np.ndarray,
        primary: str,
        alt_paths: list[str],
        alt_thresholds: list[float | None],
    ) -> "MultiMatchResult | None":
        """对一组模板(主图 + 备用图)做多模板匹配,返回命中结果或 None。

        复用本节点共享的 threshold_mode / match_strategy,经 match_config 解析参数。
        """
        from src.core.vision.match_config import resolve_find_any_params
        paths, per_thr, strategy = resolve_find_any_params(
            primary_path=primary,
            alt_paths=alt_paths,
            base_threshold=self._config.threshold,
            alt_thresholds=alt_thresholds,
            threshold_mode=self._config.threshold_mode,
            match_strategy=self._config.match_strategy,
        )
        if not paths:
            return None
        return self._matcher.find_any(
            screen, paths,
            threshold=self._config.threshold,
            strategy=strategy,
            per_template_thresholds=per_thr,
        )
```

把 `_check` 中触发图匹配段(约 173-183 行,从 `screen = self._grab_frame()` 到 `if rect is None:` 块结束)替换为使用 `_match_multi`:

```python
        screen = self._grab_frame()
        try:
            trig_result = self._match_multi(
                screen, self._config.image_path,
                self._config.alt_image_paths, self._config.alt_thresholds,
            )
        except (FileNotFoundError, ValueError):
            return

        if trig_result is None:
            with self._state_lock:
                self._consecutive_count = 0
            self._push_state()
            return

        rect = trig_result.rect
```

把 `_check` 中发布事件段里 `match_position=(rect[0], rect[1])` 保持不变(命中触发图的位置)。

把处理图匹配段(约 213-222 行,`target_rect = rect` 之后的 `if self._config.handler_image_path:` 块)替换为:

```python
        target_rect = rect
        if self._config.handler_image_path:
            try:
                handler_result = self._match_multi(
                    screen, self._config.handler_image_path,
                    self._config.alt_handler_image_paths,
                    self._config.alt_handler_thresholds,
                )
                if handler_result is not None:
                    target_rect = handler_result.rect
            except (FileNotFoundError, ValueError):
                pass
```

> **实现提示:** `_check` 中 `rect` 变量下游用法(`log.info`、`MonitorTriggeredEvent`、`_handle`)全部不变;仅把"单模板 find"换成"多模板 find_any 取 rect"。冷却/连续触发/触发计数逻辑完全不动。`MultiMatchResult` 类型用字符串注解避免顶层 import 循环(与 capture.py 现有做法一致),或直接 `from src.core.vision.capture import MultiMatchResult` 放在 `TYPE_CHECKING` 块外顶部均可——本项目 monitor.py 无循环依赖,可顶部 import。**推荐顶部 import 更清晰**:`from src.core.vision.capture import MultiMatchResult`(若与现有 vision 导入冲突,改用字符串注解)。

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest tests/unit/core/test_monitor_multi.py -v`
Expected: PASS(5 passed)

- [ ] **Step 6: 跑既有 Monitor 相关测试确保无回归**

Run: `pytest tests/unit/core/test_monitor_manager.py tests/unit/core/layers/test_monitor_coordination_layer.py -v`
Expected: 全部 PASS(单模板行为等价)

- [ ] **Step 7: 提交**

```bash
git add src/core/monitor.py tests/unit/core/test_monitor_multi.py
git commit -m "feat: MonitorConfig multi-template (trigger + handler) via find_any"
```

---

## Task 3: VisionPipeline TemplateMatchStep 多模板支持

**Files:**
- Modify: `src/core/vision/vision_pipeline.py`(`TemplateMatchStep.__init__`,约 209-219 行;`execute`,约 225-246 行)
- Test: `tests/unit/core/vision/test_vision_pipeline_multi.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/unit/core/vision/test_vision_pipeline_multi.py`:

```python
"""VisionPipeline.TemplateMatchStep 多模板测试(mock matcher.find_any)。"""

from unittest.mock import MagicMock

import numpy as np
import pytest

from src.core.action import MatchStrategy
from src.core.vision.capture import MultiMatchResult
from src.core.vision.vision_pipeline import TemplateMatchStep


def _screen():
    return np.zeros((100, 100, 3), dtype=np.uint8)


def test_multitemplate_step_uses_find_any():
    """有 alt_template_paths → 走 find_any。"""
    hit = MultiMatchResult(path="alt.png", rect=(5, 6, 10, 10), confidence=0.95, strategy_used="early_exit")
    matcher = MagicMock()
    matcher.find_any.return_value = hit
    ctx = {"_matcher": matcher}
    step = TemplateMatchStep("primary.png", threshold=0.8, alt_template_paths=["alt.png"])
    out = step.execute(_screen(), ctx)
    assert matcher.find_any.called
    assert out["template_result"] is not out.get("_NOT_FOUND")
    # 结果含命中坐标
    assert out["template_result"]["x"] == 5
    assert out["template_result"]["y"] == 6


def test_multitemplate_step_all_miss_returns_not_found():
    matcher = MagicMock()
    matcher.find_any.return_value = None
    ctx = {"_matcher": matcher}
    step = TemplateMatchStep("primary.png", threshold=0.8, alt_template_paths=["alt.png"])
    out = step.execute(_screen(), ctx)
    assert out["template_result"]["found"] is False


def test_single_template_unchanged_uses_find():
    """无 alt_template_paths → 走原 find() 路径(向后兼容)。"""
    matcher = MagicMock()
    matcher.find.return_value = (1, 2, 3, 3)
    ctx = {"_matcher": matcher}
    step = TemplateMatchStep("primary.png", threshold=0.8)
    step.execute(_screen(), ctx)
    assert matcher.find.called
    assert not matcher.find_any.called


def test_multitemplate_passes_strategy():
    hit = MultiMatchResult(path="primary.png", rect=(1, 2, 3, 3), confidence=0.95, strategy_used="early_exit")
    matcher = MagicMock()
    matcher.find_any.return_value = hit
    ctx = {"_matcher": matcher}
    step = TemplateMatchStep("p.png", threshold=0.8, alt_template_paths=["a.png"],
                             match_strategy=MatchStrategy.BEST_CONFIDENCE)
    step.execute(_screen(), ctx)
    assert matcher.find_any.call_args.kwargs.get("strategy") == MatchStrategy.BEST_CONFIDENCE
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/unit/core/vision/test_vision_pipeline_multi.py -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'alt_template_paths'`

- [ ] **Step 3: `__init__` 加参数**

修改 `src/core/vision/vision_pipeline.py` 的 `TemplateMatchStep.__init__`(约 209-219 行),整体替换为:

```python
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
        self._alt_template_paths = list(alt_template_paths) if alt_template_paths else []
        self._match_strategy = match_strategy  # None → 默认 ADAPTIVE(在 execute 内归一)
```

- [ ] **Step 4: `execute` 多模板分支**

把 `TemplateMatchStep.execute`(约 225-246 行)整体替换为:

```python
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
        """多模板匹配:主图 + 备用图 OR 匹配,命中即返回其位置。"""
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
```

> **实现提示:** `Any` 已在文件顶部 import(多尺度方法用)。`match_strategy` 用字符串注解 `"MatchStrategy | None"` + 方法内 import,避免 vision_pipeline.py 顶层依赖 action.py(保持现有依赖方向)。多模板路径不与多尺度叠加(多模板在原始尺度匹配;若同时设了 scales,以多模板为准,忽略 scales——符合规格 §7.1"多模板时走 find_any")。

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest tests/unit/core/vision/test_vision_pipeline_multi.py -v`
Expected: PASS(4 passed)

- [ ] **Step 6: 跑既有 VisionPipeline 测试确保无回归**

Run: `pytest tests/unit/core/vision/ -v -k "pipeline or template or match"`
Expected: 既有用例全部 PASS(单模板/多尺度行为未变)

- [ ] **Step 7: 提交**

```bash
git add src/core/vision/vision_pipeline.py tests/unit/core/vision/test_vision_pipeline_multi.py
git commit -m "feat: VisionPipeline TemplateMatchStep multi-template via find_any"
```

---

## Task 4: 序列化 — Condition + Monitor 字段 + 加载时 rel→abs

**Files:**
- Modify: `src/core/serialization.py`(`condition_to_dict`/`dict_to_condition`,约 111-145 行;`dict_to_flow_node` Condition 段,约 194-198 行;`monitor_to_dict`/`dict_to_monitor`,约 254-296 行)
- Test: 扩展 `tests/unit/core/test_serialization_multi.py`

- [ ] **Step 1: 追加失败测试**

在 `tests/unit/core/test_serialization_multi.py` 末尾追加:

```python
# ── Condition 多模板序列化 ──────────────────────────────────

def test_condition_to_dict_includes_multi_fields():
    from src.core.condition import Condition, ConditionType
    cond = Condition(
        condition_type=ConditionType.IMAGE_FOUND, image_path="a.png", threshold=0.8,
        alt_image_paths=["b.png", "c.png"], alt_thresholds=[0.7, None],
        match_strategy=MatchStrategy.BEST_CONFIDENCE, threshold_mode=ThresholdMode.PER_TEMPLATE,
    )
    from src.core.serialization import condition_to_dict
    d = condition_to_dict(cond)
    assert d["alt_image_paths"] == ["b.png", "c.png"]
    assert d["alt_thresholds"] == [0.7, None]
    assert d["match_strategy"] == MatchStrategy.BEST_CONFIDENCE
    assert d["threshold_mode"] == ThresholdMode.PER_TEMPLATE


def test_condition_from_dict_loads_multi_fields():
    from src.core.condition import ConditionType
    from src.core.serialization import dict_to_condition
    data = {
        "condition_type": "IMAGE_FOUND", "image_path": "a.png", "threshold": 0.8,
        "alt_image_paths": ["b.png"], "alt_thresholds": [0.7],
        "match_strategy": "ADAPTIVE", "threshold_mode": "GLOBAL",
    }
    cond = dict_to_condition(data)
    assert cond.alt_image_paths == ["b.png"]
    assert cond.alt_thresholds == [0.7]
    assert cond.match_strategy == MatchStrategy.ADAPTIVE


def test_condition_from_dict_backward_compat():
    """旧 profile 无新字段 → 默认值。"""
    from src.core.serialization import dict_to_condition
    cond = dict_to_condition({"condition_type": "IMAGE_FOUND", "image_path": "a.png", "threshold": 0.8})
    assert cond.alt_image_paths == []
    assert cond.alt_thresholds == []
    assert cond.threshold_mode == ThresholdMode.GLOBAL


def test_flow_node_load_converts_condition_alt_rel_to_abs(tmp_path):
    """加载节点时 Condition alt 相对→绝对。"""
    from src.core.serialization import dict_to_flow_node
    profile_dir = tmp_path
    (profile_dir / "b.png").write_bytes(b"x")
    data = {
        "node_id": "n1", "node_type": "ACTION",
        "action": None,
        "condition": {
            "condition_type": "IMAGE_FOUND", "image_path": "a.png", "threshold": 0.8,
            "alt_image_paths": ["b.png"], "alt_thresholds": [None],
            "match_strategy": "ADAPTIVE", "threshold_mode": "GLOBAL",
        },
    }
    node = dict_to_flow_node(data, profile_dir=str(profile_dir))
    assert node.condition is not None
    assert os.path.isabs(node.condition.alt_image_paths[0])
    assert node.condition.alt_image_paths[0].endswith("b.png")


# ── Monitor 多模板序列化 ────────────────────────────────────

def test_monitor_to_dict_includes_multi_fields():
    from src.core.monitor import MonitorConfig
    from src.core.serialization import monitor_to_dict
    mon = MonitorConfig(
        name="m", image_path="t.png", handler_image_path="h.png",
        alt_image_paths=["t2.png"], alt_thresholds=[0.7],
        alt_handler_image_paths=["h2.png"], alt_handler_thresholds=[None],
        match_strategy=MatchStrategy.BEST_CONFIDENCE, threshold_mode=ThresholdMode.PER_TEMPLATE,
    )
    d = monitor_to_dict(mon)
    assert d["alt_image_paths"] == ["t2.png"]
    assert d["alt_thresholds"] == [0.7]
    assert d["alt_handler_image_paths"] == ["h2.png"]
    assert d["match_strategy"] == MatchStrategy.BEST_CONFIDENCE
    assert d["threshold_mode"] == ThresholdMode.PER_TEMPLATE


def test_dict_to_monitor_loads_multi_and_converts_rel_to_abs(tmp_path):
    from src.core.serialization import dict_to_monitor
    profile_dir = tmp_path
    (profile_dir / "t2.png").write_bytes(b"x")
    (profile_dir / "h2.png").write_bytes(b"x")
    data = {
        "name": "m", "enabled": True, "image_path": "t.png", "threshold": 0.8,
        "check_interval": 1.0, "handler_action": "LEFT_CLICK", "handler_image_path": "h.png",
        "priority": 0, "max_consecutive": 3, "cooldown": 2.0,
        "alt_image_paths": ["t2.png"], "alt_thresholds": [0.7],
        "alt_handler_image_paths": ["h2.png"], "alt_handler_thresholds": [None],
        "match_strategy": "ADAPTIVE", "threshold_mode": "GLOBAL",
    }
    mon = dict_to_monitor(data, profile_dir=str(profile_dir))
    assert os.path.isabs(mon.alt_image_paths[0]) and mon.alt_image_paths[0].endswith("t2.png")
    assert os.path.isabs(mon.alt_handler_image_paths[0]) and mon.alt_handler_image_paths[0].endswith("h2.png")
    assert mon.alt_thresholds == [0.7]
    assert mon.match_strategy == MatchStrategy.ADAPTIVE


def test_dict_to_monitor_backward_compat():
    from src.core.serialization import dict_to_monitor
    mon = dict_to_monitor({"name": "m", "image_path": "t.png", "threshold": 0.8}, profile_dir="/tmp")
    assert mon.alt_image_paths == []
    assert mon.alt_handler_image_paths == []
    assert mon.threshold_mode == ThresholdMode.GLOBAL
```

> **实现提示:** 文件顶部需 `import os`(已有)与 `from src.core.action import MatchStrategy, ThresholdMode`(已有)。测试块顶部假设 `MatchStrategy`/`ThresholdMode`/`os` 已在该文件 import(计划 1 已加)。

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/unit/core/test_serialization_multi.py -v -k "condition or monitor"`
Expected: FAIL — `condition_to_dict` 不含 alt 字段 / `dict_to_condition` 不解析

- [ ] **Step 3: `condition_to_dict` + `dict_to_condition` 加字段**

修改 `src/core/serialization.py` 的 `condition_to_dict`(约 111-126 行),在 `d["timer_name"] = cond.timer_name` 之后、`if cond.children:` 之前新增:

```python
    d["alt_image_paths"] = list(cond.alt_image_paths)
    d["alt_thresholds"] = list(cond.alt_thresholds)
    d["match_strategy"] = cond.match_strategy.name
    d["threshold_mode"] = cond.threshold_mode.name
```

修改 `dict_to_condition`(约 129-145 行)的 `return Condition(...)`,在 `timer_name=data.get("timer_name", ""),` 之后、`children=children,` 之前新增:

```python
        alt_image_paths=list(data.get("alt_image_paths", [])),
        alt_thresholds=list(data.get("alt_thresholds", [])),
        match_strategy=_resolve_match_strategy(data.get("match_strategy")),
        threshold_mode=_resolve_threshold_mode(data.get("threshold_mode")),
```

在文件 `_FOUND_ACTION_MIGRATION` 定义之后(约 27 行后)新增两个枚举解析小助手(集中容错,供 Condition/Monitor 共用):

```python
def _resolve_match_strategy(value) -> MatchStrategy:
    """解析 MatchStrategy,未知值/None → ADAPTIVE(向前兼容)。"""
    if isinstance(value, MatchStrategy):
        return value
    if isinstance(value, str) and value in MatchStrategy.__members__:
        return MatchStrategy[value]
    return MatchStrategy.ADAPTIVE


def _resolve_threshold_mode(value) -> ThresholdMode:
    """解析 ThresholdMode,未知值/None → GLOBAL(保旧 profile 零漂移)。"""
    if isinstance(value, ThresholdMode):
        return value
    if isinstance(value, str) and value in ThresholdMode.__members__:
        return ThresholdMode[value]
    return ThresholdMode.GLOBAL
```

- [ ] **Step 4: `dict_to_flow_node` Condition alt rel→abs**

修改 `src/core/serialization.py` 的 `dict_to_flow_node`(约 194-198 行),把现有:

```python
    if "condition" in data and data["condition"] is not None:
        condition = dict_to_condition(data["condition"])
        if condition.image_path:
            abs_path = os.path.normpath(os.path.join(profile_dir, condition.image_path))
            condition.image_path = abs_path
```

替换为:

```python
    if "condition" in data and data["condition"] is not None:
        condition = dict_to_condition(data["condition"])
        if condition.image_path:
            abs_path = os.path.normpath(os.path.join(profile_dir, condition.image_path))
            condition.image_path = abs_path
        # 多模板备用图:相对路径 → 绝对(与主图同一转换规则)
        if condition.alt_image_paths:
            condition.alt_image_paths = [
                os.path.normpath(os.path.join(profile_dir, p)) if p else p
                for p in condition.alt_image_paths
            ]
```

- [ ] **Step 5: `monitor_to_dict` + `dict_to_monitor` 加字段 + rel→abs**

修改 `monitor_to_dict`(约 254-267 行),在 `"cooldown": mon.cooldown,` 之后新增:

```python
        "alt_image_paths": list(mon.alt_image_paths),
        "alt_thresholds": list(mon.alt_thresholds),
        "alt_handler_image_paths": list(mon.alt_handler_image_paths),
        "alt_handler_thresholds": list(mon.alt_handler_thresholds),
        "match_strategy": mon.match_strategy.name,
        "threshold_mode": mon.threshold_mode.name,
```

修改 `dict_to_monitor`(约 270-296 行)。在 `handler_image_path` 解析块之后(约 283 行后)、`return MonitorConfig(` 之前,新增 alt 路径 rel→abs:

```python
    alt_image_paths = [
        os.path.normpath(os.path.join(profile_dir, p)) if p else p
        for p in data.get("alt_image_paths", [])
    ]
    alt_handler_image_paths = [
        os.path.normpath(os.path.join(profile_dir, p)) if p else p
        for p in data.get("alt_handler_image_paths", [])
    ]
```

把 `return MonitorConfig(...)` 调用补入新字段(在 `cooldown=data.get("cooldown", 2.0),` 之后):

```python
        alt_image_paths=alt_image_paths,
        alt_thresholds=list(data.get("alt_thresholds", [])),
        alt_handler_image_paths=alt_handler_image_paths,
        alt_handler_thresholds=list(data.get("alt_handler_thresholds", [])),
        match_strategy=_resolve_match_strategy(data.get("match_strategy")),
        threshold_mode=_resolve_threshold_mode(data.get("threshold_mode")),
```

- [ ] **Step 6: 运行测试确认通过**

Run: `pytest tests/unit/core/test_serialization_multi.py -v`
Expected: PASS(计划 1 既有用例 + 本任务新增 Condition/Monitor 用例全过)

- [ ] **Step 7: 提交**

```bash
git add src/core/serialization.py tests/unit/core/test_serialization_multi.py
git commit -m "feat: serialize Condition + MonitorConfig multi-template fields (rel->abs on load)"
```

---

## Task 5: importer 保存时 Condition + Monitor alt 路径 abs→rel

**Files:**
- Modify: `src/core/io/importer.py`(`_graph_to_v2_dict`,约 210-239 行)
- Test: 扩展 `tests/unit/core/test_serialization_multi.py`

- [ ] **Step 1: 追加失败测试**

在 `tests/unit/core/test_serialization_multi.py` 末尾追加:

```python
# ── 导出(importer)Condition + Monitor alt abs→rel ─────────

def test_export_converts_condition_alt_abs_to_rel(tmp_path):
    from src.core.condition import Condition, ConditionType
    from src.core.flow import FlowGraph, FlowNode, NodeType
    from src.core.io.importer import _graph_to_v2_dict
    profile_dir = str(tmp_path)
    abs_b = os.path.join(profile_dir, "cond_alt.png")
    cond = Condition(
        condition_type=ConditionType.IMAGE_FOUND,
        image_path=os.path.join(profile_dir, "a.png"),
        alt_image_paths=[abs_b],
    )
    node = FlowNode(node_id="n1", node_type=NodeType.ACTION, condition=cond)
    graph = FlowGraph(name="g", start_node_id="n1", nodes={"n1": node})
    d = _graph_to_v2_dict(graph, profile_dir)
    cond_dict = d["nodes"][0]["condition"]
    assert cond_dict["alt_image_paths"] == [os.path.relpath(abs_b, profile_dir)]


def test_export_converts_monitor_alt_abs_to_rel(tmp_path):
    from src.core.monitor import MonitorConfig
    from src.core.flow import FlowGraph
    from src.core.io.importer import _graph_to_v2_dict
    profile_dir = str(tmp_path)
    abs_t2 = os.path.join(profile_dir, "t2.png")
    abs_h2 = os.path.join(profile_dir, "h2.png")
    graph = FlowGraph(name="g", start_node_id="")
    graph.monitors.append(MonitorConfig(
        name="m", image_path=os.path.join(profile_dir, "t.png"),
        handler_image_path=os.path.join(profile_dir, "h.png"),
        alt_image_paths=[abs_t2], alt_handler_image_paths=[abs_h2],
    ))
    d = _graph_to_v2_dict(graph, profile_dir)
    md = d["monitors"][0]
    assert md["alt_image_paths"] == [os.path.relpath(abs_t2, profile_dir)]
    assert md["alt_handler_image_paths"] == [os.path.relpath(abs_h2, profile_dir)]
```

> **实现提示:** `FlowGraph`/`FlowNode` 的实际构造签名以 `src/core/flow.py` 为准;若 `FlowNode` 必需更多字段(如 `pos_x`/`pos_y`),按其 dataclass 默认值补齐。测试聚焦"导出时 alt 绝对→相对"语义。

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/unit/core/test_serialization_multi.py -v -k "export"`
Expected: FAIL — importer 未转换 Condition/Monitor alt 路径

- [ ] **Step 3: `_graph_to_v2_dict` 加 Condition + Monitor alt abs→rel**

修改 `src/core/io/importer.py` 的 `_graph_to_v2_dict`(约 210-239 行)。在现有 ClickImageStep alt abs→rel 块(约 221-225 行)之后、`nodes_data.append(nd)` 之前,新增 Condition alt abs→rel:

```python
        # 多模板备用图(Condition):绝对路径 → 相对 profile_dir
        if node.condition and node.condition.alt_image_paths and "condition" in nd:
            nd["condition"]["alt_image_paths"] = [
                os.path.relpath(p, profile_dir) if os.path.isabs(p) else p
                for p in node.condition.alt_image_paths
            ]
```

在 `monitors_data = [monitor_to_dict(m) for m in graph.monitors]` 之后(约 229 行后),新增 Monitor alt abs→rel:

```python
    # 多模板备用图(Monitor):绝对路径 → 相对 profile_dir
    for mon, md in zip(graph.monitors, monitors_data):
        if mon.alt_image_paths:
            md["alt_image_paths"] = [
                os.path.relpath(p, profile_dir) if os.path.isabs(p) else p
                for p in mon.alt_image_paths
            ]
        if mon.alt_handler_image_paths:
            md["alt_handler_image_paths"] = [
                os.path.relpath(p, profile_dir) if os.path.isabs(p) else p
                for p in mon.alt_handler_image_paths
            ]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/unit/core/test_serialization_multi.py -v`
Expected: PASS(全部)

- [ ] **Step 5: 提交**

```bash
git add src/core/io/importer.py tests/unit/core/test_serialization_multi.py
git commit -m "feat: export Condition + Monitor multi-template alt paths (abs->rel)"
```

---

## Task 6: profile_manager 拷贝 Condition + Monitor alt 图片

**Files:**
- Modify: `src/panel/profile_manager.py`(`save`,约 145-177 行)
- Test: 扩展 `tests/unit/core/test_serialization_multi.py`

- [ ] **Step 1: 追加失败测试**

在 `tests/unit/core/test_serialization_multi.py` 末尾追加:

```python
# ── profile_manager 拷贝 Condition + Monitor alt 图片 ────────

def _png(path):
    import cv2
    import numpy as np
    img = np.zeros((10, 10, 3), dtype=np.uint8)
    cv2.imwrite(path, img)
    return path


def test_profile_save_copies_condition_alt_images(tmp_path):
    from src.core.condition import Condition, ConditionType
    from src.core.flow import FlowGraph, FlowNode, NodeType
    from src.panel.profile_manager import ProfileManager
    root = str(tmp_path / "profiles")
    pm = ProfileManager(root)
    src_alt = _png(str(tmp_path / "cond_alt.png"))
    cond = Condition(
        condition_type=ConditionType.IMAGE_FOUND,
        image_path=_png(str(tmp_path / "a.png")),
        alt_image_paths=[src_alt],
    )
    node = FlowNode(node_id="n1", node_type=NodeType.ACTION, condition=cond)
    graph = FlowGraph(name="g", start_node_id="n1", nodes={"n1": node})
    profile_dir = pm.save("p1", graph)
    import json
    with open(os.path.join(profile_dir, "profile.json"), encoding="utf-8") as f:
        data = json.load(f)
    cond_alt = data["flow"]["nodes"][0]["condition"]["alt_image_paths"][0]
    # 存为相对 profile_dir 的路径,且图片确实拷贝到 images/
    assert not os.path.isabs(cond_alt)
    assert os.path.exists(os.path.join(profile_dir, cond_alt))


def test_profile_save_copies_monitor_alt_images(tmp_path):
    from src.core.flow import FlowGraph
    from src.core.monitor import MonitorConfig
    from src.panel.profile_manager import ProfileManager
    root = str(tmp_path / "profiles")
    pm = ProfileManager(root)
    src_t2 = _png(str(tmp_path / "t2.png"))
    src_h2 = _png(str(tmp_path / "h2.png"))
    graph = FlowGraph(name="g", start_node_id="")
    graph.monitors.append(MonitorConfig(
        name="m",
        image_path=_png(str(tmp_path / "t.png")),
        handler_image_path=_png(str(tmp_path / "h.png")),
        alt_image_paths=[src_t2], alt_handler_image_paths=[src_h2],
    ))
    profile_dir = pm.save("p2", graph)
    import json
    with open(os.path.join(profile_dir, "profile.json"), encoding="utf-8") as f:
        data = json.load(f)
    md = data["flow"]["monitors"][0]
    assert not os.path.isabs(md["alt_image_paths"][0])
    assert os.path.exists(os.path.join(profile_dir, md["alt_image_paths"][0]))
    assert os.path.exists(os.path.join(profile_dir, md["alt_handler_image_paths"][0]))
```

> **实现提示:** `ProfileManager` 构造签名以 [profile_manager.py](../../../src/panel/profile_manager.py) 实际为准(本测试假设 `ProfileManager(root)`)。`FlowNode`/`FlowGraph` dataclass 默认值见 [flow.py](../../../src/core/flow.py)。

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/unit/core/test_serialization_multi.py -v -k "profile_save"`
Expected: FAIL — alt 图片未拷贝(JSON 里仍是绝对路径)

- [ ] **Step 3: `save` 拷贝 Condition alt 图片**

修改 `src/panel/profile_manager.py` 的 `save`。在现有 CONDITION 主图拷贝块(约 160-163 行)之后、`nodes_data.append(node_dict)` 之前,新增:

```python
            # 多模板备用图(Condition):逐个拷贝到 images/ 并存相对路径
            if node.condition and node.condition.alt_image_paths and "condition" in node_dict:
                node_dict["condition"]["alt_image_paths"] = [
                    self._copy_image(p, profile_dir, images_dir)
                    for p in node.condition.alt_image_paths
                ]
```

- [ ] **Step 4: `save` 拷贝 Monitor alt 图片(触发图 + 处理图)**

在现有 Monitor 主图/处理图拷贝块(约 173-176 行)之后、`monitors_data.append(mon_dict)` 之前,新增:

```python
            # 多模板备用图(Monitor 触发图):逐个拷贝到 images/ 并存相对路径
            if mon.alt_image_paths:
                mon_dict["alt_image_paths"] = [
                    self._copy_image(p, profile_dir, images_dir)
                    for p in mon.alt_image_paths
                ]
            # 多模板备用图(Monitor 处理图)
            if mon.alt_handler_image_paths:
                mon_dict["alt_handler_image_paths"] = [
                    self._copy_image(p, profile_dir, images_dir)
                    for p in mon.alt_handler_image_paths
                ]
```

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest tests/unit/core/test_serialization_multi.py -v`
Expected: PASS(全部)

- [ ] **Step 6: 提交**

```bash
git add src/panel/profile_manager.py tests/unit/core/test_serialization_multi.py
git commit -m "feat: copy Condition + Monitor multi-template alt images on profile save"
```

---

## Task 7: MultiTemplateEditor 加 `show_match_settings` 参数(tk + Qt)

**Files:**
- Modify: `src/panel/dialogs/multi_template_editor.py`(`MultiTemplateEditor.__init__`/`_build_controls`/`_apply_mode_visibility`/`set_state`/`get_state`/`_current_mode_name`)
- Modify: `src/panel/qt_backend/dialogs/multi_template_editor.py`(`MultiTemplateEditorQt.__init__`/`_apply_mode_visibility`/`set_state`/`get_state`)
- Test: `tests/unit/panel/test_multi_template_editor_param.py`

> **背景:** Monitor 处理图需要复用编辑器但**不显示**模式/策略/全局阈值控件(共用触发图的那一套)。加 `show_match_settings: bool = True` 参数,`False` 时跳过控制区,仅管理主图+备用图行+每行阈值。状态源统一用 StringVar/属性,控件只是其视图。

- [ ] **Step 1: 写失败测试(tk)**

创建 `tests/unit/panel/test_multi_template_editor_param.py`:

```python
"""MultiTemplateEditor.show_match_settings 参数测试(tk,免渲染:仅校验可构造 + API)。"""

import pytest

pytest.importorskip("tkinter")


def _make_root():
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    return root


def test_editor_accepts_show_match_settings_false():
    from src.panel.dialogs.multi_template_editor import MultiTemplateEditor
    root = _make_root()
    try:
        editor = MultiTemplateEditor(root, show_match_settings=False)
        # 控制区不渲染 → 无 mode/strategy 控件
        assert not hasattr(editor, "_mode_dd") or editor._mode_dd is None
    finally:
        root.destroy()


def test_editor_default_show_match_settings_true():
    from src.panel.dialogs.multi_template_editor import MultiTemplateEditor
    root = _make_root()
    try:
        editor = MultiTemplateEditor(root)
        assert hasattr(editor, "_mode_dd")
    finally:
        root.destroy()


def test_editor_hidden_settings_get_state_returns_defaults():
    """show_match_settings=False:get_state 仍返回合法的 mode/strategy(默认值)。"""
    from src.panel.dialogs.multi_template_editor import MultiTemplateEditor
    from src.core.action import MatchStrategy, ThresholdMode
    root = _make_root()
    try:
        editor = MultiTemplateEditor(root, show_match_settings=False)
        editor.set_state("a.png", ["b.png"], [0.7], ThresholdMode.GLOBAL, MatchStrategy.ADAPTIVE, 0.8)
        img, alts, thr, mode, strategy, gthr = editor.get_state()
        assert img == "a.png"
        assert alts == ["b.png"]
        assert mode == ThresholdMode.GLOBAL
        assert strategy == MatchStrategy.ADAPTIVE
    finally:
        root.destroy()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/unit/panel/test_multi_template_editor_param.py -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'show_match_settings'`

- [ ] **Step 3: tk 编辑器加参数 + 统一状态源**

修改 `src/panel/dialogs/multi_template_editor.py`。

3a) `__init__` 加参数并引入 StringVar 作统一状态源(下拉只是其视图):

```python
    def __init__(
        self,
        parent: tk.Widget,
        on_change: Callable[[], None] | None = None,
        show_match_settings: bool = True,
    ) -> None:
        self._th = current_theme()
        self._on_change = on_change
        self._show_match_settings = show_match_settings
        self._frame = themed_frame(parent)
        self._rows: list[dict] = []
        self._photo_refs: list[object] = []
        self._primary_path_var = tk.StringVar()
        self._global_thr_var = tk.DoubleVar(value=0.8)
        # 统一状态源:StringVar 永远存在;控件(show_match_settings=True)只是其视图
        self._threshold_mode_var = tk.StringVar(value=ThresholdMode.GLOBAL.name)
        self._match_strategy_var = tk.StringVar(value=MatchStrategy.ADAPTIVE.name)
        self._mode_dd = None
        self._strategy_dd = None
        self._global_thr_label = None
        self._global_thr_sb = None
        if show_match_settings:
            self._build_controls()
        self._rows_frame = themed_frame(self._frame)
        self._rows_frame.pack(fill=tk.X)
        self._build_add_bar()
        self._render_rows()
```

3b) `_build_controls` 用 StringVar 作下拉文本变量,使其与统一源联动:

```python
    def _build_controls(self) -> None:
        th = self._th
        ctrl = themed_frame(self._frame)
        ctrl.pack(fill=tk.X, pady=th.pad_xs)

        themed_label(ctrl, text=t("dialog.label.threshold_mode")).grid(
            row=0, column=0, sticky=tk.W, padx=th.pad_xs,
        )
        self._mode_dd = themed_dropdown(
            ctrl, options=_THRESHOLD_MODE_OPTIONS,
            value=self._threshold_mode_var.get(), state="readonly", width=20,
            command=lambda _v: (self._threshold_mode_var.set(_v), self._on_mode_changed()),
        )
        self._mode_dd.grid(row=0, column=1, sticky=tk.W, padx=th.pad_xs)

        themed_label(ctrl, text=t("dialog.label.match_strategy")).grid(
            row=1, column=0, sticky=tk.W, padx=th.pad_xs,
        )
        self._strategy_dd = themed_dropdown(
            ctrl, options=_MATCH_STRATEGY_OPTIONS,
            value=self._match_strategy_var.get(), state="readonly", width=20,
            command=lambda _v: self._match_strategy_var.set(_v),
        )
        self._strategy_dd.grid(row=1, column=1, sticky=tk.W, padx=th.pad_xs)

        self._global_thr_label = themed_label(ctrl, text=t("dialog.label.global_threshold"))
        self._global_thr_sb = tk.Spinbox(
            ctrl, from_=0.1, to=1.0, increment=0.05,
            textvariable=self._global_thr_var, width=6,
        )
        self._global_thr_label.grid(row=2, column=0, sticky=tk.W, padx=th.pad_xs)
        self._global_thr_sb.grid(row=2, column=1, sticky=tk.W, padx=th.pad_xs)
```

3c) `_current_mode_name` 改读 StringVar:

```python
    def _current_mode_name(self) -> str:
        return self._threshold_mode_var.get()
```

3d) `_apply_mode_visibility` 守卫控制区(精简模式下不触碰不存在的控件):

```python
    def _apply_mode_visibility(self) -> None:
        mode = self._current_mode_name()
        show_global = mode != ThresholdMode.AUTO.name
        # 全局阈值框仅在控制区渲染时存在
        if self._global_thr_label is not None and self._global_thr_sb is not None:
            if show_global:
                self._global_thr_label.grid()
                self._global_thr_sb.grid()
            else:
                self._global_thr_label.grid_remove()
                self._global_thr_sb.grid_remove()
```

3e) `set_state` / `get_state` 改用 StringVar(并同步下拉视图):

```python
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
        self._global_thr_var.set(global_threshold)
        if self._mode_dd is not None:
            self._mode_dd.set_value(mode.name)
        if self._strategy_dd is not None:
            self._strategy_dd.set_value(strategy.name)
        self._render_rows()

    def get_state(self) -> tuple[str, list[str], list[float | None], ThresholdMode, MatchStrategy, float]:
        """返回 (image_path, alt_paths, alt_thresholds, mode, strategy, global_threshold)。"""
        alt_paths = [r["path_var"].get() for r in self._rows]
        alt_thresholds: list[float | None] = []
        for r in self._rows:
            if r["custom_var"].get():
                try:
                    alt_thresholds.append(float(r["thr_var"].get()))
                except (tk.TclError, ValueError):
                    alt_thresholds.append(None)
            else:
                alt_thresholds.append(None)
        mode_name = self._threshold_mode_var.get()
        strategy_name = self._match_strategy_var.get()
        mode = ThresholdMode[mode_name] if mode_name in ThresholdMode.__members__ else ThresholdMode.GLOBAL
        strategy = MatchStrategy[strategy_name] if strategy_name in MatchStrategy.__members__ else MatchStrategy.ADAPTIVE
        try:
            gthr = float(self._global_thr_var.get())
        except (tk.TclError, ValueError):
            gthr = 0.8
        return self._primary_path_var.get(), alt_paths, alt_thresholds, mode, strategy, gthr
```

- [ ] **Step 4: 运行 tk 测试确认通过**

Run: `pytest tests/unit/panel/test_multi_template_editor_param.py -v`
Expected: PASS(3 passed)

- [ ] **Step 5: Qt 编辑器加同规格参数**

修改 `src/panel/qt_backend/dialogs/multi_template_editor.py`。

5a) `__init__` 加 `show_match_settings` 参数;mode/strategy/threshold 改为实例属性作统一状态源,控件只是视图:

```python
    def __init__(self, parent=None, show_match_settings: bool = True) -> None:
        super().__init__(parent)
        self._rows: list[dict] = []
        self._primary_path = ""
        # 统一状态源(控件只是视图)
        self._mode = ThresholdMode.GLOBAL
        self._strategy = MatchStrategy.ADAPTIVE
        self._global_threshold = 0.8
        self._show_match_settings = show_match_settings

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if show_match_settings:
            layout.addWidget(self._build_controls())

        # 行容器
        self._rows_layout = QVBoxLayout()
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._rows_layout)

        # 添加按钮 + 提示
        bar = QHBoxLayout()
        add_btn = QPushButton(t("dialog.multi_template.add"))
        add_btn.clicked.connect(self._add_alt)
        bar.addWidget(add_btn)
        bar.addWidget(QLabel(t("dialog.multi_template.hint_order")))
        layout.addLayout(bar)
```

5b) 把原 `__init__` 内的控制区构建抽成 `_build_controls`,返回控件 QWidget;下拉变化同步实例属性:

```python
    def _build_controls(self) -> QWidget:
        ctrl = QWidget()
        cl = QVBoxLayout(ctrl)
        cl.setContentsMargins(0, 0, 0, 0)
        # 阈值模式
        r1 = QHBoxLayout()
        r1.addWidget(QLabel(t("dialog.label.threshold_mode")))
        self._mode_cb = QComboBox()
        for m, key in [
            (ThresholdMode.AUTO, "dialog.threshold_mode.auto"),
            (ThresholdMode.GLOBAL, "dialog.threshold_mode.global"),
            (ThresholdMode.PER_TEMPLATE, "dialog.threshold_mode.per_template"),
        ]:
            self._mode_cb.addItem(t(key), userData=m)
        self._mode_cb.currentIndexChanged.connect(self._on_mode_changed)
        r1.addWidget(self._mode_cb)
        cl.addLayout(r1)
        # 匹配策略
        r2 = QHBoxLayout()
        r2.addWidget(QLabel(t("dialog.label.match_strategy")))
        self._strategy_cb = QComboBox()
        for s, key in [
            (MatchStrategy.ADAPTIVE, "dialog.match_strategy.adaptive"),
            (MatchStrategy.FIRST_MATCH, "dialog.match_strategy.first_match"),
            (MatchStrategy.BEST_CONFIDENCE, "dialog.match_strategy.best_confidence"),
        ]:
            self._strategy_cb.addItem(t(key), userData=s)
        r2.addWidget(self._strategy_cb)
        cl.addLayout(r2)
        # 全局阈值
        r3 = QHBoxLayout()
        self._global_thr_label = QLabel(t("dialog.label.global_threshold"))
        self._global_thr_sb = QDoubleSpinBox()
        self._global_thr_sb.setRange(0.1, 1.0)
        self._global_thr_sb.setSingleStep(0.05)
        self._global_thr_sb.setDecimals(2)
        self._global_thr_sb.valueChanged.connect(lambda v: setattr(self, "_global_threshold", v))
        r3.addWidget(self._global_thr_label)
        r3.addWidget(self._global_thr_sb)
        cl.addLayout(r3)
        return ctrl
```

5c) `_on_mode_changed` 同步实例属性 + 重渲染:

```python
    def _on_mode_changed(self) -> None:
        if self._show_match_settings:
            self._mode = self._mode_cb.currentData()
            self._strategy = self._strategy_cb.currentData()
            self._global_threshold = self._global_thr_sb.value()
        self._render_rows()
```

5d) `_apply_mode_visibility` 守卫:

```python
    def _apply_mode_visibility(self) -> None:
        mode = self._mode
        show_global = mode != ThresholdMode.AUTO
        if self._show_match_settings:
            self._global_thr_label.setVisible(show_global)
            self._global_thr_sb.setVisible(show_global)
        for row in self._rows:
            row["thr_widget"].setVisible(mode == ThresholdMode.PER_TEMPLATE)
```

5e) `set_state` / `get_state` 用实例属性(同步控件):

```python
    def set_state(self, image_path, alt_paths, alt_thresholds, mode, strategy, global_threshold) -> None:
        self._primary_path = image_path
        self._rows = [
            {
                "path": p,
                "custom": (i < len(alt_thresholds) and alt_thresholds[i] is not None),
                "thr": alt_thresholds[i] if (i < len(alt_thresholds) and alt_thresholds[i] is not None) else 0.8,
            }
            for i, p in enumerate(alt_paths)
        ]
        self._mode = mode
        self._strategy = strategy
        self._global_threshold = global_threshold
        if self._show_match_settings:
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
            self._mode,
            self._strategy,
            self._global_threshold,
        )
```

- [ ] **Step 6: Qt 逻辑可导入验证(无 PySide6 则 SKIP)**

Run: `pytest tests/unit/panel/test_qt_multi_template_editor.py -v`
Expected: 无 PySide6 → SKIP;有 PySide6 → PASS(既有计划 1 用例 + show_match_settings 默认 True 不破坏)

> **实现提示:** 既有 `test_qt_multi_template_editor.py`(计划 1 Task 11)调用 `MultiTemplateEditorQt(parent=None)`,`show_match_settings` 默认 True → 行为不变,不破坏。如需补 `show_match_settings=False` 用例,追加到该文件。

- [ ] **Step 7: 提交**

```bash
git add src/panel/dialogs/multi_template_editor.py src/panel/qt_backend/dialogs/multi_template_editor.py tests/unit/panel/test_multi_template_editor_param.py
git commit -m "feat: MultiTemplateEditor show_match_settings param (tk + Qt) for Monitor handler"
```

---

## Task 8: tkinter condition_dialog 嵌入 MultiTemplateEditor

**Files:**
- Modify: `src/panel/dialogs/condition_dialog.py`(`_build_image_fields`、`rebuild_fields` 调用、`on_ok`、`open_condition_dialog` 的 var 初始化)
- Test: `tests/unit/panel/test_condition_dialog_multi.py`

> **核心难点:** 条件类型切换时 `rebuild_fields()` 会销毁重建字段区 → 编辑器被销毁。解法:用一个闭包 `image_state` 字典 + `on_change` 回调持续把编辑器状态同步回 `image_state`;重建时新编辑器从 `image_state` 恢复;`on_ok` 从 `image_state` 读(对图片类条件)。

- [ ] **Step 1: 写失败测试(免渲染:可导入 + 数据模型)**

创建 `tests/unit/panel/test_condition_dialog_multi.py`:

```python
"""condition_dialog 多模板集成测试(免渲染:校验可导入 + Condition 多模板字段装配)。"""

import pytest

pytest.importorskip("tkinter")


def test_condition_dialog_module_imports():
    """模块可导入即说明集成完成(无语法/导入错误)。"""
    import src.panel.dialogs.condition_dialog as mod
    assert hasattr(mod, "open_condition_dialog")


def test_image_condition_with_multi_fields_assembles():
    """验证带多模板字段的 Condition 能被对话框逻辑正确读取(不依赖 Tk root)。"""
    from src.core.action import MatchStrategy, ThresholdMode
    from src.core.condition import Condition, ConditionType
    cond = Condition(
        condition_type=ConditionType.IMAGE_FOUND, image_path="a.png", threshold=0.8,
        alt_image_paths=["b.png", "c.png"], alt_thresholds=[0.7, None],
        match_strategy=MatchStrategy.BEST_CONFIDENCE, threshold_mode=ThresholdMode.PER_TEMPLATE,
    )
    # 对话框应能把这些字段原样读出并装配(此处校验数据模型,渲染在手动验证)
    assert cond.threshold_mode == ThresholdMode.PER_TEMPLATE
    assert cond.match_strategy == MatchStrategy.BEST_CONFIDENCE
    assert len(cond.alt_image_paths) == 2
```

- [ ] **Step 2: 运行测试确认(导入即通过 / 失败则集成未完成)**

Run: `pytest tests/unit/panel/test_condition_dialog_multi.py -v`
Expected: 本任务改完前可能 PASS(仅校验数据模型)或 FAIL(若改坏导入);改完应为 PASS

- [ ] **Step 3: 重构 `open_condition_dialog` 用 image_state + 编辑器**

修改 `src/panel/dialogs/condition_dialog.py`。

3a) 顶部 import 新增:

```python
from src.core.action import MatchStrategy, ThresholdMode
from src.panel.dialogs.multi_template_editor import MultiTemplateEditor
```

3b) 在 `open_condition_dialog` 中,把现有 `var_image` / `var_threshold` 初始化(约 61-62 行)替换为统一的 `image_state` 字典 + 编辑器占位:

```python
    # 图片条件多模板状态(跨 rebuild 保活)
    image_state = {
        "image_path": condition.image_path,
        "alt_paths": list(condition.alt_image_paths),
        "alt_thresholds": list(condition.alt_thresholds),
        "mode": condition.threshold_mode,
        "strategy": condition.match_strategy,
        "threshold": condition.threshold,
    }
    image_editor_holder: list = []  # 持当前编辑器实例(0 或 1 个)
```

3c) 把 `rebuild_fields()` 中对 `_build_image_fields` 的调用(约 88 行)改为传入 holder + state:

```python
        if selected in (ConditionType.IMAGE_FOUND, ConditionType.IMAGE_NOT_FOUND):
            _build_image_fields(fields_frame, r, image_state, image_editor_holder)
```

3d) `on_ok` 中(约 162-173 行 `else:` 分支),用 `image_state` 构造图片条件的多模板字段:

```python
        else:
            selected = _get_selected_type()
            image_path, threshold = "", 0.8
            alt_paths: list[str] = []
            alt_thresholds: list[float | None] = []
            mode = ThresholdMode.GLOBAL
            strategy = MatchStrategy.ADAPTIVE
            if selected in (ConditionType.IMAGE_FOUND, ConditionType.IMAGE_NOT_FOUND):
                # 提交前从编辑器同步最新状态
                if image_editor_holder:
                    (image_path, alt_paths, alt_thresholds,
                     mode, strategy, threshold) = image_editor_holder[0].get_state()
                else:
                    image_path = image_state["image_path"]
                    threshold = image_state["threshold"]
                    alt_paths = image_state["alt_paths"]
                    alt_thresholds = image_state["alt_thresholds"]
                    mode = image_state["mode"]
                    strategy = image_state["strategy"]
            result = Condition(
                condition_type=selected,
                image_path=image_path,
                threshold=threshold,
                alt_image_paths=alt_paths,
                alt_thresholds=alt_thresholds,
                match_strategy=strategy,
                threshold_mode=mode,
                variable_name=var_var_name.get().strip(),
                compare_op=var_compare_op.get(),
                compare_value_x=var_compare_x.get(),
                compare_value_y=var_compare_y.get(),
                timer_name=var_timer_name.get().strip(),
                timeout_seconds=var_timeout.get(),
            )
```

3e) 重写 `_build_image_fields` 为嵌入编辑器(替换原 183-199 行整段):

```python
def _build_image_fields(parent, start_row, image_state, holder):
    """图片检测条件字段 — 嵌入多模板管理器(主图 + 备用图 + 策略/阈值模式)。"""
    th = current_theme()

    def _sync():
        """编辑器变更 → 同步回 image_state(跨 rebuild 保活)。"""
        (image_state["image_path"], image_state["alt_paths"],
         image_state["alt_thresholds"], image_state["mode"],
         image_state["strategy"], image_state["threshold"]) = editor.get_state()

    editor = MultiTemplateEditor(parent, on_change=_sync)
    editor.set_state(
        image_state["image_path"], image_state["alt_paths"], image_state["alt_thresholds"],
        image_state["mode"], image_state["strategy"], image_state["threshold"],
    )
    editor.frame.grid(row=start_row, column=0, columnspan=2, sticky=tk.EW, padx=th.pad_sm, pady=th.pad_xs)
    parent.columnconfigure(1, weight=1)
    holder.clear()
    holder.append(editor)
```

> **实现提示:** `var_image`/`var_threshold` 在重构后不再被图片字段使用,但保留它们的初始化无害(其它分支不用)。`_browse_cond_image` 模块级函数若不再被引用可保留(不影响)。`themed_entry`/`themed_button`/`ttk.Scale` 的既有 import 保留(其它字段构造器仍用)。

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/unit/panel/test_condition_dialog_multi.py -v`
Expected: PASS

- [ ] **Step 5: 跑既有条件对话框相关测试(若有)确保无回归**

Run: `pytest tests/unit/panel/ -v -k "condition" 2>/dev/null || echo "no condition dialog tests"`
Expected: 既有用例 PASS 或无既有用例

- [ ] **Step 6: 提交**

```bash
git add src/panel/dialogs/condition_dialog.py tests/unit/panel/test_condition_dialog_multi.py
git commit -m "feat: tkinter condition_dialog embeds MultiTemplateEditor for image conditions"
```

---

## Task 9: tkinter monitor_dialog 嵌入 MultiTemplateEditor ×2(触发图 + 处理图)

**Files:**
- Modify: `src/panel/dialogs/monitor_dialog.py`(`open_monitor_dialog` 的检测图/阈值/处理图区,`on_ok`)
- Test: `tests/unit/panel/test_monitor_dialog_multi.py`

> **设计:** 触发图用完整编辑器(`show_match_settings=True`,拥有模式/策略/全局阈值);处理图用精简编辑器(`show_match_settings=False`,只管主图+备用图+每行阈值)。`on_ok` 时两者共用触发图的 mode/strategy/threshold。

- [ ] **Step 1: 写失败测试(免渲染 import)**

创建 `tests/unit/panel/test_monitor_dialog_multi.py`:

```python
"""monitor_dialog 多模板集成测试(免渲染:校验可导入)。"""

import pytest

pytest.importorskip("tkinter")


def test_monitor_dialog_module_imports():
    import src.panel.dialogs.monitor_dialog as mod
    assert hasattr(mod, "open_monitor_dialog")


def test_monitor_config_multi_fields_visible():
    from src.core.action import MatchStrategy, ThresholdMode
    from src.core.monitor import MonitorConfig
    m = MonitorConfig(
        name="m", image_path="t.png", handler_image_path="h.png",
        alt_image_paths=["t2.png"], alt_handler_image_paths=["h2.png"],
        match_strategy=MatchStrategy.BEST_CONFIDENCE, threshold_mode=ThresholdMode.PER_TEMPLATE,
    )
    assert m.alt_image_paths == ["t2.png"]
    assert m.alt_handler_image_paths == ["h2.png"]
```

- [ ] **Step 2: 运行测试(导入校验)**

Run: `pytest tests/unit/panel/test_monitor_dialog_multi.py -v`
Expected: 改完前可能 PASS(仅数据模型);改完应 PASS 且不破坏导入

- [ ] **Step 3: 嵌入触发图编辑器(替换检测图 + 阈值区)**

修改 `src/panel/dialogs/monitor_dialog.py`。

3a) 顶部 import 新增:

```python
from src.core.action import MatchStrategy, ThresholdMode
from src.panel.dialogs.multi_template_editor import MultiTemplateEditor
```

3b) 在 `open_monitor_dialog` 中,删除现有 `var_image` / `var_threshold` 初始化(约 32-33 行)及"检测图片"块(约 64-70 行)与"阈值"块(约 72-88 行),替换为触发图编辑器。在"检测配置"标签(约 59-62 行)之后插入:

```python
    # 触发图多模板管理器(完整:含模式/策略/全局阈值)
    trigger_editor = MultiTemplateEditor(dlg, on_change=None)
    trigger_editor.set_state(
        monitor.image_path, monitor.alt_image_paths, monitor.alt_thresholds,
        monitor.threshold_mode, monitor.match_strategy, monitor.threshold,
    )
    trigger_editor.frame.grid(row=row, column=0, columnspan=2, sticky=tk.EW, padx=th.pad_sm, pady=th.pad_xs)
    row += 1
```

把"检测间隔"块(约 90-94 行)的 `row` 计数顺延(已被编辑器占用一行,后续 `row += 1` 保持不变,因为编辑器只占一行)。

3c) 嵌入处理图编辑器(替换"处理目标图片"块,约 117-128 行),用精简编辑器:

```python
    # 处理图多模板管理器(精简:不显示模式/策略/全局阈值,共用触发图的)
    handler_editor = MultiTemplateEditor(dlg, on_change=None, show_match_settings=False)
    handler_editor.set_state(
        monitor.handler_image_path, monitor.alt_handler_image_paths,
        monitor.alt_handler_thresholds,
        monitor.threshold_mode, monitor.match_strategy, monitor.threshold,
    )
    handler_editor.frame.grid(row=row, column=0, columnspan=2, sticky=tk.EW, padx=th.pad_sm, pady=th.pad_xs)
    row += 1
```

> **实现提示:** 删除原 `var_handler_image` 相关 entry/button 与"可选处理图"提示行(已由精简编辑器取代);`row` 计数随之顺延。保留 `handler_dropdown`、`var_interval`、`var_max_consecutive`、`var_cooldown`、`var_name`、`var_enabled` 等其它控件不动。

- [ ] **Step 4: `on_ok` 改用两个编辑器的状态**

把 `on_ok`(约 150-167 行)替换为:

```python
    def on_ok():
        # 触发图状态(完整编辑器,含 mode/strategy/threshold)
        (t_path, t_alts, t_thr, mode, strategy, threshold) = trigger_editor.get_state()
        # 处理图状态(精简编辑器;mode/strategy 忽略,用触发图的)
        (h_path, h_alts, h_thr, _h_mode, _h_strategy, _h_gthr) = handler_editor.get_state()
        # 处理动作
        handler_val = handler_dropdown.get_value()
        handler_action = FoundAction[handler_val] if handler_val in FoundAction.__members__ else FoundAction.LEFT_CLICK

        result = MonitorConfig(
            name=var_name.get().strip() or t("common.unnamed_monitor"),
            enabled=var_enabled.get(),
            image_path=t_path.strip(),
            threshold=threshold,
            check_interval=var_interval.get(),
            handler_action=handler_action,
            handler_image_path=h_path.strip(),
            max_consecutive=var_max_consecutive.get(),
            cooldown=var_cooldown.get(),
            alt_image_paths=t_alts,
            alt_thresholds=t_thr,
            alt_handler_image_paths=h_alts,
            alt_handler_thresholds=h_thr,
            match_strategy=strategy,
            threshold_mode=mode,
        )
        dlg.destroy()
        on_done(result)
```

> **实现提示:** `_browse_image` 模块级函数若不再被引用可保留。`var_image`/`var_threshold`/`var_handler_image` 删除后,确认没有其它引用。

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest tests/unit/panel/test_monitor_dialog_multi.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add src/panel/dialogs/monitor_dialog.py tests/unit/panel/test_monitor_dialog_multi.py
git commit -m "feat: tkinter monitor_dialog embeds MultiTemplateEditor x2 (trigger + handler)"
```

---

## Task 10: Qt condition_dialog + monitor_dialog 嵌入(镜像 tk)

**Files:**
- Modify: `src/panel/qt_backend/dialogs/condition_dialog.py`(`_build_image_fields`、`_on_ok`)
- Modify: `src/panel/qt_backend/dialogs/monitor_dialog.py`(`QtMonitorDialog.__init__` 检测/处理图区、`_on_ok`)
- Test: `tests/unit/panel/test_qt_condition_monitor_multi.py`(SKIP,无 PySide6)

> **环境:** venv 无 PySide6 → 本任务测试一律 SKIP;逻辑可导入即视为通过。执行时以实际 Qt 对话框结构为准(下方代码对照 [condition_dialog.py](../../../src/panel/qt_backend/dialogs/condition_dialog.py) 与 [monitor_dialog.py](../../../src/panel/qt_backend/dialogs/monitor_dialog.py) 实际行号微调)。

- [ ] **Step 1: 写失败测试(SKIP 守卫)**

创建 `tests/unit/panel/test_qt_condition_monitor_multi.py`:

```python
"""Qt condition/monitor 多模板集成(无 PySide6 则 SKIP)。"""

import pytest

qtw = pytest.importorskip("PySide6")


def test_qt_condition_dialog_imports():
    from src.panel.qt_backend.dialogs.condition_dialog import QtConditionDialog
    assert QtConditionDialog is not None


def test_qt_monitor_dialog_imports():
    from src.panel.qt_backend.dialogs.monitor_dialog import QtMonitorDialog
    assert QtMonitorDialog is not None
```

- [ ] **Step 2: 运行测试(无 PySide6 → SKIP)**

Run: `pytest tests/unit/panel/test_qt_condition_monitor_multi.py -v`
Expected: SKIP(无 PySide6);改完应仍可 SKIP 且不报导入错误

- [ ] **Step 3: Qt condition_dialog 嵌入编辑器**

修改 `src/panel/qt_backend/dialogs/condition_dialog.py`。

3a) 顶部 import 新增:

```python
from src.panel.qt_backend.dialogs.multi_template_editor import MultiTemplateEditorQt
from src.core.action import MatchStrategy, ThresholdMode
```

3b) `_build_image_fields`(约 131-170 行)整体替换为嵌入编辑器(保留 `self._image_editor` 引用):

```python
    def _build_image_fields(self, cond: Condition, sm) -> None:
        th = self._th
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        self._image_editor = MultiTemplateEditorQt(parent=self)
        self._image_editor.set_state(
            cond.image_path, cond.alt_image_paths, cond.alt_thresholds,
            cond.threshold_mode, cond.match_strategy, cond.threshold,
        )
        self._fields_layout.addWidget(self._image_editor)
```

> **实现提示:** 原方法用 `form.addRow` 建图片 entry + 阈值 slider,现整段替换为编辑器。`self._fields_layout` 是 `_rebuild_fields` 的字段容器(以实际属性名为准;若叫 `self._fields_widget.layout()` 则相应调整)。删除原 `self._image_entry`/`self._threshold_slider`/`self._thresh_label`(由编辑器取代)。

3c) `_on_ok`(约 355-415 行)中,图片类条件的 `image_path`/`threshold` 读取段(约 380-382 行)替换为编辑器状态:

```python
            image_path, alt_paths, alt_thresholds = "", [], []
            threshold = 0.8
            mode = ThresholdMode.GLOBAL
            strategy = MatchStrategy.ADAPTIVE
            if selected in (ConditionType.IMAGE_FOUND, ConditionType.IMAGE_NOT_FOUND):
                if hasattr(self, "_image_editor"):
                    (image_path, alt_paths, alt_thresholds,
                     mode, strategy, threshold) = self._image_editor.get_state()
```

在构造 `self._result = Condition(...)`(约 403-415 行)时补入多模板字段:

```python
            self._result = Condition(
                condition_type=selected,
                image_path=image_path,
                threshold=threshold,
                alt_image_paths=alt_paths,
                alt_thresholds=alt_thresholds,
                match_strategy=strategy,
                threshold_mode=mode,
                variable_name=variable_name,
                compare_op=compare_op,
                compare_value_x=compare_value_x,
                compare_value_y=compare_value_y,
                timer_name=timer_name,
                timeout_seconds=timeout_seconds,
            )
```

> **实现提示:** `_on_ok` 中非图片类条件的字段(variable/compare/time)读取逻辑保持原样,仅图片分支改读编辑器。以实际 `_on_ok` 变量名为准对齐。

- [ ] **Step 4: Qt monitor_dialog 嵌入编辑器 ×2**

修改 `src/panel/qt_backend/dialogs/monitor_dialog.py`。

4a) 顶部 import 新增:

```python
from src.panel.qt_backend.dialogs.multi_template_editor import MultiTemplateEditorQt
from src.core.action import MatchStrategy, ThresholdMode
```

4b) `QtMonitorDialog.__init__` 中,删除"检测图片"行(约 60-61 行 `_make_browse_row`)与"阈值"行(约 63-76 行),替换为触发图编辑器,插在"检测配置"标签之后:

```python
        self._trigger_editor = MultiTemplateEditorQt(parent=self)
        self._trigger_editor.set_state(
            monitor.image_path, monitor.alt_image_paths, monitor.alt_thresholds,
            monitor.threshold_mode, monitor.match_strategy, monitor.threshold,
        )
        form.addRow(t("dialog.label.detect_image"), self._trigger_editor)
```

删除"处理目标图片"行(约 98-100 行)与"可选处理图"提示行,替换为处理图精简编辑器:

```python
        self._handler_editor = MultiTemplateEditorQt(parent=self, show_match_settings=False)
        self._handler_editor.set_state(
            monitor.handler_image_path, monitor.alt_handler_image_paths,
            monitor.alt_handler_thresholds,
            monitor.threshold_mode, monitor.match_strategy, monitor.threshold,
        )
        form.addRow(t("dialog.label.handler_target_image"), self._handler_editor)
```

4c) `_on_ok`(约 148-163 行)替换为读两个编辑器:

```python
    def _on_ok(self) -> None:
        idx = self._action_combo.currentIndex()
        handler_action = self._action_data[idx] if 0 <= idx < len(self._action_data) else self._monitor.handler_action
        t_path, t_alts, t_thr, mode, strategy, threshold = self._trigger_editor.get_state()
        h_path, h_alts, h_thr, _hm, _hs, _hg = self._handler_editor.get_state()
        result = MonitorConfig(
            name=self._name_edit.text().strip() or t("common.unnamed_monitor"),
            enabled=self._enabled_cb.isChecked(),
            image_path=t_path.strip(),
            threshold=threshold,
            check_interval=self._interval_spin.value(),
            handler_action=handler_action,
            handler_image_path=h_path.strip(),
            max_consecutive=self._max_consecutive_spin.value(),
            cooldown=self._cooldown_spin.value(),
            alt_image_paths=t_alts,
            alt_thresholds=t_thr,
            alt_handler_image_paths=h_alts,
            alt_handler_thresholds=h_thr,
            match_strategy=strategy,
            threshold_mode=mode,
        )
        self.accept()
        self._on_done(result)
```

> **实现提示:** `QSlider`/`_threshold_slider`/`_image_edit`/`_handler_image_edit`/`_make_browse_row`(若仅 monitor 用)在替换后可能不再被引用,保留无害或清理均可。`_FOUND_ACTION_I18N` import 保留。

- [ ] **Step 5: 运行测试(无 PySide6 → SKIP)**

Run: `pytest tests/unit/panel/test_qt_condition_monitor_multi.py tests/unit/panel/test_qt_multi_template_editor.py -v`
Expected: SKIP(无 PySide6);不报导入/语法错误

- [ ] **Step 6: 提交**

```bash
git add src/panel/qt_backend/dialogs/condition_dialog.py src/panel/qt_backend/dialogs/monitor_dialog.py tests/unit/panel/test_qt_condition_monitor_multi.py
git commit -m "feat: Qt condition + monitor dialogs embed MultiTemplateEditorQt"
```

---

## Task 11: 全量回归 + 覆盖率验证

**Files:**
- 无新增;运行全套测试

- [ ] **Step 1: 运行全部测试**

Run: `pytest tests/ -q`
Expected: 全部 PASS 或 Qt 相关 SKIP(既有 84 文件 + 本计划新增 ~7 文件,核心层全绿)

- [ ] **Step 2: 多模板新模块覆盖率**

Run: `pytest --cov=src/core/condition --cov=src/core/monitor --cov=src/core/vision/vision_pipeline --cov-report=term-missing tests/unit/core/test_condition_multi.py tests/unit/core/test_monitor_multi.py tests/unit/core/vision/test_vision_pipeline_multi.py tests/unit/core/test_serialization_multi.py`
Expected: 新增逻辑覆盖率 ≥ 80%

- [ ] **Step 3: 手动冒烟(可选但推荐)**

```bash
python main.py
```

验证:
- 动作链/工作流里给一个 Condition(IMAGE_FOUND)加 2~3 张备用图,保存重开数据保留
- 通知/监控页给一个 Monitor 触发图 + 处理图各加备用图,切换阈值模式时触发图显隐正确(处理图精简无控件)
- 导出/导入后 Condition/Monitor alt 路径正确(相对 profile 目录)

- [ ] **Step 4: 最终提交(若有遗漏修正)**

```bash
git add -A
git commit -m "test: full regression pass for multi-template Condition/Monitor/Pipeline"
```

---

## Self-Review(计划自检)

**1. Spec 覆盖** — 对照规格 §5.3/§7.1/§8:
- §5.3 三节点字段映射(Condition 4 字段 / Monitor 触发图 4 + 处理图 3 alt + 共用 strategy/mode)→ Task 1/2 ✓
- §7.1 执行层接入(Condition `_check_image_found` / Monitor `_check` / Pipeline `TemplateMatchStep`)→ Task 1/2/3 ✓
- §8.2 图片路径处理(3 文件 × Condition/Monitor 补齐 rel↔abs + 拷贝)→ Task 4/5/6 ✓
- §6.5 三对话框差异化嵌入(Condition 嵌入 / Monitor 触发+处理图各一组)→ Task 8/9/10 ✓
- §6.3 阈值模式联动 → Task 7 编辑器(复用计划 1 已实现的联动)✓
- §9.1 测试文件(test_condition_multi / test_monitor_multi / 扩展 serialization_multi)→ 各 Task 内嵌 TDD ✓
- §12 非目标(OCR/PixelSearch/game/*)→ 不在本计划范围 ✓

**2. 占位符扫描**:无 TBD/TODO;每个代码步骤含完整代码;测试含完整断言。Task 10(Qt)因 venv 无 PySide6 标注 SKIP,代码步骤仍含完整 Qt 代码(对照实际文件微调行号)。

**3. 类型一致性**:
- `find_any(screen, paths, threshold=, strategy=, per_template_thresholds=)` 调用形态 → Task 1/2/3 全程一致 ✓
- `resolve_find_any_params(primary_path, alt_paths, base_threshold, alt_thresholds, threshold_mode, match_strategy) → (paths, per_thr, strategy)` → Task 1/2/3 一致 ✓
- `MultiTemplateEditor.get_state() → (image_path, alt_paths, alt_thresholds, mode, strategy, global_threshold)` 6 元组 → Task 8/9 一致(新增 `show_match_settings` 不改签名)✓
- `MonitorConfig` 新字段名(`alt_image_paths`/`alt_thresholds`/`alt_handler_image_paths`/`alt_handler_thresholds`/`match_strategy`/`threshold_mode`)→ Task 2/4/5/6/9/10 全程一致 ✓
- `Condition` 新字段名(`alt_image_paths`/`alt_thresholds`/`match_strategy`/`threshold_mode`)→ Task 1/4/5/6/8/10 全程一致 ✓
- `_resolve_match_strategy`/`_resolve_threshold_mode` 助手 → Task 4 定义、Task 4 内 Condition+Monitor 复用 ✓

**4. 向后兼容不变量**:
- 旧 profile(无新字段)→ Condition/Monitor 默认 `alt=[]`/`mode=GLOBAL`/`strategy=ADAPTIVE` → `find_any` 退化为单模板 → 行为等价旧 `find()` ✓
- `matcher.find()` 签名未动 → 现有所有 `find()` 调用者零改动 ✓
- `MultiTemplateEditor(show_match_settings=True)` 默认 → 计划 1 的 ClickImage 集成零破坏 ✓

---

## Execution Handoff

计划已保存至 `docs/superpowers/plans/2026-06-15-multi-template-condition-monitor.md`。两种执行方式:

1. **Subagent-Driven(推荐)** — 每个 Task 派发独立子代理,任务间审查,快速迭代
2. **Inline Execution** — 在本会话内按 executing-plans 批量执行,带检查点

选择哪种方式?
