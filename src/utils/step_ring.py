"""StepRing — 高效 Treeview 增量同步，避免全量 delete+insert"""

import tkinter as tk
from tkinter import ttk

from src.core.action import ActionType
from src.core.step_types import BaseStep
from src.core.flow import FlowNode, NodeType
from src.panel.components.step_param_view import wait_text
from src.utils.i18n import t


_ACTION_TYPE_KEYS = {
    ActionType.CLICK_IMAGE: "action_type.click_image",
    ActionType.WAIT: "action_type.wait",
    ActionType.WAIT_RANDOM: "action_type.wait_random",
    ActionType.PRESS_KEY: "action_type.press_key",
    ActionType.CLICK_POS: "action_type.click_pos",
    ActionType.MOUSE_SCROLL: "action_type.scroll",
    ActionType.HOLD_KEY: "action_type.hold_key",
    ActionType.MOUSE_MOVE: "action_type.mouse_move",
    ActionType.MOUSE_DRAG: "action_type.mouse_drag",
    ActionType.KEY_COMBO: "action_type.key_combo",
    ActionType.MULTI_KEY_SEQUENCE: "action_type.multi_key",
    ActionType.IDLE_BEHAVIOR: "action_type.idle",
    ActionType.START_TIMER: "action_type.start_timer",
}

_NODE_TYPE_KEYS = {
    NodeType.START: "workflow.node.start",
    NodeType.ACTION: "workflow.node.action",
    NodeType.CONDITION: "workflow.node.condition",
    NodeType.MERGE: "workflow.node.merge",
    NodeType.LOOP: "workflow.node.loop",
    NodeType.END: "workflow.node.end",
}


def _type_label(step: BaseStep) -> str:
    return t(_ACTION_TYPE_KEYS.get(step.action_type, step.action_type.name))


def _wait_text(step: BaseStep) -> str:
    """步骤「等待」列文案（委托共用 wait_text，Qt/tk 统一 :g 格式）。"""
    return wait_text(step)


def _step_values(index: int, step: BaseStep) -> tuple:
    return (
        index + 1,
        _type_label(step),
        step.describe(),
        _wait_text(step),
        "✓" if step.enabled else "✗",
        step.comment,
    )


def _node_values(index: int, node: FlowNode) -> tuple:
    """将 FlowNode 转换为 Treeview 行数据"""
    match node.node_type:
        case NodeType.ACTION:
            if node.action:
                return (
                    index + 1,
                    _type_label(node.action),
                    node.action.describe(),
                    _wait_text(node.action),
                    "✓" if node.enabled else "✗",
                    node.comment,
                )
            return (index + 1, t("workflow.node.action"), "(空)", "-", "✓", node.comment)
        case NodeType.CONDITION:
            desc = node.describe()
            return (index + 1, t("workflow.node.condition"), desc, "-", "✓" if node.enabled else "✗", node.comment)
        case NodeType.START:
            return (index + 1, t("workflow.node.start"), "[ 开始 ]", "-", "-", "")
        case NodeType.END:
            return (index + 1, t("workflow.node.end"), "[ 结束 ]", "-", "-", "")
        case NodeType.MERGE:
            return (index + 1, t("workflow.node.merge"), f"[ 汇合: {node.comment or node.node_id} ]", "-", "✓", node.comment)
        case NodeType.LOOP:
            count_str = t("flow.node.infinite") if node.loop_count == 0 else str(node.loop_count)
            return (index + 1, t("workflow.node.loop"), f"[ 循环 ×{count_str} ]", "-", "✓" if node.enabled else "✗", node.comment)
        case _:
            return (index + 1, t(_NODE_TYPE_KEYS.get(node.node_type, "?")), node.describe(), "-", "✓", node.comment)


class StepRing:
    """循环利用 Treeview 行，仅更新变化部分。

    执行期间支持三态显示：
    - pending:  默认外观
    - running:  蓝色高亮 + ▶ 图标
    - completed: 绿色文字 + ✓ 图标
    """

    def __init__(self, tree: ttk.Treeview):
        self._tree = tree
        self._ids: list[str] = []
        self._highlight_idx: int = -1
        self._completed_indices: set[int] = set()
        self._items: list = []
        self._value_fn = None

    def _sync(self, items, value_fn) -> None:
        self._items = items
        self._value_fn = value_fn
        cur = len(self._ids)
        tgt = len(items)
        for i in range(min(cur, tgt)):
            self._tree.item(self._ids[i], values=value_fn(i, items[i]))
        for i in range(cur, tgt):
            iid = self._tree.insert("", tk.END, values=value_fn(i, items[i]))
            self._ids.append(iid)
        if tgt < cur:
            for iid in self._ids[tgt:]:
                self._tree.delete(iid)
            self._ids = self._ids[:tgt]
        if 0 <= self._highlight_idx < len(self._ids):
            self._apply_highlight(self._highlight_idx)
        else:
            self._highlight_idx = -1

    def sync_steps(self, steps: list[BaseStep]) -> None:
        """增量同步 BaseStep 列表（向后兼容）"""
        self._sync(steps, _step_values)

    def sync_nodes(self, nodes: list[FlowNode]) -> None:
        """增量同步 FlowNode 列表"""
        self._sync(nodes, _node_values)

    def sync(self, steps: list[BaseStep]) -> None:
        """sync_steps 的别名，保持向后兼容"""
        self.sync_steps(steps)

    def is_alive(self) -> bool:
        """检查底层 Treeview 是否仍然存在"""
        return bool(self._tree.winfo_exists())

    def highlight(self, index: int) -> None:
        """高亮指定步骤，并将前一步标记为已完成。

        新一轮由 executor.round_started 事件驱动 reset_execution()，
        不再依赖 index 回退检测。
        """
        if index == self._highlight_idx:
            return
        from src.panel.canvas.theme import current_theme
        th = current_theme()
        self._tree.tag_configure("running", background=th.accent_blue, foreground=th.text_on_accent)
        self._tree.tag_configure("completed", foreground=th.accent_green, background=th.bg_surface)
        # 前一步标记为已完成
        if self._highlight_idx >= 0:
            self._completed_indices.add(self._highlight_idx)
        self._apply_highlight(index)

    def clear_highlight(self) -> None:
        if self._highlight_idx >= 0 and self._highlight_idx < len(self._ids):
            self._tree.item(self._ids[self._highlight_idx], tags=())
        self._highlight_idx = -1

    def reset_execution(self) -> None:
        """清除所有执行状态（高亮 + 已完成标记），恢复原始显示"""
        self._highlight_idx = -1
        self._completed_indices.clear()
        for iid in self._ids:
            self._tree.item(iid, tags=())
        self._restore_all_values()

    def selected_index(self) -> int | None:
        sel = self._tree.selection()
        if not sel:
            return None
        try:
            return self._ids.index(sel[0])
        except ValueError:
            return None

    def select(self, index: int) -> None:
        if 0 <= index < len(self._ids):
            self._tree.selection_set(self._ids[index])

    def see(self, index: int) -> None:
        """滚动到指定行，确保可见"""
        if 0 <= index < len(self._ids):
            self._tree.see(self._ids[index])

    # ── 内部 ──────────────────────────────────────────────

    def _apply_highlight(self, index: int) -> None:
        prev = self._highlight_idx
        if prev >= 0 and prev < len(self._ids):
            self._tree.item(self._ids[prev], tags=("completed",) if prev in self._completed_indices else ())
            self._update_index_icon(prev)
        self._highlight_idx = index
        if 0 <= index < len(self._ids):
            self._tree.item(self._ids[index], tags=("running",))
            self._tree.see(self._ids[index])
            self._update_index_icon(index)

    def _update_index_icon(self, index: int) -> None:
        """更新序号列显示：▶ 运行中 / ✓ 已完成 / 数字 待执行"""
        if not (0 <= index < len(self._ids)):
            return
        if index == self._highlight_idx:
            icon = "▶"
        elif index in self._completed_indices:
            icon = "✓"
        else:
            icon = str(index + 1)
        values = list(self._tree.item(self._ids[index], "values"))
        values[0] = icon
        self._tree.item(self._ids[index], values=tuple(values))

    def _restore_all_values(self) -> None:
        """恢复所有行的原始数据（用于清除执行图标）"""
        if not self._items or not self._value_fn:
            return
        for i in range(min(len(self._ids), len(self._items))):
            self._tree.item(self._ids[i], values=self._value_fn(i, self._items[i]))
