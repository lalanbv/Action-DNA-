"""硬编码色彩/尺寸 lint 脚本测试（Phase 2 §5.3）。

规格要求：新增硬编码色彩/尺寸被拦截；已存在的列出待清理清单、不阻塞（退出 0）。
本测试验证 lint 逻辑能正确识别违规样本、对干净样本不报。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest  # noqa: F401  # 供 pytest 发现（test_ 函数标记等）

_LINT_PATH = Path("scripts/lint_hardcoded_ui.py")


def _load_lint_module():
    """动态加载 lint 脚本（避免在包 import 层面耦合）。"""
    spec = importlib.util.spec_from_file_location(
        "lint_hardcoded_ui", _LINT_PATH
    )
    assert spec is not None and spec.loader is not None, "lint 脚本不存在"
    module = importlib.util.module_from_spec(spec)
    # 注册到 sys.modules，供 dataclass 解析 __module__（Python 3.14 要求）
    sys.modules["lint_hardcoded_ui"] = module
    spec.loader.exec_module(module)
    return module


def test_lint_detects_hardcoded_hex_color(tmp_path):
    """含 #rrggbb 硬编码色彩的样本被检出。"""
    lint = _load_lint_module()
    sample = tmp_path / "sample.py"
    sample.write_text(
        'bg = "#1e1e1e"\n'   # 硬编码色彩
        'fg = "#fff"\n',     # 短形式硬编码色彩
        encoding="utf-8",
    )
    findings = lint.scan_file(sample)
    colors = [f for f in findings if f.kind == "color"]
    assert len(colors) >= 2, f"应检出至少 2 个硬编码色彩，实际 {len(colors)}"


def test_lint_detects_hardcoded_dimension(tmp_path):
    """裸数字尺寸魔法值被检出（width=/height=/padx= 后跟数字字面量）。"""
    lint = _load_lint_module()
    sample = tmp_path / "sample.py"
    sample.write_text(
        'btn.config(width=80)\n'
        'frame.configure(height=24)\n',
        encoding="utf-8",
    )
    findings = lint.scan_file(sample)
    dims = [f for f in findings if f.kind == "dimension"]
    assert len(dims) >= 2, f"应检出至少 2 个硬编码尺寸，实际 {len(dims)}"


def test_lint_clean_sample_no_findings(tmp_path):
    """干净样本（仅用 tokens / 变量）无检出。"""
    lint = _load_lint_module()
    sample = tmp_path / "sample.py"
    sample.write_text(
        'bg = th.bg_surface\n'           # token 引用
        'pad = th.pad_md\n'              # token 引用
        'x = some_var\n',                # 变量
        encoding="utf-8",
    )
    findings = lint.scan_file(sample)
    assert findings == [], f"干净样本不应有检出，实际 {findings}"


def test_lint_finding_has_location_and_value(tmp_path):
    """每个 finding 携带文件路径、行号、违规值（便于生成清理清单）。"""
    lint = _load_lint_module()
    sample = tmp_path / "sample.py"
    sample.write_text('bg = "#1e1e1e"\n', encoding="utf-8")
    findings = lint.scan_file(sample)
    assert findings
    f = findings[0]
    assert f.file == str(sample)
    assert f.line == 1
    assert "#1e1e1e" in f.value
