"""规划工具：时间计算、activity 构建。"""

from __future__ import annotations

from typing import Any


def add_minutes(time_str: str, minutes: int) -> str:
    """HH:MM 加分钟。"""
    h, m = map(int, time_str.split(":"))
    total = h * 60 + m + minutes
    return f"{total // 60:02d}:{total % 60:02d}"


def time_to_minutes(time_str: str) -> int:
    h, m = map(int, time_str.split(":"))
    return h * 60 + m


def minutes_to_time(total: int) -> str:
    total = max(0, total)
    return f"{total // 60:02d}:{total % 60:02d}"


def max_time(a: str, b: str) -> str:
    return a if time_to_minutes(a) >= time_to_minutes(b) else b


def annotate_transports(
    segments: list[dict[str, Any]],
    people: int,
    taxi_cars: int | None = None,
) -> list[dict[str, Any]]:
    """补全官方 transport 字段：price / tickets / cars。"""
    cars = taxi_cars if taxi_cars is not None else max(1, (people + 3) // 4)
    result: list[dict[str, Any]] = []
    for seg in segments:
        item = dict(seg)
        item.setdefault("price", item.get("cost", 0))
        item.setdefault("cost", item.get("price", 0))
        item.setdefault("distance", item.get("distance", 0.0))
        mode = item.get("mode", "")
        if mode == "metro":
            item["tickets"] = people
        elif mode == "taxi":
            item["cars"] = cars
        result.append(item)
    return result


def empty_transports() -> list[dict[str, Any]]:
    """空交通列表（满足 schema required）。"""
    return []


def make_activity(
    act_type: str,
    start_time: str,
    end_time: str,
    cost: float,
    price: float,
    transports: list[dict] | None = None,
    position: str = "",
    tickets: int = 1,
    extra: dict | None = None,
) -> dict[str, Any]:
    """构建单条官方 activity 字典。"""
    act: dict[str, Any] = {
        "type": act_type,
        "start_time": start_time,
        "end_time": end_time,
        "cost": round(float(cost), 2),
        "price": round(float(price), 2),
        "transports": transports if transports is not None else empty_transports(),
    }
    if position:
        act["position"] = position
    if act_type in ("attraction", "airplane", "train"):
        act["tickets"] = tickets
    if extra:
        act.update(extra)
    return act


def make_intercity_activity(row: dict, people: int, is_return: bool = False) -> dict[str, Any]:
    """从城际交通记录构建 airplane/train activity。"""
    mode = row.get("type", "airplane")
    start = row.get("From") or row.get("start") or row.get("start_city", "")
    end = row.get("To") or row.get("end") or row.get("target_city", "")
    start_time = row.get("BeginTime") or row.get("start_time") or "08:00"
    end_time = row.get("EndTime") or row.get("end_time") or "10:30"
    unit_price = float(row.get("Price") or row.get("Cost") or row.get("price") or 500)
    total_cost = unit_price * people

    extra: dict[str, Any] = {"start": start, "end": end}
    if mode == "airplane":
        extra["FlightID"] = str(row.get("FlightID") or row.get("FlightId") or f"FL_{start}_{end}")
    else:
        extra["TrainID"] = str(row.get("TrainID") or row.get("TrainId") or f"TR_{start}_{end}")

    return make_activity(
        act_type=mode,
        start_time=start_time,
        end_time=end_time,
        cost=total_cost,
        price=unit_price,
        tickets=people,
        transports=empty_transports(),
        extra=extra,
    )


def normalize_transports(segments: list[dict], people: int = 1, taxi_cars: int | None = None) -> list[dict]:
    """补全 transport 段的 price/tickets/cars 字段。"""
    return annotate_transports(segments, people, taxi_cars)
