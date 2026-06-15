"""i18n key gate — 真实 src + translations 下零缺失、零不对齐。

missing/mismatch 阻断(防腐化);redundant/dynamic 不阻断(信息性)。
"""
from pathlib import Path

from src.utils.i18n_lint import lint_i18n

_SRC = Path("src")
_TRANS = Path("src/utils/translations")


def test_no_missing_keys() -> None:
    report = lint_i18n(_SRC, _TRANS)
    assert not report.missing, \
        "缺失 key(代码用但 json 无): " + ", ".join(f.key for f in report.missing)


def test_no_mismatched_keys() -> None:
    report = lint_i18n(_SRC, _TRANS)
    assert not report.mismatch, \
        "zh/en 不对齐: " + ", ".join(f.key for f in report.mismatch)
