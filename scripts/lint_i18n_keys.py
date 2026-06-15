#!/usr/bin/env python3
"""i18n key 校验 CLI — AST 扫描 t() 对比翻译 json。

用法::

    python scripts/lint_i18n_keys.py              # 人类可读报告
    python scripts/lint_i18n_keys.py --json       # 机器可读(CI 解析)
    python scripts/lint_i18n_keys.py --strict     # redundant/dynamic 也算错

退出码:has_errors(missing/mismatch)为真 → 1;--strict 下有警告 → 1;否则 0。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 确保项目根在 sys.path(脚本直接调用时 sys.path[0] 是 scripts/,需回溯两级到根)。
# 用最弱副作用方式插入:仅当根不在 path 时追加。
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.utils.i18n_lint import LintReport, lint_i18n  # noqa: E402  (sys.path 修正后才能 import)

# 四类严重性,顺序即输出顺序(missing/mismatch 阻断级在前)
_SEVERITIES: tuple[str, ...] = ("missing", "mismatch", "redundant", "dynamic")


def _format_text(report: LintReport) -> str:
    """人类可读报告:头部标识(OK / OK(警告) / FAIL)+ 各类条目明细。"""
    lines: list[str] = []
    if report.has_errors:
        lines.append("FAIL(有阻断级问题)")
    elif report.redundant or report.dynamic:
        lines.append("OK(仅有非阻断警告)")
    else:
        lines.append("OK")
    for sev in _SEVERITIES:
        items = getattr(report, sev)
        if not items:
            continue
        lines.append(f"\n## {sev} ({len(items)})")
        for f in items:
            loc = f"  @ {f.location}" if f.location else ""
            lines.append(f"  - {f.key}: {f.detail}{loc}")
    return "\n".join(lines)


def _format_json(report: LintReport) -> str:
    """机器可读 JSON:四类键,每类为 finding 字典列表。"""
    data = {sev: [{"key": f.key, "detail": f.detail, "location": f.location}
                  for f in getattr(report, sev)]
            for sev in _SEVERITIES}
    return json.dumps(data, ensure_ascii=False, indent=2)


def main(argv: list[str] | None = None) -> int:
    """CLI 入口:解析参数 → 执行 lint_i18n → 格式化输出 → 返回退出码。

    退出码规则:
    - has_errors(missing/mismatch) → 1(阻断级,必须修)。
    - --strict 且有 redundant/dynamic → 1(警告升级为错)。
    - 否则 → 0。
    """
    parser = argparse.ArgumentParser(description="i18n key 校验(AST 扫描 + 翻译对比)")
    parser.add_argument("--src", default="src", help="源码根目录(默认 src)")
    parser.add_argument("--translations", default="src/utils/translations",
                        help="翻译目录(默认 src/utils/translations)")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--strict", action="store_true",
                        help="redundant/dynamic 也算错(非 0 退出)")
    args = parser.parse_args(argv)

    src_root = Path(args.src)
    translations_dir = Path(args.translations)
    if not src_root.exists():
        print(f"[lint_i18n] 源码根目录不存在:{src_root}", file=sys.stderr)
        return 0
    if not translations_dir.exists():
        print(f"[lint_i18n] 翻译目录不存在:{translations_dir}", file=sys.stderr)
        return 0

    report = lint_i18n(src_root, translations_dir)
    print(_format_json(report) if args.json else _format_text(report))

    if report.has_errors:
        return 1
    if args.strict and (report.redundant or report.dynamic):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
