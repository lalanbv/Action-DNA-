# 多模板检测(Multi-Template Detection)设计规格

- **日期**:2026-06-14
- **状态**:设计已确认,待转入实现计划
- **作者**:设计与实现协作产出
- **关联**:[CLAUDE.md](../../../CLAUDE.md) · [vision_pipeline.py](../../../src/core/vision/vision_pipeline.py) · [capture.py](../../../src/core/vision/capture.py)

---

## 1. 背景与问题

### 1.1 用户痛点

挂机(unattended automation)场景中,图片检测(模板匹配)频繁出现"明明按钮在屏幕上却检测失败"的问题,导致动作链中断。

### 1.2 根因:状态变体匹配问题(State-Variant Matching)

一个按钮在运行时存在**互斥的多种视觉状态**,而当前模板匹配只支持单张模板:

| 状态 | 触发条件 | 视觉差异 |
|------|---------|---------|
| 默认态(default) | 未点击 / 无焦点 | 基准亮度 |
| 悬停态(hover) | 鼠标浮在上面 | 高亮边框 / 底色变深 |
| 按下态(pressed) | 鼠标点击中 | 内阴影 / 位移 |
| 已激活态(active/toggle) | 被点过 / 选中 | 持续高亮 / 勾选 |
| 禁用态(disabled) | 不可用 | 灰度降低 |

**机理**:[click_image_descriptor.py](../../../src/core/engine/descriptors/click_image_descriptor.py) 调用 [TemplateMatcher.find()](../../../src/core/vision/capture.py) 时只接受单张模板。匹配采用归一化互相关(NCC,`cv2.TM_CCOEFF_NORMED`),要求模板与运行时画面的像素高度一致才能过阈值(默认 0.8)。当按钮进入了与截图时不同的状态,像素差异足以让置信度跌破阈值 → 误判"未找到" → 动作链中断。

### 1.3 解决方向

**多模板 OR 匹配**:一个检测动作可挂载 N 张模板(每种状态一张),**任意一张匹配即视为找到**,使用该命中结果的位置。用户把每个状态各截一张即可彻底消除状态漂移导致的检测失败。

### 1.4 设计目标(用户明确诉求)

1. **好用**:小白零配置即可使用,专家可深度调参
2. **可靠**:不引入新的检测失败模式,严格向后兼容
3. **性能好**:挂机循环下额外开销趋近于零(缓存复用)
4. **准确度高**:自适应算法 + 二次验证保证不误匹配
5. **兼容性强**:覆盖全部检测类节点,兼容所有匹配策略组合

---

## 2. 改造范围

用户要求:**全部检测类节点**(基于模板匹配的)统一获得多模板能力。

### 2.1 模板匹配消费者枚举(经代码核实)

**用户可配置的检测节点(本次主改造范围)**:

| 节点 | 数据模型 | 匹配入口 | 对话框(tk + Qt) |
|------|---------|---------|----------------|
| ClickImage | `ClickImageStep` ([step_types.py:44](../../../src/core/step_types.py)) | [click_image_descriptor.py:168](../../../src/core/engine/descriptors/click_image_descriptor.py) `_try_single_match` | tk `click_image_dialog.py` + Qt `qt_backend/dialogs/click_image_dialog.py` |
| Condition | `Condition` ([condition.py:52](../../../src/core/condition.py)) | [condition.py:172](../../../src/core/condition.py) `_check_image_found` | tk `condition_dialog.py` + Qt 对应 |
| Monitor | `MonitorConfig` ([monitor.py](../../../src/core/monitor.py)) | [monitor.py:175,216](../../../src/core/monitor.py)(触发图 + 处理图) | tk `monitor_dialog.py` + Qt 对应 |

> **注**:OCR / PixelSearch 不属于模板匹配(分别是文字识别与颜色搜索),不在范围内。

**基础设施层**:
- `TemplateMatcher`([capture.py](../../../src/core/vision/capture.py))— 新增 `find_any()` 编排入口
- `VisionPipeline.TemplateMatchStep`([vision_pipeline.py:201](../../../src/core/vision/vision_pipeline.py))— 支持多模板(向后兼容)

**内部模块** `src/game/*`(combat/navigation/task):使用硬编码单模板调用 `matcher.find()`,属内置逻辑而非用户节点。本次不强制改造,但因 `find_any()` 提供在匹配器层,这些模块若后续扩展状态资源可平滑迁移。

---

## 3. 架构设计

### 3.1 核心选型:多模板编排逻辑置于 `TemplateMatcher`

经对比三个方案,选定 **方案 A:在 `TemplateMatcher` 新增 `find_any()`** 作为唯一编排入口:

| 方案 | 说明 | 结论 |
|------|------|------|
| **A. `TemplateMatcher.find_any()`** | 核心匹配器统一提供多模板编排,所有消费者调用它 | **采用**:单一真相源、缓存天然复用、零重复逻辑 |
| B. 各描述符自己循环 `find()` | ClickImageDescriptor/ConditionEvaluator/Monitor 各写一遍 | 否决:逻辑三份重复,策略/阈值改动需改三处,易不一致 |
| C. 新建 `MultiTemplateMatcher` 包装类 | 再包一层转发 | 否决:多一层间接,收益低 |

**理由**:多模板的本质是"对同一张截图跑 N 次单模板匹配再汇总"。单模板匹配的全部复杂度(多尺度 / 多策略 / 验证 / 缓存)都已在 `find()` 内。`find_any()` 只做"循环 + 策略汇总",每张模板的 `find()` 调用各自命中现有 LRU 缓存 → N 张模板的额外开销 ≈ 0(缓存命中时),最坏情况才是 N 次全量匹配。

### 3.2 共享逻辑下沉(双框架统一规则)

遵循"可统一的部分务必统一规则与规格"原则,框架无关的纯逻辑抽到 core 层,tk 与 Qt 对话框均调用:

```
src/core/vision/match_config.py   ← 新增,框架无关纯逻辑
  ├─ AUTO_THRESHOLD = 0.72                # AUTO 模式使用的稳健阈值常量
  ├─ normalize_templates(...)             # 去空/去重/对齐长度
  ├─ effective_thresholds(mode, ...)      # 按 ThresholdMode 解析每张模板的有效阈值
  └─ resolve_find_any_params(...)         # 汇总出最终传给 find_any() 的 (paths, per_thresholds, strategy)
```

对话框只负责**渲染 + 采集输入**,所有阈值 / 策略解析经此模块 → tk 与 Qt 行为完全一致,杜绝"一套逻辑写两遍导致漂移"。

---

## 4. 核心匹配算法

### 4.1 `TemplateMatcher` 零破坏重构

把现有 `find()` 的匹配主体抽成 `_find_core()`,返回 `(rect, best_score, from_cache)`。`find()` 变薄壳只取 rect(签名与返回值完全不变 → 全部现有调用者零改动);新增 `find_with_score()` 取 `(rect, score)`:

```python
def find(self, screen, template_path, threshold=0.8, screen_hash=None):
    """签名与返回值完全不变 → 向后兼容所有现有调用。"""
    rect, _score, _ = self._find_core(screen, template_path, threshold, screen_hash)
    return rect

def find_with_score(self, screen, template_path, threshold=0.8, screen_hash=None):
    """单模板匹配,返回 (rect, best_confidence)。rect 为 None 时 best_confidence 仍返回最高分。"""
    rect, score, _ = self._find_core(...)
    return rect, score
```

**缓存小改**:`_MatchCacheEntry` 增加 `score` 字段(原只存 rect),让 `find_with_score` 命中缓存时也能返回置信度。LRU key `(screen_hash, template_path, round(threshold,2))` 不变。

### 4.2 `find_any()` 智能自适应混合算法

返回不可变 `MultiMatchResult`:

```python
@dataclass(frozen=True)
class MultiMatchResult:
    path: str                                  # 命中的模板路径
    rect: tuple[int, int, int, int]            # 命中位置 (x, y, w, h)
    confidence: float                          # 命中置信度
    strategy_used: str                         # "early_exit"|"best_of"|"first_match"|"adaptive_best"

def find_any(
    self,
    screen: np.ndarray,
    template_paths: list[str],
    threshold: float,
    *,
    strategy: MatchStrategy = MatchStrategy.ADAPTIVE,
    per_template_thresholds: list[float] | None = None,
    screen_hash: int | None = None,
) -> MultiMatchResult | None:
    """多模板匹配编排入口。任一命中即视为找到。"""
```

**ADAPTIVE(默认)执行流程**:

```
candidates = []
for i, path in enumerate(template_paths):       # 按用户排列顺序
    eff_threshold = per_template_thresholds[i] if per_template_thresholds else threshold
    rect, score = self.find_with_score(screen, path, eff_threshold, screen_hash)

    if rect is not None:                         # 该模板命中(已过 eff_threshold)
        candidates.append(MultiMatchResult(path, rect, score, ""))

        # ① 顺序优先 + 提前退出(快速路径):高确信直接定锤
        #    注意:与"该模板"的门控阈值 eff_threshold 比较,PER_TEMPLATE 下各模板独立,语义一致
        if strategy == FIRST_MATCH:
            return candidates[-1] (strategy_used="first_match")
        if strategy == ADAPTIVE and score >= eff_threshold + _EARLY_EXIT_MARGIN:  # 复用现有常量 0.08
            return candidates[-1] (strategy_used="early_exit")
    # ② 未触发提前退出(候选都是"勉强过阈值")→ 继续试下一张

# ③ 全部跑完仍无高确信候选 → 全局最佳兜底(平局/模糊态取最高置信度)
if not candidates:
    return None
if strategy in (ADAPTIVE, BEST_CONFIDENCE):
    return max(candidates, key=lambda c: c.confidence) (strategy_used="best_of" 或 "adaptive_best")
```

### 4.3 三策略如何"兼容"

同一份 `find_any()` 实现,通过 `strategy` 参数切换**终止条件**,候选收集逻辑零重复:

| 策略 | 终止条件 | 特性 |
|------|---------|------|
| `ADAPTIVE`(默认) | 高确信提前退出,否则扫完取最佳 | 快(正常只跑 1~2 张)+ 稳(模糊态取最佳) |
| `FIRST_MATCH` | 第一个 `rect` 命中即返回 | 最快、最可预测,纯顺序优先 |
| `BEST_CONFIDENCE` | 总是扫完全部,返回 `max(candidates)` | 最稳,无提前退出 |

### 4.4 关键技术细节

1. **缓存复用**:`find_any()` 不自建缓存,依赖每个内部 `find_with_score`/`find` 调用的 LRU 缓存。同一画面重复检测时,N 张模板第二次起全部缓存命中 → 挂机循环下近乎零开销。
2. **`_verify_match` 二次验证**:继续在 `find()`/`_find_core()` 内部生效,`find_any()` 透明继承 → AUTO 模式可放心用偏宽松的 0.72 阈值,误匹配由验证层拦截。
3. **位置语义**:返回的是命中那张模板的匹配位置,点击其中心。各状态模板是同一按钮、位置一致 → 无需特殊处理。
4. **`_EARLY_EXIT_MARGIN = 0.08`**:直接复用现有常量,不引入新魔法数。

---

## 5. 数据模型设计

### 5.1 新增两个枚举(置于 `action.py`,与 `DetectMode` 同位)

```python
class MatchStrategy(Enum):
    ADAPTIVE = "ADAPTIVE"              # 智能混合(默认):顺序优先快 + 全局最佳稳
    FIRST_MATCH = "FIRST_MATCH"        # 纯顺序优先:第一个命中即返回
    BEST_CONFIDENCE = "BEST_CONFIDENCE"# 纯全局最佳:总是扫完全部取最高

class ThresholdMode(Enum):
    AUTO = "AUTO"                      # 智能零配置:忽略阈值,系统自动兜底
    GLOBAL = "GLOBAL"                  # 统一阈值:所有模板共用 threshold
    PER_TEMPLATE = "PER_TEMPLATE"      # 逐模板:基础阈值 + 每模板可选覆盖
```

### 5.2 `ClickImageStep` 增量式字段扩展(向后兼容)

```python
@dataclass
class ClickImageStep(BaseStep):
    # ── 既有字段完全不动,旧 profile 直接兼容 ──
    image_path: str = ""               # 主模板(第一个),保留语义
    threshold: float = 0.8             # 全局 / 主模板阈值
    detect_mode: DetectMode = DetectMode.SKIP_IF_NOT_FOUND
    # ... 其余既有字段不变 ...

    # ── 新增多模板字段 ──
    alt_image_paths: list[str] = field(default_factory=list)
    # 与 alt_image_paths 平行;None = 继承全局 / 自动;具体浮点 = 独立覆盖
    alt_thresholds: list[float | None] = field(default_factory=list)
    match_strategy: MatchStrategy = MatchStrategy.ADAPTIVE
    threshold_mode: ThresholdMode = ThresholdMode.GLOBAL
```

**设计要点**:
- `image_path` + `threshold` **原封不动** → 旧 `profile.json` 零修改加载,行为完全不变。
- 完整模板集 = `[image_path] + alt_image_paths`;主模板永远第一个(顺序优先时优先命中)。
- `alt_thresholds` 用**平行列表 + None 哨兵**,JSON 原生支持(`null`),无需 int-key 字典(JSON 不支持)或结构体嵌套(破坏 `image_path` 纯字符串兼容)。
- `alt_thresholds[i] is None` = "继承",有值 = "覆盖",语义清晰。

### 5.3 三节点的字段映射

| 节点 | 主模板字段 | 备用模板字段 | 新增配置字段 |
|------|-----------|------------|------------|
| ClickImageStep | `image_path` | `alt_image_paths` + `alt_thresholds` | `match_strategy`, `threshold_mode` |
| Condition | `image_path` | `alt_image_paths` + `alt_thresholds` | `match_strategy`, `threshold_mode` |
| Monitor(触发图) | `image_path` | `alt_image_paths` + `alt_thresholds` | `match_strategy`, `threshold_mode` |
| Monitor(处理图) | `handler_image_path` | `alt_handler_image_paths` + `alt_handler_thresholds` | *(共用本节点的一套 strategy/mode)* |

Monitor 的触发图与处理图各加一组备用列表,但**共用同一套 `match_strategy` / `threshold_mode`**(一个监控节点一套策略,避免配置爆炸)。

### 5.4 默认值决策:`threshold_mode` 默认 = `GLOBAL`

**理由**:旧 `profile.json` 没有 `threshold_mode` 字段 → 加载时取默认 `GLOBAL` → 继续使用用户当年设的 `threshold` → **零行为漂移**。若默认成 AUTO,旧配置里用户精心调的 0.8 会被静默忽略,是隐患。

**两套默认解耦**:
- **数据模型字段默认** = `GLOBAL`(保证旧 profile 加载零漂移)
- **对话框新建默认** = `AUTO`(新用户上手即零配置,符合"小白不用在意"诉求;老用户编辑旧步骤时仍显示其保存的 GLOBAL)

### 5.5 AUTO 模式阈值

定义常量 `AUTO_THRESHOLD = 0.72`(比 0.8 宽松,容忍状态色差),靠现有 `_verify_match` 二次验证拦截误匹配。该值集中在一处常量(`match_config.py`),可后续调优。AUTO 模式下 `resolve_find_any_params` 内部把 `threshold` 统一替换为 `AUTO_THRESHOLD`。

### 5.6 输入校验(系统边界)

加载时与对话框保存时各做一次归一化(`normalize_templates`):
- `len(alt_thresholds)` 对齐到 `len(alt_image_paths)`(不足补 `None`,多余截断)。
- 过滤掉空路径、去重(同一路径只保留第一次出现)。
- `alt_image_paths` 中路径若不存在,记 warning 但不阻断(降级为跳过该模板)。

---

## 6. 双框架 UI 设计

遵循双框架规则,先定**框架无关 UI 规格**,tk 与 Qt 两套实现严格遵循同一规格。

### 6.1 统一布局规格(三对话框共用"多模板图片管理器"组件)

ClickImage / Condition / Monitor 三个对话框的图片区域,用同一套可复用的多模板管理器(tk 版一个工厂函数、Qt 版一个 Widget,规格一致):

```
┌─ 模板图片(主图 + 状态备用图)─────────────────────────────┐
│ ┌缩略图┐ 主图   btn_default.png   [主·置顶·不可删]        │ ← image_path
│ ┌缩略图┐ 备用1  btn_hover.png     [阈值:继承☐自定义] ↑↓ ✕ │ ← alt[0]
│ ┌缩略图┐ 备用2  btn_pressed.png   [阈值:继承☐自定义] ↑↓ ✕ │ ← alt[1]
│ ┌缩略图┐ 备用3  btn_active.png    [阈值:继承☐自定义] ↑↓ ✕ │ ← alt[2]
│ [+ 添加备用图片]   ⓘ 第一个为主图;顺序 = 命中优先级       │
└──────────────────────────────────────────────────────────┘
┌─ 匹配设置 ────────────────────────────────────────────────┐
│ 阈值模式 [智能自动 AUTO ▼]   ← AUTO / GLOBAL / PER_TEMPLATE│
│ 匹配策略 [智能混合 ADAPTIVE ▼] ← ADAPTIVE / FIRST / BEST   │
│         (旁注:一般无需修改)                              │
│ 全局阈值 [0.80]              ← 仅 GLOBAL / PER_TEMPLATE 显示│
└──────────────────────────────────────────────────────────┘
```

### 6.2 每行控件

- **缩略图**(~40×40):tk 用 `PIL.ImageTk`、Qt 用 `QPixmap`,复用各自已有预览逻辑。
- **路径 + 浏览按钮**:主图可直接替换;备用图可改路径。
- **阈值单元**:一个小 spinbox(0.1~1.0)+ `☐自定义阈值` 复选框。未勾选 → 存 `None`(继承);勾选 → spinbox 可编辑,存具体值。
- **排序按钮** `↑↓`:主图锁定置顶无此按钮;移动时 path 与 threshold 同步移动,保持平行列表对齐。
- **删除按钮** `✕`:主图无;删除时同步删对应 threshold。

### 6.3 阈值模式 ↔ 控件显隐联动(两框架同一矩阵)

| 阈值模式 | 全局阈值框 | 每行阈值单元 | 用户心智 |
|---------|-----------|------------|---------|
| **AUTO** | 隐藏 | 隐藏(整列) | "我啥都不用管,丢图就行" |
| **GLOBAL** | 显示可编辑 | 隐藏(显示"统一"灰字) | "所有图一个标准" |
| **PER_TEMPLATE** | 显示(作基础) | 显示(可勾选自定义) | "某张图模糊,单独调" |

**匹配策略下拉恒显示**(AUTO 下也显示,默认 ADAPTIVE,带旁注"一般无需修改"),因为策略与阈值正交,专家在 AUTO 下也可能想强制 BEST_CONFIDENCE。

### 6.4 新建 vs 编辑的默认行为(两框架一致)

- **新建步骤**:对话框默认 `阈值模式 = AUTO`、`匹配策略 = ADAPTIVE`,全局阈值框隐藏 → 用户只管加图。
- **编辑既有步骤**:显示其保存的 mode / strategy(旧 profile 无这些字段 → 显示 GLOBAL + ADAPTIVE,全局阈值 = 其原 threshold)。

### 6.5 三对话框差异化嵌入点

同一套"多模板管理器"组件,嵌入位置不同:
- **ClickImage**:替换现有单行 image_path([click_image_dialog.py:62-80](../../../src/panel/dialogs/click_image_dialog.py)),其余(retry / found_action / detect_mode)不动。
- **Condition**:在 IMAGE_FOUND / IMAGE_NOT_FOUND 条件类型的图片区嵌入(含主图 + 备用);非图片条件类型不显示。
- **Monitor**:触发图区一组、处理图区一组(各一个管理器实例,共用本节点的 strategy / threshold_mode)。

### 6.6 i18n 新增(中英双语)

统一 key 前缀 `dialog.multi_template.*` / `dialog.match_strategy.*` / `dialog.threshold_mode.*`,约 15 条,例如:
- `dialog.multi_template.primary` → "主图" / "Primary"
- `dialog.multi_template.alt` → "备用图 {n}" / "Alt {n}"
- `dialog.multi_template.add` → "+ 添加备用图片" / "+ Add alt image"
- `dialog.multi_template.hint_order` → "第一个为主图;顺序 = 命中优先级" / "First is primary; order = match priority"
- `dialog.threshold_mode.auto` → "智能自动(零配置)" / "Auto (zero-config)"
- `dialog.match_strategy.adaptive` → "智能混合(推荐)" / "Adaptive (recommended)"

### 6.7 边界与容错

- 缩略图加载失败 → 显示占位"无预览",不阻断(沿用现有 `_update_preview` 容错)。
- 备用图路径重复 / 为空 → 保存时 `normalize_templates` 自动去重去空,不打断用户。
- 误删全部备用图 → 自动退化为单主图模式(等价旧行为)。

---

## 7. 执行层接入

### 7.1 改动点(精确到方法)

| 节点 | 文件:方法 | 改动 |
|------|----------|------|
| ClickImage | [click_image_descriptor.py:159](../../../src/core/engine/descriptors/click_image_descriptor.py) `_try_single_match` | 不再收 `template_path`,改收 `step`;经 `match_config.resolve_find_any_params(step)` 解析出 `(paths, per_thresholds, strategy)`,调 `matcher.find_any()`,返回命中 rect |
| | `_find_with_retries` / `_wait_until_found` | 逻辑不变(retry / wait 作用于**整个模板集**),仅改调用入口 + 日志带"命中模板名 / 策略" |
| | `_handle_not_found` | 不变(detect_mode 语义:整个集合都没找到才算 not found) |
| Condition | [condition.py:172](../../../src/core/condition.py) `_check_image_found` | 同理解析 cond 的多模板配置,调 `find_any`;`IMAGE_FOUND` = 任一命中,`IMAGE_NOT_FOUND` = 全部未命中 |
| Monitor | [monitor.py:175,216](../../../src/core/monitor.py) | 触发图与处理图各自一组多模板,共用本节点 strategy / mode |
| Pipeline | [vision_pipeline.py:201](../../../src/core/vision/vision_pipeline.py) `TemplateMatchStep` | 增可选 `alt_template_paths` + `match_strategy`;单模板时走原路径,多模板时走 `find_any`(向后兼容) |

### 7.2 关键不变量

- 三种 `detect_mode`(WAIT / SKIP / FAIL)语义从"单模板找到没"升级为"**整个模板集合**找到没"。
- `_execute_found_action` 拿到的是命中那张模板的 rect,点击其中心(各状态模板同位置,无需特殊处理)。

---

## 8. 序列化与配置管理

### 8.1 通用序列化(无需特殊代码)

通用序列化用 `dataclasses.asdict()`([serialization.py:63](../../../src/core/serialization.py)),新增字段**自动往返** JSON。`list[str]`、`list[float | None]`、枚举均原生支持。

### 8.2 图片路径处理(3 文件机械式补齐)

对 ClickImageStep / Condition / MonitorConfig 各加一组循环,模式与现有 `image_path` 处理逐字镜像:

| 文件 | 现有 | 新增 |
|------|------|------|
| [serialization.py:178](../../../src/core/serialization.py) 加载 | `image_path` rel→abs | 循环 `alt_image_paths` 逐个 rel→abs(Monitor 再加 `alt_handler_image_paths`) |
| [importer.py:215](../../../src/core/io/importer.py) 保存 | `image_path` abs→rel | 循环 `alt_image_paths` 逐个 abs→rel |
| [profile_manager.py:150](../../../src/panel/profile_manager.py) 保存 | 拷贝 `image_path`→images/ + 存 rel | 循环拷贝每个 `alt_image_paths` 到 images/ + 存 rel |

### 8.3 双向向后兼容验证

- **旧 profile → 新代码**:无新字段 → 默认 `alt=[]` / `strategy=ADAPTIVE` / `mode=GLOBAL` → `find_any` 退化为单模板 → **行为完全等价旧 `find()`**。
- **新 profile → 旧代码**:旧代码读 `image_path`(未变),忽略未知字段 → 当单模板用(备用图被忽略)→ 优雅降级。

---

## 9. 测试策略

遵循 TDD 强制工作流(先写 RED 测试 → 跑失败 → 实现 → GREEN → 重构 → 验证 80%+ 覆盖率)。

### 9.1 新增测试文件

| 文件 | 覆盖内容 |
|------|---------|
| `tests/unit/core/vision/test_find_any.py` | `find_with_score` + `find_any` 三策略表驱动(早退 / 最佳 / 全 miss / 单模板退化 / 空列表) |
| `tests/unit/core/test_match_config.py` | `normalize_templates`(去空 / 去重 / 对齐)、`effective_thresholds`(AUTO/GLOBAL/PER_TEMPLATE)、`resolve_find_any_params` |
| `tests/unit/core/engine/test_click_image_multi.py` | 主图 miss、备用图 hit 仍成功点击;三种 detect_mode 在集合维度的语义 |
| `tests/unit/core/test_condition_multi.py` | `IMAGE_FOUND` / `IMAGE_NOT_FOUND` 在多模板下的判定 |
| `tests/unit/core/test_monitor_multi.py` | 触发图 + 处理图多模板 |
| `tests/unit/core/test_serialization_multi.py` | 三类对象多模板字段往返 + rel/abs 转换 + 图片拷贝;**旧 JSON 无新字段加载**回归 |
| `tests/unit/panel/test_click_image_dialog_multi.py` | tk 侧 `_get_result`/`_populate_fields` 数据往返(纯数据方法,免渲染);Qt 侧同 |

### 9.2 回归

现有 84 个测试文件全跑通,尤其 ClickImage / Condition / Monitor 相关用例单模板行为零变化。

---

## 10. 日志与可观测性

挂机排障关键。`find_any` 命中时聚合日志一条,沿用现有 i18n 日志风格:

```
[MULTI] "btn_hover.png" 命中 (conf=0.91, 策略=early_exit, 第2/4张) ✓
```

全 miss 时汇总:

```
[MULTI] 4 张模板全部未匹配 ✗ (主图 btn_default.png conf=0.62, 最佳备用 btn_hover.png conf=0.58)
```

让用户挂机出问题时能一眼看出是哪张图该补 / 哪张阈值该调。

---

## 11. 文件改动清单

```
新增:
  src/core/vision/match_config.py                       # 共享纯逻辑
  src/core/vision/__init__.py 导出                       # (小改)
  tests/.../*.py ×7                                      # 测试

修改:
  src/core/action.py                                    # +2 枚举
  src/core/vision/capture.py                            # _find_core 拆分 + find_with_score + find_any + MultiMatchResult
  src/core/step_types.py                                # ClickImageStep +4 字段
  src/core/condition.py                                 # Condition +4 字段 + _check_image_found
  src/core/monitor.py                                   # MonitorConfig +多模板字段 + 匹配调用
  src/core/vision/vision_pipeline.py                    # TemplateMatchStep 多模板
  src/core/serialization.py                             # alt 路径 rel→abs
  src/core/io/importer.py                               # alt 路径 abs→rel
  src/panel/profile_manager.py                          # alt 图片拷贝
  src/panel/dialogs/click_image_dialog.py               # tk 多模板管理器
  src/panel/qt_backend/dialogs/click_image_dialog.py    # Qt 多模板管理器
  src/panel/dialogs/condition_dialog.py                 # tk(Condition 嵌入)
  src/panel/qt_backend/dialogs/condition_dialog.py      # Qt
  src/panel/dialogs/monitor_dialog.py                   # tk(Monitor 嵌入×2)
  src/panel/qt_backend/dialogs/monitor_dialog.py        # Qt
  src/utils/translations/zh.json / en.json              # ~15 条 i18n
```

---

## 12. 非目标 / 范围外

明确排除,避免范围蔓延:

- **不改造** OCR、PixelSearch(非模板匹配)。
- **不强制改造** `src/game/*` 内置模块(硬编码单模板,可选未来迁移)。
- **不引入** 自动状态采集(如"鼠标悬停自动截图各状态")— 用户手动提供状态图即可,自动采集复杂度高且易引入不稳定。
- **不改动** `image_path` / `threshold` 既有字段语义(硬性向后兼容)。
- **不实现** 多模板的"AND 匹配"(要求全部命中)— 当前需求是 OR(任一命中),AND 属不同语义,不在范围。

---

## 13. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 缓存未存 score 导致 `find_with_score` 退化 | `_MatchCacheEntry` 增加 score 字段,缓存命中也返回置信度 |
| PER_TEMPLATE 平行列表错位 | `normalize_templates` 加载/保存时强制对齐长度 |
| AUTO 模式 0.72 阈值误匹配 | 复用现有 `_verify_match` 二次验证拦截;常量集中可调 |
| 双框架 UI 漂移 | 配置逻辑下沉 `match_config.py`,渲染层只采集输入 |
| 旧 profile 行为漂移 | `threshold_mode` 默认 GLOBAL;`find()` 签名不变 |
