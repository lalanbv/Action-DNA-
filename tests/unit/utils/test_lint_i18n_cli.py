"""lint_i18n_keys CLI 的 main() 测试。"""

import json

from scripts.lint_i18n_keys import main


def test_main_clean_returns_zero(capsys) -> None:
    """真实 src/translations 干净(missing=0/mismatch=0)→ 返回 0。"""
    rc = main([])
    out = capsys.readouterr().out
    assert rc == 0
    assert "OK" in out  # OK 或 OK(仅有警告)


def test_main_json_valid_output(capsys) -> None:
    """--json 输出合法 JSON,含四类键。"""
    rc = main(["--json"])
    data = json.loads(capsys.readouterr().out)
    assert rc == 0
    for key in ("missing", "mismatch", "redundant", "dynamic"):
        assert key in data


def test_main_strict_mode(capsys) -> None:
    """--strict 模式下,有 redundant/dynamic 时返回 1(真实 src 有 redundant)→ 非 0。"""
    rc = main(["--strict"])
    # 真实 src 有 redundant(动态误报)+ dynamic → strict 下返回 1
    assert rc == 1
