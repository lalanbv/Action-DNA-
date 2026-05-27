"""ScriptExporter — 将 FlowGraph 导出为独立可运行的 Python 脚本或可编辑 JSON。"""

from __future__ import annotations

import base64
import json
import logging
import platform
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from pathlib import Path

from src.core.action import ActionType
from src.core.step_types import BaseStep
from src.core.flow import FlowGraph, FlowNode, NodeType

logger = logging.getLogger(__name__)


class GraphComplexity(Enum):
    """图的复杂度级别"""
    LINEAR = auto()
    BRANCHING = auto()
    COMPLEX = auto()


@dataclass(frozen=True)
class ExportResult:
    """导出操作的结果"""
    output_path: Path
    complexity: GraphComplexity
    warnings: list[str]
    node_count: int
    template_count: int


class ScriptExporter:
    """将 FlowGraph 导出为独立的 Python 脚本。

    导出的脚本：
    - 仅依赖 opencv-python, numpy, mss, pyautogui
    - 模板图片嵌入为 base64
    - 保留简化的反检测（随机延迟、偏移）
    - 命令行参数：--loop N --region x,y,w,h

    限制：
    - 仅支持线性图（START -> ... -> END）
    - 分支和循环节点会触发警告，导出时取第一条路径
    """

    def __init__(self, template_dir: Path | None = None) -> None:
        self._template_dir = template_dir

    def export(
        self,
        graph: FlowGraph,
        output_path: Path,
        profile_name: str = "exported",
    ) -> ExportResult:
        """导出 FlowGraph 为 Python 脚本。"""
        complexity = self.analyze_complexity(graph)
        warnings = self._build_warnings(graph, complexity)

        templates = self._collect_templates(graph)
        nodes = self._linearize(graph)

        script = self._generate_script(
            nodes=nodes,
            templates=templates,
            profile_name=profile_name,
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(script, encoding="utf-8")

        node_count = len([n for n in nodes if n.action and n.enabled and n.action.enabled])
        template_count = len(templates)

        logger.info("脚本已导出: %s (%d 节点, %d 模板)", output_path, node_count, template_count)

        return ExportResult(
            output_path=output_path,
            complexity=complexity,
            warnings=warnings,
            node_count=node_count,
            template_count=template_count,
        )

    def export_json(
        self,
        steps: list[BaseStep],
        meta: dict | None = None,
    ) -> str:
        """将 ActionStep 列表导出为人类可编辑的 JSON 格式。"""
        return json.dumps(
            {
                "version": "2.0",
                "meta": {
                    "exported_at": datetime.now().isoformat(),
                    "platform": platform.system(),
                    **(meta or {}),
                },
                "steps": [
                    self._step_to_json_dict(step, i)
                    for i, step in enumerate(steps)
                ],
            },
            ensure_ascii=False,
            indent=2,
        )

    def _step_to_json_dict(self, step: BaseStep, index: int) -> dict:
        """单个 BaseStep → JSON 可编辑字典。"""
        d: dict = {"index": index, "type": step.action_type.name}

        match step.action_type:
            case ActionType.CLICK_POS:
                d.update({
                    "pos": [step.pos_x, step.pos_y],
                    "clicks": step.clicks,
                    "button": step.button,
                    "hold": step.hold_duration,
                })
            case ActionType.PRESS_KEY:
                if step.text:
                    d["text"] = step.text
                else:
                    d["key"] = step.key
            case ActionType.HOLD_KEY:
                d.update({"key": step.keys_hold, "duration": step.hold_duration})
            case ActionType.MOUSE_SCROLL:
                d.update({
                    "clicks": step.scroll_clicks,
                    "horizontal": step.scroll_delta_x,
                    "pos": [step.pos_x, step.pos_y],
                })
            case ActionType.MOUSE_MOVE:
                d.update({
                    "offset": [step.offset_x, step.offset_y],
                    "speed": step.move_speed,
                    "curve": step.curve_amount,
                    "has_path": bool(step.path_points),
                    "button": step.button,
                })
            case ActionType.MOUSE_DRAG:
                d.update({
                    "start": [step.start_x, step.start_y],
                    "end": [step.end_x, step.end_y],
                    "button": step.button,
                })
            case ActionType.WAIT:
                d["seconds"] = step.wait_seconds
            case ActionType.WAIT_RANDOM:
                d.update({"min": step.wait_min, "max": step.wait_max})
            case ActionType.KEY_COMBO:
                d.update({"keys": step.combo_keys, "mode": step.combo_mode})

        d["duration"] = step.recorded_duration
        d["enabled"] = step.enabled
        return d

    def analyze_complexity(self, graph: FlowGraph) -> GraphComplexity:
        """分析图的复杂度（导出前可调用）。"""
        has_condition = any(
            n.node_type == NodeType.CONDITION for n in graph.nodes.values()
        )
        has_loop = any(
            n.node_type == NodeType.LOOP for n in graph.nodes.values()
        )
        has_merge = any(
            n.node_type == NodeType.MERGE for n in graph.nodes.values()
        )

        if has_condition or has_merge:
            return GraphComplexity.BRANCHING
        if has_loop:
            return GraphComplexity.COMPLEX

        for node in graph.nodes.values():
            out_edges = graph.get_outgoing_edges(node.node_id)
            if len(out_edges) > 1:
                return GraphComplexity.BRANCHING

        return GraphComplexity.LINEAR

    # ── 内部方法 ─────────────────────────────────────────────

    def _build_warnings(
        self, _graph: FlowGraph, complexity: GraphComplexity,
    ) -> list[str]:
        if complexity == GraphComplexity.LINEAR:
            return []

        warnings: list[str] = []
        if complexity == GraphComplexity.BRANCHING:
            warnings.append("图包含分支节点（CONDITION/MERGE），仅导出第一条路径")
        if complexity == GraphComplexity.COMPLEX:
            warnings.append("图包含 LOOP 节点，循环逻辑不会导出到脚本中")
        return warnings

    def _linearize(self, graph: FlowGraph) -> list[FlowNode]:
        """沿连接线性遍历图节点，收集有序节点列表。"""
        start_id = graph.start_node_id
        if not start_id or start_id not in graph.nodes:
            raise ValueError("图中没有有效的 START 节点")

        result: list[FlowNode] = []
        visited: set[str] = set()
        current_id = start_id

        while current_id and current_id not in visited:
            visited.add(current_id)
            node = graph.nodes.get(current_id)
            if node is None:
                break
            result.append(node)

            out_edges = graph.get_outgoing_edges(current_id)
            if out_edges:
                current_id = out_edges[0].to_node
            else:
                current_id = ""

        return result

    def _collect_templates(self, graph: FlowGraph) -> dict[str, str]:
        """收集图中引用的所有模板图片，编码为 base64。"""
        templates: dict[str, str] = {}

        if not self._template_dir:
            return templates

        for node in graph.nodes.values():
            if not node.action:
                continue
            if node.action.action_type != ActionType.CLICK_IMAGE:
                continue
            image_path = node.action.image_path
            if not image_path:
                continue
            full_path = self._template_dir / image_path
            if full_path.exists():
                data = full_path.read_bytes()
                b64 = base64.b64encode(data).decode("ascii")
                templates[image_path] = b64

        return templates

    def _generate_script(
        self,
        nodes: list[FlowNode],
        templates: dict[str, str],
        profile_name: str,
    ) -> str:
        lines: list[str] = []

        lines.extend(self._gen_header(profile_name))
        lines.extend(self._gen_imports())
        lines.extend(self._gen_template_data(templates))
        lines.extend(self._gen_utility_functions())
        lines.extend(self._gen_action_functions(nodes))
        lines.extend(self._gen_main_loop(nodes, profile_name))

        return "\n".join(lines)

    def _gen_header(self, profile_name: str) -> list[str]:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return [
            "#!/usr/bin/env python3",
            "# -*- coding: utf-8 -*-",
            '"""',
            f"Action<DNA> 导出脚本: {profile_name}",
            f"导出时间: {now}",
            "",
            "依赖: pip install opencv-python numpy mss pyautogui",
            f"使用: python {profile_name}.py --loop 10 --region 100,100,800,600",
            '"""',
            "",
        ]

    def _gen_imports(self) -> list[str]:
        return [
            "import argparse",
            "import base64",
            "import time",
            "import random",
            "",
            "import cv2",
            "import numpy as np",
            "import mss",
            "import pyautogui",
            "",
            "",
        ]

    def _gen_template_data(self, templates: dict[str, str]) -> list[str]:
        lines = ["# === 模板图片数据 ===", ""]

        if not templates:
            lines.append("TEMPLATES: dict[str, np.ndarray] = {}")
            lines.append("")
            lines.append("")
            return lines

        lines.append("TEMPLATES: dict[str, np.ndarray] = {}")
        lines.append("")

        for filename, b64_data in templates.items():
            var_name = Path(filename).stem.replace("-", "_").replace(" ", "_")
            lines.append(f"# {filename}")
            lines.append(f"_{var_name}_b64 = {b64_data!r}")
            lines.append(f'TEMPLATES["{filename}"] = cv2.imdecode(')
            lines.append(f"    np.frombuffer(base64.b64decode(_{var_name}_b64), np.uint8),")
            lines.append("    cv2.IMREAD_COLOR")
            lines.append(")")
            lines.append("")

        lines.append("")
        return lines

    def _gen_utility_functions(self) -> list[str]:
        return [
            "# === 工具函数 ===",
            "",
            "",
            "def find_template(sct, template, region=None, threshold=0.8):",
            '    """在屏幕截图中查找模板图片"""',
            "    screenshot = np.array(sct.grab(region))",
            "    screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGRA2BGR)",
            "    result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)",
            "    _, max_val, _, max_loc = cv2.minMaxLoc(result)",
            "    if max_val >= threshold:",
            "        h, w = template.shape[:2]",
            "        cx = max_loc[0] + w // 2",
            "        cy = max_loc[1] + h // 2",
            "        if region:",
            '            cx += region["left"]',
            '            cy += region["top"]',
            "        return cx, cy, max_val",
            "    return None",
            "",
            "",
            "def safe_click(x, y, button=\"left\"):",
            '    """带反检测的点击操作"""',
            "    ox = random.randint(-3, 3)",
            "    oy = random.randint(-3, 3)",
            "    tx, ty = x + ox, y + oy",
            "    dur = random.uniform(0.15, 0.35)",
            "    pyautogui.moveTo(tx, ty, duration=dur)",
            "    time.sleep(random.uniform(0.05, 0.15))",
            "    pyautogui.click(x=tx, y=ty, button=button)",
            "",
            "",
            "def random_wait(min_s, max_s):",
            '    """随机等待"""',
            "    time.sleep(random.uniform(min_s, max_s))",
            "",
            "",
        ]

    def _gen_action_functions(self, nodes: list[FlowNode]) -> list[str]:
        lines = ["# === 动作步骤 ===", ""]

        step = 0
        for node in nodes:
            if not node.action or not node.enabled or not node.action.enabled:
                continue
            step += 1
            action = node.action
            lines.extend(self._gen_single_step(step, action))
            lines.append("")

        return lines

    def _gen_single_step(self, step: int, action: BaseStep) -> list[str]:
        at = action.action_type

        if at == ActionType.CLICK_IMAGE:
            return self._gen_click_image_step(step, action)
        if at == ActionType.CLICK_POS:
            return self._gen_click_pos_step(step, action)
        if at == ActionType.PRESS_KEY:
            return self._gen_press_key_step(step, action)
        if at in (ActionType.WAIT, ActionType.WAIT_RANDOM):
            return self._gen_wait_step(step, action)
        if at == ActionType.MOUSE_SCROLL:
            return self._gen_scroll_step(step, action)
        if at == ActionType.HOLD_KEY:
            return self._gen_hold_key_step(step, action)

        return []

    def _gen_click_image_step(self, step: int, action: BaseStep) -> list[str]:
        return [
            f"def step_{step}_click_image(sct, region=None):",
            f'    """步骤 {step}: 查找并点击模板图片"""',
            f'    template = TEMPLATES.get("{action.image_path}")',
            "    if template is None:",
            f'        print(f"[步骤 {step}] 模板图片未找到: {action.image_path}")',
            "        return False",
            "    result = find_template(sct, template, region)",
            "    if result:",
            "        x, y, confidence = result",
            f'        print(f"[步骤 {step}] 找到目标 (置信度: {{confidence:.2f}})")',
            "        safe_click(x, y)",
            "        return True",
            f'    print(f"[步骤 {step}] 未找到目标")',
            "    return False",
        ]

    def _gen_click_pos_step(self, step: int, action: BaseStep) -> list[str]:
        x = action.pos_x
        y = action.pos_y
        return [
            f"def step_{step}_click_pos(region=None):",
            f'    """步骤 {step}: 点击固定坐标"""',
            f"    x, y = {x}, {y}",
            "    if region:",
            '        x += region["left"]',
            '        y += region["top"]',
            "    safe_click(x, y)",
        ]

    def _gen_press_key_step(self, step: int, action: BaseStep) -> list[str]:
        return [
            f"def step_{step}_press_key():",
            f'    """步骤 {step}: 按键"""',
            f'    pyautogui.press("{action.key}")',
            "    time.sleep(random.uniform(0.1, 0.3))",
        ]

    def _gen_wait_step(self, step: int, action: BaseStep) -> list[str]:
        if action.action_type == ActionType.WAIT_RANDOM:
            mn = action.wait_min
            mx = action.wait_max
        else:
            t = action.wait_seconds
            mn, mx = round(t * 0.8, 2), round(t * 1.2, 2)

        return [
            f"def step_{step}_wait():",
            f'    """步骤 {step}: 等待"""',
            f"    random_wait({mn}, {mx})",
        ]

    def _gen_scroll_step(self, step: int, action: BaseStep) -> list[str]:
        clicks = action.scroll_clicks
        direction = "scroll up" if clicks > 0 else "scroll down"
        return [
            f"def step_{step}_scroll():",
            f'    """步骤 {step}: {direction}"""',
            f"    pyautogui.scroll({clicks})",
            "    time.sleep(random.uniform(0.2, 0.5))",
        ]

    def _gen_hold_key_step(self, step: int, action: BaseStep) -> list[str]:
        key = action.keys_hold or action.key
        duration = action.hold_duration
        return [
            f"def step_{step}_hold_key():",
            f'    """步骤 {step}: 长按按键"""',
            f'    pyautogui.keyDown("{key}")',
            f"    time.sleep({duration})",
            f'    pyautogui.keyUp("{key}")',
        ]

    def _gen_main_loop(
        self, nodes: list[FlowNode], profile_name: str,
    ) -> list[str]:
        step_calls: list[str] = []
        step = 0
        for node in nodes:
            if not node.action or not node.enabled or not node.action.enabled:
                continue
            step += 1
            at = node.action.action_type
            # try 块内需要 16 个空格缩进 (def:4 + with:4 + for:4 + try:4)
            indent = "                "
            if at == ActionType.CLICK_IMAGE:
                step_calls.append(f"{indent}step_{step}_click_image(sct, region)")
            elif at == ActionType.CLICK_POS:
                step_calls.append(f"{indent}step_{step}_click_pos(region)")
            elif at == ActionType.PRESS_KEY:
                step_calls.append(f"{indent}step_{step}_press_key()")
            elif at in (ActionType.WAIT, ActionType.WAIT_RANDOM):
                step_calls.append(f"{indent}step_{step}_wait()")
            elif at == ActionType.MOUSE_SCROLL:
                step_calls.append(f"{indent}step_{step}_scroll()")
            elif at == ActionType.HOLD_KEY:
                step_calls.append(f"{indent}step_{step}_hold_key()")

        calls_lines = step_calls if step_calls else ["                pass"]

        lines = [
            "# === 主程序 ===",
            "",
            "",
            "def run_loop(loop_count, region=None):",
            '    """执行动作链循环"""',
            '    print(f"开始执行: {loop_count} 次循环")',
            "    with mss.mss() as sct:",
            "        for i in range(loop_count):",
            r'            print(f"\n--- 第 {i + 1}/{loop_count} 次循环 ---")',
            "            try:",
        ]
        lines.extend(calls_lines)
        lines.extend([
            "            except KeyboardInterrupt:",
            r'                print("\n用户中断")',
            "                break",
            "            except Exception as e:",
            '                print(f"循环出错: {e}")',
            "",
            "            if i < loop_count - 1:",
            "                random_wait(0.5, 1.5)",
            "",
            r'    print("\n执行完成!")',
            "",
            "",
            "def main():",
            "    parser = argparse.ArgumentParser(",
            f'        description="Action<DNA> 导出脚本: {profile_name}"',
            "    )",
            '    parser.add_argument("--loop", type=int, default=10,',
            '        help="循环次数 (默认: 10)")',
            '    parser.add_argument("--region", type=str, default=None,',
            '        help="执行区域 x,y,w,h (例: 100,100,800,600)")',
            "    args = parser.parse_args()",
            "",
            "    region = None",
            "    if args.region:",
            '        parts = [int(x) for x in args.region.split(",")]',
            "        if len(parts) == 4:",
            '            region = {"left": parts[0], "top": parts[1],',
            '                      "width": parts[2], "height": parts[3]}',
            "",
            f'    print(f"Action<DNA> 导出脚本: {profile_name}")',
            '    print("=" * 40)',
            "    run_loop(args.loop, region)",
            "",
            "",
            'if __name__ == "__main__":',
            "    main()",
            "",
        ])
        return lines
