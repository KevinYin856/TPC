"""路线评分。"""

from __future__ import annotations

from typing import Any


def score_route(route: list[str], distance_matrix: dict[tuple[str, str], float]) -> float:
    """计算路线总成本/时间。

    Args:
        route: POI 访问顺序（POI ID 或名称列表）。
        distance_matrix: 距离/时间矩阵，键为 (from, to) 元组，值为距离或时间。

    Returns:
        float: 路线分数（越低越好）。
    """
    if len(route) <= 1:
        return 0.0

    total = 0.0
    for i in range(len(route) - 1):
        key = (route[i], route[i + 1])
        val = distance_matrix.get(key)
        if val is None:
            # 尝试按名称匹配
            val = _fuzzy_lookup(route[i], route[i + 1], distance_matrix)
        if val is None:
            val = float("inf")
        total += float(val)

    return total


def _fuzzy_lookup(a: str, b: str, dm: dict) -> float | None:
    """在键中模糊搜索匹配项。"""
    for (ka, kb), v in dm.items():
        if (str(ka) == str(a) and str(kb) == str(b)) or (
            str(ka) in str(a) and str(kb) in str(b)
        ):
            return float(v)
    return None
