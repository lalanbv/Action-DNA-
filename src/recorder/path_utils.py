"""路径处理工具函数。"""

from __future__ import annotations

import math


def simplify_path(
    points: list[tuple[int, int, float]],
    epsilon: float = 2.0,
) -> list[tuple[int, int, float]]:
    """Ramer-Douglas-Peucker 路径简化 — 保留曲线精度，削减直线冗余点。

    2px 采样会产生密集路径点（200px 直线 ≈ 100 点），
    简化后直线段仅保留起终点，曲线段保留关键拐点。
    始终保留首尾点，epsilon=2 与采样间距匹配。
    迭代栈实现，无递归深度限制。
    """
    n = len(points)
    if n <= 2:
        return points

    keep = [False] * n
    keep[0] = True
    keep[-1] = True

    stack: list[tuple[int, int]] = [(0, n - 1)]

    while stack:
        start_idx, end_idx = stack.pop()
        sx, sy, _ = points[start_idx]
        ex, ey, _ = points[end_idx]
        dx = ex - sx
        dy = ey - sy
        line_len_sq = dx * dx + dy * dy

        max_dist = 0.0
        max_idx = start_idx

        for i in range(start_idx + 1, end_idx):
            px, py, _ = points[i]
            if line_len_sq < 1e-6:
                dist = math.hypot(px - sx, py - sy)
            else:
                t = max(0.0, min(1.0, ((px - sx) * dx + (py - sy) * dy) / line_len_sq))
                proj_x = sx + t * dx
                proj_y = sy + t * dy
                dist = math.hypot(px - proj_x, py - proj_y)
            if dist > max_dist:
                max_dist = dist
                max_idx = i

        if max_dist > epsilon:
            keep[max_idx] = True
            stack.append((start_idx, max_idx))
            stack.append((max_idx, end_idx))

    return [points[i] for i in range(n) if keep[i]]
