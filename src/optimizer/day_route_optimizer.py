"""日内路线优化入口（当前：保持 activity 顺序）。"""

from src.data_layer.schema import Plan


def optimize_daily_routes(plan: Plan) -> Plan:
    """优化每日 POI 访问顺序；暂无 OR-Tools 时原样返回。"""
    return plan
