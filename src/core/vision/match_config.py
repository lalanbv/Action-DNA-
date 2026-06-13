"""多模板匹配的框架无关纯逻辑。

tk 与 Qt 对话框、描述符、匹配器共用此模块,确保双框架规则与规格一致。
所有函数为纯函数(无副作用、返回新对象),便于单元测试。
"""

from __future__ import annotations

from src.core.action import MatchStrategy, ThresholdMode

# AUTO 模式使用的稳健阈值:比默认 0.8 宽松,容忍按钮状态色差;
# 误匹配由 TemplateMatcher._verify_match 二次验证拦截。集中一处便于调优。
AUTO_THRESHOLD: float = 0.72


def normalize_templates(
    primary_path: str,
    alt_paths: list[str],
    alt_thresholds: list[float | None],
) -> tuple[str, list[str], list[float | None]]:
    """归一化多模板配置。

    - 过滤 alt 中的空路径
    - 去重(同一路径只保留第一次出现及其阈值)
    - 对齐 alt_thresholds 长度到 alt_paths(不足补 None)

    返回 (primary, alts, aligned_thresholds),均为新对象(不可变语义)。
    """
    seen: set[str] = set()
    cleaned_alts: list[str] = []
    cleaned_thr: list[float | None] = []

    for idx, path in enumerate(alt_paths):
        if not path or path in seen:
            continue
        seen.add(path)
        cleaned_alts.append(path)
        thr = alt_thresholds[idx] if idx < len(alt_thresholds) else None
        cleaned_thr.append(thr)

    # 防御性对齐(cleaned_thr 已与 cleaned_alts 等长,此处保不变量)
    while len(cleaned_thr) < len(cleaned_alts):
        cleaned_thr.append(None)

    return primary_path, cleaned_alts, cleaned_thr


def effective_thresholds(
    mode: ThresholdMode,
    base_threshold: float,
    alt_thresholds: list[float | None],
    count: int,
) -> list[float]:
    """根据阈值模式计算每张模板的有效阈值。

    count 为模板总数(主图 + 备用图)。alt_thresholds 的索引对应从第 2 张起的备用图。

    - AUTO:全部用 AUTO_THRESHOLD
    - GLOBAL:全部用 base_threshold
    - PER_TEMPLATE:主图用 base;alt[i] 有值用其值,None 继承 base
    """
    if mode == ThresholdMode.AUTO:
        return [AUTO_THRESHOLD] * count

    if mode == ThresholdMode.GLOBAL:
        return [base_threshold] * count

    # PER_TEMPLATE
    result: list[float] = [base_threshold]  # 主图(索引 0)
    for i in range(count - 1):
        alt_idx = i  # alt_thresholds 索引对应从第 1 张备用图起
        thr = alt_thresholds[alt_idx] if alt_idx < len(alt_thresholds) else None
        result.append(thr if thr is not None else base_threshold)
    return result


def resolve_find_any_params(
    primary_path: str,
    alt_paths: list[str],
    base_threshold: float,
    alt_thresholds: list[float | None],
    threshold_mode: ThresholdMode,
    match_strategy: MatchStrategy,
) -> tuple[list[str], list[float], MatchStrategy]:
    """汇总出最终传给 TemplateMatcher.find_any() 的参数。

    返回 (paths, per_template_thresholds, strategy)。
    paths = [primary] + alts(已归一化去空去重);若 primary 为空则仅 alts。
    """
    _, clean_alts, clean_thr = normalize_templates(primary_path, alt_paths, alt_thresholds)
    paths = [primary_path] + clean_alts if primary_path else clean_alts
    count = len(paths)
    per_thr = effective_thresholds(threshold_mode, base_threshold, clean_thr, count)
    return paths, per_thr, match_strategy
