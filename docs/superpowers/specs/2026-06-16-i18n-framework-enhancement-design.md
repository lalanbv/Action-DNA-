# i18n 多语言框架优化与补齐设计

- **日期**: 2026-06-16
- **状态**: 待审查
- **方案**: A(全量分阶段)
- **范围**: 框架能力 + 工具链 + 补齐 166 处硬编码中文

---

## 1. 背景与现状

### 1.1 调研发现(基于 2026-06-16 工作树)

| 维度 | 现状 | 说明 |
|------|------|------|
| 翻译文件对齐 | ✅ zh/en 各 778 key,零缺失、零未翻译 | "翻译文件缺 key"不是问题 |
| 框架 API | ✅ 较完备 | `t()` / `set_language` / 观察者 / zh 回退 / 内存缓存 / 延迟校验 / 线程安全 |
| i18n 测试 | ⚠️ 仅 2 个文件 | `test_i18n.py` + `test_i18n_multi_template.py`,覆盖度有限 |
| 硬编码中文字符串字面量 | ⚠️ 约 166 处未走 i18n | logger 152 处 + 异常消息 14 处 |
| 中文注释/docstring | 1563+ 处 | 按项目规范**保留不动** |

### 1.2 三类问题

1. **框架工程化缺失**:无 key 提取/校验工具,翻译随版本演进易腐化(代码新增 `t("x")` 但忘加 json key,或 json key 弃用后残留)
2. **框架运行时缺陷**:
   - `t()` 的 `.format()` 失败时 `except (KeyError, IndexError): pass` 静默吞掉,返回 `{name}` 半成品;`ValueError` 未捕获会抛出未处理异常
   - 无复数支持(pluralization)
   - 无系统 locale 自动检测(首次启动无法据系统语言选 zh/en)
   - 无"可用语言列表"API
3. **内容缺失**:166 处硬编码中文(logger 152 + 异常 14),英文用户/英文环境看到中文

---

## 2. 目标与非目标

### 2.1 目标

1. 增强 `i18n.py` 运行时能力:format 错误修复、可用语言列表、locale 检测、复数(全部向后兼容)
2. 建立 key 校验工具链:`i18n_lint.py`(AST 扫描核心)+ `scripts/lint_i18n_keys.py`(CLI)+ pytest gate
3. 补齐 166 处硬编码中文(logger 152 + 异常 14 全部 i18n,新增 ~166 key)

### 2.2 非目标(YAGNI)

- 第三种语言脚手架(本次不做,但 `get_available_languages` + locale 检测已为扩展铺路)
- 完整 ICU MessageFormat(轻量复数约定已满足当前需求)
- 外部翻译管理平台集成

---

## 3. 总体架构

### 3.1 模块划分

| 文件 | 动作 | 职责 |
|------|------|------|
| `src/utils/i18n.py` | 改 | 4 项运行时能力增强(向后兼容) |
| `src/utils/i18n_lint.py` | **新增** | key 校验核心逻辑(AST 扫描 + 对比 + 报告),CLI 与 pytest 共用 |
| `scripts/lint_i18n_keys.py` | **新增** | CLI 入口(人工运行 / CI) |
| `tests/unit/utils/test_i18n.py` | 扩充 | 4 项新能力测试 |
| `tests/unit/utils/test_i18n_lint.py` | **新增** | lint 逻辑单测 |
| `tests/unit/utils/test_i18n_keys.py` | **新增** | pytest gate(零缺失/零不对齐) |
| `src/utils/translations/{zh,en}.json` | Phase 2 补 ~166 key | |
| 166 个调用点(分布在约 40+ 文件) | Phase 2 替换 | |

### 3.2 设计原则

- **向后兼容优先**:所有 i18n.py 改动不破坏现有 778 key 与 128 个调用文件的 `t()` 用法
- **工具链先行**:Phase 1 建立校验工具,Phase 2 补齐时用其兜底,保证可验证、可回归
- **不可变数据**:`LintFinding` / `LintReport` 用 `@dataclass(frozen=True)`
- **零外部依赖**:复数等能力内置实现,不引入 babel 等重依赖(符合项目"优雅降级"风格)

---

## 4. Phase 1 详细设计

### 4.1 i18n.py 四项增强

#### ① format 错误修复(bug 级)

**现状**:
```python
if kwargs:
    try:
        text = text.format(**kwargs)
    except (KeyError, IndexError):
        pass
return text
```
问题:`KeyError/IndexError` 被吞返回 `{name}` 半成品;`ValueError` 未捕获会崩。

**改为**:
```python
if kwargs:
    try:
        text = text.format(**kwargs)
    except (KeyError, IndexError, ValueError) as exc:
        _logger.warning("i18n format failed for key %r: %s", key, exc)
        # 返回带占位符的原文本(开发者一眼可见),不静默
return text
```
策略:format 失败记 warning + 返回带占位符的原文本(降级而非崩溃,占位符可见便于发现)。

#### ② 可用语言列表

```python
def get_available_languages() -> list[str]:
    """返回 translations/ 目录下所有可用语言代码(如 ['en', 'zh']),排序去重。"""
```
扫描 `translations/*.json`,返回排序后语言码列表。供设置页动态渲染语言下拉框。

#### ③ 系统 locale 自动检测

```python
def detect_system_locale() -> str:
    """检测系统首选语言,映射到支持的 i18n 语言码。失败返回 'zh'。"""
```
- 优先 `locale.getdefaultlocale()`(跨平台)
- macOS/Windows 备选系统 API
- 映射规则:`zh* → zh, en* → en, 其他 → zh`
- `init()` 首次启动且 settings.json 未指定 `language` 时用检测结果;已指定则尊重用户选择

#### ④ 复数支持(轻量内置)

约定 JSON key 后缀,`t(key, count=n)` 自动选:

```json
// en.json — 区分单复数
"chain.step_count.one": "{count} step",
"chain.step_count.other": "{count} steps"
// zh.json — 中文无复数,直接用基础 key
"chain.step_count": "{count} 步"
```

`t()` 签名扩展为 `def t(key: str, count: int | None = None, **kwargs) -> str`:

- `count is not None` 时触发复数查找,且 `count` 自动注入 `kwargs`(供 `"{count}"` 占位)
- `count is None` 时行为与现状完全一致
- 查找顺序:`{key}.one`/`{key}.other`(count==1 选 one,否则 other)→ `{key}` → zh 回退 → key 本身

**后缀冲突检查**:现有 778 key 无 `.one`/`.other` 结尾,已验证安全。

### 4.2 key 校验工具链

#### 4.2.1 核心模块 `src/utils/i18n_lint.py`

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class LintFinding:
    severity: str       # "missing" | "mismatch" | "redundant" | "dynamic"
    key: str
    detail: str
    location: str | None  # "file:line"(动态 key 用)

@dataclass(frozen=True)
class LintReport:
    missing: list[LintFinding]     # 代码用了但 json 没有(阻断)
    mismatch: list[LintFinding]    # zh/en key 不对齐(阻断)
    redundant: list[LintFinding]   # json 有但代码没用(警告)
    dynamic: list[LintFinding]     # 动态 key 调用点(人工复核,警告)

    @property
    def has_errors(self) -> bool:  # missing/mismatch 非空 → True
        return bool(self.missing or self.mismatch)

def lint_i18n(src_root: Path, translations_dir: Path) -> LintReport: ...
```

#### 4.2.2 AST 扫描策略(`ast` 模块,非正则)

- **import 跟踪**:逐文件解析 import,建立"本地名 → 是否 i18n"映射,支持:
  - `from src.utils.i18n import t`
  - `from src.utils.i18n import t as tr`(别名)
  - `from src.utils import i18n` → `i18n.t(...)`
- **目标调用**:第一参数为 `t(...)` / `i18n.t(...)`,以及 `schedule_validation(key, ctx)` / `has_key(key)`(它们也引用 key)
- **静态 key**:第一参数是 `ast.Constant(str)` → 直接收集
- **动态 key**(关键正确性机制):第一参数是 f-string 如 `t(f"action_type.{step_type}")` → 提取静态前缀 `action_type.`。该前缀下所有 json key(如 `action_type.click_image`)视为"已用",**不计入 redundant**;调用点本身列入 `dynamic` 供复核

#### 4.2.3 四类对比

| 类别 | 判定 | 严重度 |
|------|------|--------|
| missing | `used_static_keys − zh_keys` | 🔴 阻断 |
| mismatch | `zh_keys ^ en_keys`(对称差) | 🔴 阻断 |
| redundant | `zh_keys − used_static − 动态前缀覆盖` | 🟡 警告 |
| dynamic | 第一参数非常量的调用点 | 🟡 警告(列 file:line) |

#### 4.2.4 CLI `scripts/lint_i18n_keys.py`

风格对齐已有 `scripts/lint_hardcoded_ui.py`。

```bash
python scripts/lint_i18n_keys.py              # 人类可读报告
python scripts/lint_i18n_keys.py --json       # 机器可读(CI 解析)
python scripts/lint_i18n_keys.py --strict     # redundant/dynamic 也算错
```
退出码:`has_errors` 为真,或 `--strict` 下有警告 → 非 0。

#### 4.2.5 pytest gate `tests/unit/utils/test_i18n_keys.py`

```python
def test_no_missing_keys():
    report = lint_i18n(SRC_ROOT, TRANSLATIONS_DIR)
    assert not report.missing, f"缺失 key: {[f.key for f in report.missing]}"

def test_no_mismatched_keys():
    report = lint_i18n(SRC_ROOT, TRANSLATIONS_DIR)
    assert not report.mismatch, f"zh/en 不对齐: {[f.key for f in report.mismatch]}"
```
missing/mismatch 阻断;redundant/dynamic 仅信息性(非阻断),避免 CI 因合理动态 key 失败。

---

## 5. Phase 2 详细设计:补齐 166 处

### 5.1 命名规范

| 来源 | 命名空间 | 示例 | 备注 |
|------|----------|------|------|
| logger | `<module>.log.<verb>` | `scheduler.log.state_saved` | 沿用现有惯例(已有 `scheduler.log.*`/`vision.log.*`) |
| 异常 | `<module>.exc.<verb>` | `serialization.exc.missing_field` | 新命名空间(现有 `error_config.*` 是 UI 错误配置,不冲突) |

新增 key 按字母序插入,保持 json 排序风格;占位符用语义化参数名(`target`/`count`/`error`,非 `arg0`)。

### 5.2 logger 格式协调(关键技术点)

现有用 logger 的 %-style(惰性求值):
```python
logger.info("从 %s 加载了 %d 个调度", target, count)
```
转换为 i18n 的 `{}` 占位符,**变量填入 `t()`,logger 收到完整字符串**:
```python
logger.info(t("scheduler.log.loaded", target=target, count=count))
# zh: "从 {target} 加载了 {count} 个调度"
# en: "Loaded {count} schedule(s) from {target}"
```

**权衡**:丧失 logger 惰性求值(debug 级关闭时仍 `t()` 求值)。但 `t()` 是内存 dict 查找 + 一次 `str.format`,开销极小,项目规模下可接受。热路径 debug 日志若 profiling 显示瓶颈,可单独加 `if logger.isEnabledFor(logging.DEBUG)` 守卫,但不作为默认。

### 5.3 异常 i18n(安全)

```python
raise ValueError(t("serialization.exc.missing_field", field="action_type"))
# zh: "缺少必需字段 '{field}'"   en: "Missing required field '{field}'"
```
**安全回退**:`t()` 在未初始化时自动 `init("zh")`,异常在早期/导入期抛出也不会崩。英文环境下 traceback 变英文(预期行为,用户已确认"全部 i18n")。

### 5.4 批量替换工作流

1. 用 tokenize 扫描生成 166 处精确清单(`file:line` + 当前中文字符串 + 上下文)
2. **按模块分批**(config → schedule → engine → vision → plugins → panel/controllers → 其余),每批:
   - 生成 key + zh/en 翻译 → 替换调用点
   - 跑 `lint_i18n_keys.py` 确认该模块 missing=0
   - 独立 commit(`feat(i18n): internationalize <module> logs/exceptions`)
3. 全部完成后:lint 全量 missing=0 + zh/en 对齐 + 完整测试套件

### 5.5 回归保障

- **硬编码中文归零**:补齐后 tokenize 复扫,字符串字面量中的中文(logger/异常类)→ 0(注释/docstring 不动)
- **翻译零缺失**:pytest gate `test_no_missing_keys` / `test_no_mismatched_keys` 通过
- **行为不变**:logger 输出语义等价(仅语言切换),异常类型/抛出点不变

---

## 6. 测试策略

### 6.1 测试矩阵(目标覆盖率 80%+,核心模块近 100%)

| 能力 | 关键测试用例 |
|------|------|
| format 修复 | `KeyError`/`IndexError`/`ValueError` 各自安全降级 + warning 记录;成功路径回归不变 |
| 可用语言列表 | 返回排序后语言码;忽略非 json 文件 |
| locale 检测 | `zh*`/`en*`/未知 分别映射;检测失败回退 `zh`(monkeypatch locale) |
| 复数 | count=1→`.one`、count=n→`.other`、中文回退基础 key、无复数 key 回退、无 count 参数回归 |
| lint 扫描 | 静态 key 收集、动态前缀提取、import 别名跟踪、`schedule_validation`/`has_key` 收集 |
| lint 对比 | missing/mismatch/redundant 检测;redundant 被动态前缀豁免 |
| key gate | 真实 src+translations 下 `test_no_missing_keys` / `test_no_mismatched_keys` 通过 |

### 6.2 TDD 工作流(CLAUDE.md 强制 + superpowers:tdd)

- **Phase 1(框架/lint)严格 TDD**:每项能力先写失败测试(RED)→ 最小实现(GREEN)→ 重构(IMPROVE)
- **Phase 2(补齐)机械替换**:lint gate 作"集成测试"兜底,每批替换后 `missing=0` 才提交

---

## 7. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| AST 误判动态 key | lint 漏报/误报 | dynamic 列 file:line 人工复核;前缀机制覆盖枚举式(`action_type.*` 等) |
| logger 丧失惰性求值 | 微小性能损耗 | 开销极小可接受;热路径可加 `isEnabledFor` 守卫 |
| 异常导入期抛出 | i18n 未初始化 | `t()` 自动 `init("zh")` 回退,已安全 |
| 复数后缀 `.one`/`.other` 冲突 | 查找异常 | 现有 778 key 无此结尾,已验证安全 |
| en 翻译质量 | 英文不准确 | 保持技术英语风格;提交时附 en.json diff 供复核 |
| 大量替换引入行为偏差 | 行为变化 | 分批 + lint gate + 全量测试套件 |

---

## 8. 向后兼容(零破坏)

- i18n.py 改动全部向后兼容:`count` 为新增可选参数,新增函数,format 修复属 bug fix
- 现有 778 key 与所有 `t()` 调用零影响
- settings.json 无破坏性改动(locale 检测仅在未配置 `language` 时生效)
- ~166 key 纯增量

---

## 9. 实施顺序

```
Phase 1A: i18n.py format 修复 + 测试(先解决 bug)
Phase 1B: 可用语言列表 + locale 检测 + 复数 + 测试(严格 TDD)
Phase 1C: i18n_lint.py + CLI + 单测(严格 TDD)
Phase 1D: pytest gate 接入(此时 778 key 对齐,gate 应通过)
Phase 2A–2N: 按模块分批补齐(config→schedule→engine→vision→plugins→panel→其余)
收尾: 全量测试 + tokenize 复扫确认硬编码中文归零
```

---

## 10. 验收标准

- [ ] i18n.py 4 项能力实现 + 单测通过(format/locale/语言列表/复数)
- [ ] i18n_lint.py 实现 + 单测通过(扫描/对比/动态前缀)
- [ ] `scripts/lint_i18n_keys.py` CLI 可用(`--json` / `--strict`)
- [ ] pytest gate 通过(`missing=0`, `mismatch=0`)
- [ ] 166 处硬编码中文全部补齐(zh/en)
- [ ] tokenize 复扫:字符串字面量中文(logger/异常类)归零
- [ ] 完整测试套件通过
- [ ] 现有 778 key 与所有 `t()` 调用行为不变(回归)
- [ ] 核心模块(i18n.py / i18n_lint.py)覆盖率 ≥ 80%
