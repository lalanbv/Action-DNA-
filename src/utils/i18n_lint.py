"""i18n key 校验 — AST 扫描 t() 调用,对比翻译 json,报告缺失/不对齐/冗余/动态。

供 ``scripts/lint_i18n_keys.py``(CLI)与 ``tests/unit/utils/test_i18n_keys.py``(pytest gate)共用。

本模块只负责「数据结构 + collect_used_keys(AST 静态 key + 动态前缀提取)」。
对比逻辑(lint_i18n 对比翻译 json)见后续 Task。
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

# i18n 函数名(跟踪 import 后的本地绑定)
_I18N_FUNCS = frozenset({"t", "schedule_validation", "has_key"})


@dataclass(frozen=True)
class LintFinding:
    """一条校验记录。"""

    severity: str  # "missing" | "mismatch" | "redundant" | "dynamic"
    key: str
    detail: str
    location: str | None = None  # "file:line"(dynamic 用)


@dataclass(frozen=True)
class LintReport:
    """校验报告。has_errors 为真表示有阻断级问题(missing/mismatch)。"""

    missing: list[LintFinding] = field(default_factory=list)
    mismatch: list[LintFinding] = field(default_factory=list)
    redundant: list[LintFinding] = field(default_factory=list)
    dynamic: list[LintFinding] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        """存在阻断级问题(missing 或 mismatch)。"""
        return bool(self.missing or self.mismatch)


@dataclass
class _FileImports:
    """文件级 i18n 调用名跟踪(由 _parse_imports 填充)。

    - local_names: ``from src.utils.i18n import t``(或 ``as tr``)绑定的本地名集合。
    - module_alias: ``from src.utils import i18n``(或 ``import ... i18n``)绑定的模块别名。
    """

    local_names: set[str] = field(default_factory=set)
    module_alias: str | None = None


def _parse_imports(tree: ast.AST) -> _FileImports:
    """解析文件 import,识别 i18n 函数的本地绑定。

    支持三种写法:
    - ``from src.utils.i18n import t`` → local_names={"t"}
    - ``from src.utils.i18n import t as tr`` → local_names={"tr"}
    - ``from src.utils import i18n`` → module_alias="i18n"
      (``from src.utils import i18n as i`` → module_alias="i")
    - ``import src.utils.i18n`` → module_alias="src.utils.i18n"(name 以 i18n 结尾)
    """
    imp = _FileImports()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in _I18N_FUNCS:
                    imp.local_names.add(alias.asname or alias.name)
                elif alias.name == "i18n":
                    imp.module_alias = alias.asname or alias.name
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.endswith("i18n"):
                    imp.module_alias = alias.asname or alias.name
    return imp


def _is_i18n_call(call: ast.Call, imp: _FileImports) -> str | None:
    """若 call 是 i18n 函数调用,返回函数名;否则 None。

    覆盖三种识别路径:
    - 直接名 ``t(...)`` 且 ``t`` 已 import 到本地 → 命中 local_names。
    - 领域特有名(如 ``schedule_validation(...)``、``has_key(...)``)→ 即使未显式
      import 也命中(这类名称在项目中专属 i18n,不会与第三方冲突)。
    - 属性访问 ``i18n.t(...)`` → 校验 func.value.id == imp.module_alias 且 attr 在白名单。
    """
    func = call.func
    if isinstance(func, ast.Name):
        if func.id in imp.local_names:
            return func.id
        # 领域特有名(schedule_validation / has_key)即便未显式 import 也视作 i18n 调用;
        # ``t`` 因名称过于通用,必须经 import 跟踪后(进入 local_names)才认。
        if func.id in _I18N_FUNCS and func.id != "t":
            return func.id
        return None
    if (isinstance(func, ast.Attribute) and func.attr in _I18N_FUNCS
            and isinstance(func.value, ast.Name)
            and imp.module_alias is not None
            and func.value.id == imp.module_alias):
        return func.attr
    return None


def _extract_key_arg(arg: ast.AST) -> tuple[str | None, str | None]:
    """从调用第一参数提取 (静态 key) 或 (动态前缀)。

    返回 ``(static, prefix)``:
    - ``(str, None)``: 字符串字面量,精确 key。
    - ``(None, str)``: f-string,提取首变量前的静态前缀(如 ``f"prefix.{x}"`` → ``"prefix."``)。
    - ``(None, None)``: 无法解析(非字符串、变量、空 f-string)。
    """
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value, None
    if isinstance(arg, ast.JoinedStr):  # f-string:提取首变量前的静态前缀
        prefix_parts: list[str] = []
        for val in arg.values:
            if isinstance(val, ast.Constant) and isinstance(val.value, str):
                prefix_parts.append(val.value)
            else:
                break
        if prefix_parts:
            return None, "".join(prefix_parts)
    return None, None


def collect_used_keys(src_root: Path) -> tuple[set[str], set[str], list[LintFinding]]:
    """AST 扫描 src_root,返回 (静态 keys, 动态前缀, dynamic findings)。

    遍历 ``src_root`` 下所有 ``.py`` 文件(排除 ``translations/`` 与 ``__pycache__/``),
    解析 import 跟踪 i18n 调用名,逐 Call 节点提取第一参数。

    Returns:
        三元组 ``(used, prefixes, dynamic)``:
        - ``used``: 代码中出现的精确 key 集合(来自字符串字面量)。
        - ``prefixes``: 动态 key 的静态前缀集合(来自 f-string 首段)。
        - ``dynamic``: 每个动态/不可解析调用一条 LintFinding(severity="dynamic")。
    """
    used: set[str] = set()
    prefixes: set[str] = set()
    dynamic: list[LintFinding] = []
    for py in sorted(src_root.rglob("*.py")):
        if any(part in {"translations", "__pycache__"} for part in py.parts):
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (SyntaxError, OSError):
            continue
        imp = _parse_imports(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fname = _is_i18n_call(node, imp)
            if fname is None or not node.args:
                continue
            static, prefix = _extract_key_arg(node.args[0])
            if static is not None:
                used.add(static)
            elif prefix is not None:
                prefixes.add(prefix)
                dynamic.append(LintFinding(
                    "dynamic", prefix, f"动态 key 前缀(调用 {fname})", f"{py}:{node.lineno}"))
            else:
                dynamic.append(LintFinding(
                    "dynamic", "", f"无法解析的 {fname}() 参数", f"{py}:{node.lineno}"))
    return used, prefixes, dynamic
