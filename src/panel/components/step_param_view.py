"""步骤参数视图共用工具：重排 order 构造 + 字段值格式化。Qt/tk 共用。

- ``build_move_order`` / ``build_batch_move_order``：构造 insert 语义的原索引排列，
  直接喂给 ``ChainModel.reorder_steps``。供详情面板「移动到序号」、列表拖拽、
  置顶/置底、多选批量移动统一使用。
- ``format_field_value`` / ``iter_all_fields``：详情面板「全部字段」表的取值与渲染。
"""

from __future__ import annotations

import dataclasses
import os
from collections.abc import Iterator
from enum import Enum

from src.utils.i18n import t


def build_move_order(n: int, src: int, dst: int) -> list[int]:
    """把原索引 ``src`` 取出 insert 到 ``dst``，其余顺延；返回原索引的新排列。

    ``new_order[i]`` = 新序列位置 ``i`` 应承载的原步骤索引（与
    ``ChainModel.reorder_steps`` 的入参语义一致）。非法或 src==dst 时原序返回。
    """
    if not (0 <= src < n and 0 <= dst < n) or src == dst:
        return list(range(n))
    order = list(range(n))
    moved = order.pop(src)
    order.insert(dst, moved)
    return order


def build_batch_move_order(n: int, selected: list[int], delta: int) -> list[int]:
    """选中索引集合整体上移(``delta<0``)/下移(``delta>0``)一格。

    按位置扫描：选中元素与其紧邻的非选中邻居交换，保证连续块整体平移
    （而非逐个错位）。已在边界的选中项不动。
    """
    sel = set(selected)
    order = list(range(n))
    if delta < 0:
        for pos in range(1, n):
            if order[pos] in sel and order[pos - 1] not in sel:
                order[pos], order[pos - 1] = order[pos - 1], order[pos]
    elif delta > 0:
        for pos in range(n - 2, -1, -1):
            if order[pos] in sel and order[pos + 1] not in sel:
                order[pos], order[pos + 1] = order[pos + 1], order[pos]
    return order


def build_top_order(n: int, selected: list[int]) -> list[int]:
    """选中项整体移到序列顶部，保持相对顺序；返回原索引的新排列。"""
    order = list(range(n))
    target = 0
    for src in sorted(set(selected)):
        if 0 <= src < n:
            moved = order.pop(order.index(src))
            order.insert(target, moved)
            target += 1
    return order


def build_bottom_order(n: int, selected: list[int]) -> list[int]:
    """选中项整体移到序列底部，保持相对顺序；返回原索引的新排列。"""
    order = list(range(n))
    target = n - 1
    for src in sorted(set(selected), reverse=True):
        if 0 <= src < n:
            moved = order.pop(order.index(src))
            order.insert(target, moved)
            target -= 1
    return order


def format_field_value(step, field_name: str) -> str:
    """格式化单个字段值为人类可读字符串。

    枚举→``.name``；路径(含 / 或 \\)→basename；空串→未设置；
    list/tuple→「N 项」；None→``--``；bool→✓/✗；其余→``str``。
    """
    value = getattr(step, field_name, None)
    if value is None:
        return "--"
    if isinstance(value, Enum):
        return value.name
    if isinstance(value, bool):
        return "✓" if value else "✗"
    if isinstance(value, str):
        if value == "":
            return t("common.not_set")
        if "/" in value or "\\" in value:
            return os.path.basename(value)
        return value
    if isinstance(value, (list, tuple)):
        return t("chain.detail.n_items", count=len(value)) if value else "--"
    return str(value)


def iter_all_fields(step) -> Iterator[tuple[str, str]]:
    """遍历 dataclass 全部字段（ClassVar 自动排除），yield (字段名, 格式化值)。"""
    for f in dataclasses.fields(step):
        yield (f.name, format_field_value(step, f.name))
