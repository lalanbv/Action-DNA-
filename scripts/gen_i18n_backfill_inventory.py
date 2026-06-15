#!/usr/bin/env python3
"""扫描源码硬编码中文(logger/异常),生成 i18n 补齐清单(markdown)。

供 Phase 2 补齐工作提供精确清单(file:line + 字符串 + 分类)。
排除:注释、docstring、translations/、i18n.py。

用法::

    python scripts/gen_i18n_backfill_inventory.py > docs/superpowers/plans/i18n-backfill-inventory.md
"""

from __future__ import annotations

import io
import re
import tokenize
from pathlib import Path

_CN = re.compile(r"[一-鿿]")
_SKIP = {"translations", "__pycache__"}
_LOG_METHODS = (".info", ".warning", ".error", ".debug", ".exception", ".critical")


def scan(root: Path) -> list[tuple[str, int, str, str]]:
    """返回 [(file, line, kind, source_text)],kind ∈ {'logger','exception'}。

    kind='logger': 含 logger 且带 .info/.warning/.error/.debug/.exception/.critical 的行。
    kind='exception': 含 raise 或 XxxError(/Exception) 调用的行。
    排除 docstring(行含 \"\"\" 或 ''')、translations/、__pycache__/、i18n.py。
    """
    items: list[tuple[str, int, str, str]] = []
    for py in sorted(root.rglob("*.py")):
        if any(part in _SKIP for part in py.parts) or py.name == "i18n.py":
            continue
        src = py.read_text(encoding="utf-8")
        lines = src.splitlines()
        try:
            toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
        except tokenize.TokenError:
            continue
        for tok in toks:
            if tok.type != tokenize.STRING or not _CN.search(tok.string):
                continue
            srow = tok.start[0]
            line = lines[srow - 1] if srow - 1 < len(lines) else ""
            if '"""' in line or "'''" in line:  # 跳过 docstring
                continue
            stripped = line.strip()
            if "logger" in line and any(m in line for m in _LOG_METHODS):
                items.append((str(py), srow, "logger", stripped))
            elif "raise " in line or re.search(r"\b\w+(Error|Exception)\(", line):
                items.append((str(py), srow, "exception", stripped))
    return items


def main() -> None:
    items = scan(Path("src"))
    by_file: dict[str, list[tuple[int, str, str]]] = {}
    for f, lineno, kind, text in items:
        by_file.setdefault(f, []).append((lineno, kind, text))
    print(f"# i18n 补齐清单({len(items)} 处)\n")
    for f in sorted(by_file):
        rows = by_file[f]
        log_n = sum(1 for _, k, _ in rows if k == "logger")
        exc_n = sum(1 for _, k, _ in rows if k == "exception")
        print(f"## `{f}` (logger {log_n} + 异常 {exc_n})\n")
        for lineno, kind, text in sorted(rows):
            print(f"- L{lineno} [{kind}] `{text}`")
        print()


if __name__ == "__main__":
    main()
