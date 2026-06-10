"""提交格式校验。"""

from src.data_layer.schema import OfficialPlan


def check_format(plan: OfficialPlan) -> list[str]:
    """校验 JSON 字段完整性。

    Args:
        plan: 官方格式行程。

    Returns:
        list[str]: 格式问题列表。
    """
    raise NotImplementedError
