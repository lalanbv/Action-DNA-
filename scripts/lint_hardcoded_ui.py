#!/usr/bin/env python3
"""硬编码色彩/尺寸 lint（Phase 2，规格 §5.3）。

扫描 ``src/panel/**``（排除 token 真相源 ``canvas/theme/`` 与 ``translations/``），
检出硬编码 ``#hex`` 色彩与裸数字尺寸魔法值（``width=/height=/padx=/pady=`` 后跟
数字字面量），输出待清理清单。

设计要点（规格 §5.3）：
- **不阻塞现有**：退出码恒为 0；已存在的违规仅列入清单，留作后续治理。
- **可接入 CI**：``--check-new`` 模式下，若清单条数超过基线（``--baseline N``）则
  非零退出，供增量门禁用（本计划不接入 CI，留作后续）。

用法::

    python scripts/lint_hardcoded_ui.py                 # 扫描并打印清单（退出 0）
    python scripts/lint_hardcoded_ui.py --root src/panel
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# 硬编码色彩：#rgb / #rrggbb / #rrggbbaa（不含已转义的）
_COLOR_RE = re.compile(r'"(#[0-9a-fA-F]{3,8})"|\'(#[0-9a-fA-F]{3,8})\'|=(#[0-9a-fA-F]{3,8})')

# 裸数字尺寸魔法值：width=/height=/padx=/pady= 后跟数字字面量（非变量、非 token）
_DIM_RE = re.compile(
    r'\b(width|height|padx|pady|minimum|maximum)\s*=\s*(\d+(?:\.\d+)?)\b'
)

# 默认扫描根 + 排除目录（token 真相源 / 翻译 / 缓存）
DEFAULT_ROOT = "src/panel"
EXCLUDE_DIRS: tuple[str, ...] = (
    "canvas/theme",   # token 单一真相源
    "translations",   # 翻译文件
    "__pycache__",
)


@dataclass(frozen=True)
class Finding:
    """一条硬编码违规记录。"""

    file: str
    line: int
    kind: str   # "color" | "dimension"
    value: str  # 违规字面量（如 "#1e1e1e" / "80"）

    def as_markdown(self) -> str:
        return f"- `{self.file}:{self.line}` [{self.kind}] `{self.value}`"


def _is_excluded(path: Path, root: Path) -> bool:
    rel = path.relative_to(root).as_posix()
    return any(rel.startswith(ex) or f"/{ex}/" in f"/{rel}/" for ex in EXCLUDE_DIRS)


def scan_file(path: Path) -> list[Finding]:
    """扫描单个文件，返回违规清单。非 .py 文件或读取失败返回空。"""
    if path.suffix != ".py":
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    findings: list[Finding] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        # 色彩
        for m in _COLOR_RE.finditer(line):
            value = next(g for g in m.groups() if g)
            findings.append(Finding(str(path), lineno, "color", value))
        # 尺寸
        for m in _DIM_RE.finditer(line):
            # 跳过显然合法的边界（如 QSpinBox minimum/maximum 在某些上下文是合理的，
            # 但规格要求列出待清理清单，故全部记录由人工裁决）
            findings.append(Finding(str(path), lineno, "dimension", m.group(2)))
    return findings


def scan_tree(root: Path) -> list[Finding]:
    """递归扫描目录树（排除 token 真相源等），返回全部违规。"""
    all_findings: list[Finding] = []
    for path in sorted(root.rglob("*.py")):
        if _is_excluded(path, root):
            continue
        all_findings.extend(scan_file(path))
    return all_findings


def check_baseline(count: int, baseline: int) -> bool:
    """CI 门禁基线判定（规格 §5.3 增量门禁）。

    违规数 ``count`` 不超过基线 ``baseline`` → 通过（True）；超出 → 失败（False）。
    允许清理减少基线，禁止增量引入硬编码。
    """
    return count <= baseline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="硬编码色彩/尺寸 lint（Phase 2 §5.3）")
    parser.add_argument("--root", default=DEFAULT_ROOT, help="扫描根目录")
    parser.add_argument(
        "--format", choices=("markdown", "count"), default="markdown",
        help="输出格式（默认 markdown 清单）",
    )
    parser.add_argument(
        "--baseline", type=int, default=None,
        help="CI 门禁基线：违规数超过此值时非零退出（规格 §5.3 增量门禁）",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="CI 门禁模式：配合 --baseline，超基线返回 1，否则 0",
    )
    args = parser.parse_args(argv)

    root = Path(args.root)
    if not root.exists():
        print(f"[lint] 根目录不存在：{root}", file=sys.stderr)
        return 0  # 不阻塞

    findings = scan_tree(root)
    count = len(findings)

    # CI 门禁模式：基线判定优先，控制退出码（默认输出 count，便于日志）
    if args.check:
        if args.baseline is None:
            print("[lint] --check 需要 --baseline N", file=sys.stderr)
            return 2
        passed = check_baseline(count, args.baseline)
        status = "PASS" if passed else "FAIL"
        print(
            f"[lint] {status}: {count} 项违规，基线 {args.baseline} "
            f"（{'允许清理减少，禁止新增' if passed else '超出基线，请改用 tokens/常量'}）"
        )
        return 0 if passed else 1

    if args.format == "count":
        print(count)
        return 0

    # markdown 清单
    colors = [f for f in findings if f.kind == "color"]
    dims = [f for f in findings if f.kind == "dimension"]
    print(f"# 硬编码色彩/尺寸待清理清单（{count} 项，规格 §5.3）\n")
    print(f"## 色彩（{len(colors)}）\n")
    for f in colors:
        print(f.as_markdown())
    print(f"\n## 尺寸（{len(dims)}）\n")
    for f in dims:
        print(f.as_markdown())
    return 0  # 不阻塞现有（规格 §5.3）


if __name__ == "__main__":
    raise SystemExit(main())
