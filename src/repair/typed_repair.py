"""类型化修复调度（占位）。"""

from src.data_layer.schema import CandidatePool, Constraints, OfficialPlan, TypedError


def typed_repair(
    plan: OfficialPlan,
    errors: list[TypedError],
    constraints: Constraints,
    candidates: CandidatePool,
) -> OfficialPlan:
    """暂未实现修复逻辑，原样返回。"""
    return plan
