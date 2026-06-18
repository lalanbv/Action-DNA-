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

from src.core.step_types import WaitRandomStep, WaitStep, field_value_i18n_key
from src.panel.components.step_key_fields import key_fields_for
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


def build_block_insert_order(n: int, selected: list[int], target: int) -> list[int]:
    """选中块整体 insert 到原序 ``target`` 行之前；返回原索引的新排列。

    拖拽语义：``selected`` 块（保持相对顺序）整体移到原序 ``target`` 行处，
    ``target`` 及之后的非选中项顺延。单选时等价于把该项插到 target 前。
    ``target == n`` 表示落到所有行下方 → 追加末尾。target 越界或无选中返回原序。
    """
    sel = sorted(set(selected))
    if not sel or not (0 <= target <= n):
        return list(range(n))
    sel_set = set(sel)
    result: list[int] = []
    inserted = False
    for i in range(n):
        if i == target and not inserted:
            result.extend(sel)
            inserted = True
        if i not in sel_set:
            result.append(i)
    if not inserted:  # target == n：块追加到末尾
        result.extend(sel)
    return result


def drop_insert_target(target_idx: int | None, click_below_center: bool, n: int) -> int:
    """由拖拽落点计算 insert target 下标（供 ``build_block_insert_order``）。

    ``target_idx=None`` → 落到所有行下方空区 → 追加末尾（``n``）；
    否则光标在目标行下半部 → ``idx+1``，上半部 → ``idx``。Qt 原生拖拽指示线语义。
    """
    if target_idx is None:
        return n
    return target_idx + 1 if click_below_center else target_idx


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


def build_edge_order(n: int, selected: list[int], to_top: bool) -> list[int]:
    """选中项整体移到序列顶部(``to_top=True``)或底部，保持相对顺序。

    返回原索引的新排列。与 ``build_batch_move_order`` 用单函数处理双向的风格对齐。
    """
    order = list(range(n))
    if to_top:
        target = 0
        rows = sorted(set(selected))
    else:
        target = n - 1
        rows = sorted(set(selected), reverse=True)
    for src in rows:
        if 0 <= src < n:
            order.pop(order.index(src))
            order.insert(target, src)
            target += 1 if to_top else -1
    return order


def build_top_order(n: int, selected: list[int]) -> list[int]:
    """选中项整体移到顶部（``build_edge_order`` 薄包装，向后兼容）。"""
    return build_edge_order(n, selected, to_top=True)


def build_bottom_order(n: int, selected: list[int]) -> list[int]:
    """选中项整体移到底部（``build_edge_order`` 薄包装，向后兼容）。"""
    return build_edge_order(n, selected, to_top=False)


# 路径字段后缀：按字段名判断是否取 basename，而非 sniff 值内容
# （避免 combo_keys='Shift+a/Shift+b' 等含斜杠的非路径字符串被截断）。
_PATH_FIELD_SUFFIXES = ("_path",)

def format_field_value(step, field_name: str) -> str:
    """格式化单个字段值为人类可读字符串。

    优先级：语义枚举/模式→i18n（查 ``step_types._FIELD_VALUE_I18N``，与各 ``describe()``
    同源、单一事实源）；bool→✓/✗；路径字段（字段名以 ``_path`` 结尾）→basename；
    空串→未设置；list/tuple→「N 项」；None→``--``；其余 Enum→``.name``、普通值→``str``。
    """
    value = getattr(step, field_name, None)
    if value is None:
        return "--"
    if isinstance(value, Enum):
        key = field_value_i18n_key(field_name, value.name)
        return t(key) if key else value.name
    if isinstance(value, bool):
        return "✓" if value else "✗"
    if isinstance(value, str):
        if value == "":
            return t("common.not_set")
        key = field_value_i18n_key(field_name, value)
        if key:
            return t(key)
        if field_name.endswith(_PATH_FIELD_SUFFIXES):
            return os.path.basename(value)
        return value
    if isinstance(value, (list, tuple)):
        return t("chain.detail.n_items", count=len(value)) if value else "--"
    return str(value)


def iter_all_fields(step) -> Iterator[tuple[str, str]]:
    """遍历 dataclass 全部字段（ClassVar 自动排除），yield (字段名, 格式化值)。"""
    for f in dataclasses.fields(step):
        yield (f.name, format_field_value(step, f.name))


def wait_text(step) -> str:
    """步骤「等待」列文案（Qt/tk 共用，统一 :g 格式去尾零；非等待类返回空串）。"""
    if isinstance(step, WaitStep):
        return f"{step.wait_seconds:g}s"
    if isinstance(step, WaitRandomStep):
        return f"{step.wait_min:g}~{step.wait_max:g}s"
    return ""


def key_field_rows(step) -> list[tuple[str, str]]:
    """关键参数表的 (i18n 标签, 格式化值) 行（Qt/tk 共用，框架无关）。"""
    return [
        (t(i18n_key), format_field_value(step, fname))
        for fname, i18n_key in key_fields_for(step)
    ]
