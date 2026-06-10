"""核心行程构建：约束驱动 + ChinaTravel WorldEnv。"""

from __future__ import annotations

from typing import Any

from src.data_layer.chinatravel_bridge import infer_lang
from src.data_layer.schema import CandidatePool, Constraints, POICandidate
from src.data_layer.world_env_client import SandboxClient, get_sandbox
from src.planner.constraint_profile import (
    PlanningConstraints,
    extract_planning_constraints,
    max_meal_price,
)
from src.planner.plan_utils import (
    add_minutes,
    make_activity,
    make_intercity_activity,
    max_time,
    normalize_transports,
    time_to_minutes,
)


def _poi_price(poi: POICandidate | None, default: float = 0.0) -> float:
    if poi is None:
        return default
    meta = poi.metadata or {}
    for key in ("price", "cost", "ticket_price", "Price"):
        if meta.get(key) not in (None, ""):
            try:
                return float(meta[key])
            except (TypeError, ValueError):
                pass
    return default


def _records_to_candidates(records: list[dict[str, Any]]) -> list[POICandidate]:
    out: list[POICandidate] = []
    for r in records:
        if not r.get("name"):
            continue
        out.append(POICandidate(
            poi_id=str(r.get("id", r.get("name"))),
            name=str(r.get("name")),
            metadata=r,
        ))
    return out


def _ensure_candidates(
    sandbox: SandboxClient,
    target_city: str,
    candidates: CandidatePool,
) -> tuple[list[POICandidate], list[POICandidate], list[POICandidate]]:
    pois = list(candidates.pois or [])
    hotels = list(candidates.hotels or [])
    restaurants = list(candidates.restaurants or [])

    if not pois:
        pois = _records_to_candidates(sandbox.list_attractions(target_city, limit=30))
    if not hotels:
        hotels = _records_to_candidates(sandbox.list_hotels(target_city, limit=20))
    if not hotels:
        hotels = [POICandidate(
            poi_id="hotel_default",
            name=f"{target_city} Central Hotel",
            metadata={"price": 300.0},
        )]
    if not restaurants:
        restaurants = _records_to_candidates(sandbox.list_restaurants(target_city, limit=30))
    return pois, hotels, restaurants


def _select_hotel(
    sandbox: SandboxClient,
    pc: PlanningConstraints,
    hotels: list[POICandidate],
) -> POICandidate | None:
    if not hotels:
        return None

    pool = hotels
    if pc.hotel_near_anchor and pc.hotel_max_distance_km:
        nearby = sandbox.hotels_nearby(
            pc.target_city,
            pc.hotel_near_anchor,
            topk=30,
            max_dist_km=pc.hotel_max_distance_km + 0.01,
        )
        if nearby:
            pool = _records_to_candidates(nearby)

    if pc.required_hotel_type:
        filtered = [
            h for h in pool
            if pc.required_hotel_type in str((h.metadata or {}).get("featurehoteltype", ""))
            or pc.required_hotel_type in str((h.metadata or {}).get("featureHotelType", ""))
        ]
        if filtered:
            pool = filtered

    if pc.accommodation_budget is not None:
        affordable = [h for h in pool if _poi_price(h, 9999) * max(1, (pc.people + 1) // 2) <= pc.accommodation_budget]
        if affordable:
            pool = affordable

    pool = sorted(pool, key=lambda h: _poi_price(h, 9999))
    return pool[0] if pool else hotels[0]


def _select_restaurants(
    pc: PlanningConstraints,
    restaurants: list[POICandidate],
) -> tuple[POICandidate | None, POICandidate | None, POICandidate | None]:
    """返回 (breakfast, lunch, dinner) 候选；无数据时用占位。"""
    if not restaurants:
        placeholder = POICandidate(
            poi_id="meal_default",
            name=f"{pc.target_city} Local Restaurant",
            metadata={"price": 30.0},
        )
        return placeholder, placeholder, placeholder

    cap = max_meal_price(pc)
    affordable = restaurants
    if cap is not None:
        affordable = [r for r in restaurants if _poi_price(r, 999) <= cap]
        if not affordable:
            affordable = sorted(restaurants, key=lambda r: _poi_price(r))[:5]

    affordable = sorted(affordable, key=lambda r: _poi_price(r))
    cheap = affordable[0]
    mid = affordable[len(affordable) // 2] if len(affordable) > 1 else cheap
    return cheap, mid, mid


def _pick_pois_per_day(
    pois: list[POICandidate],
    num_days: int,
    pc: PlanningConstraints,
    policy: str,
    pace_weight: float,
) -> list[list[POICandidate]]:
    if not pois or num_days <= 0:
        return [[] for _ in range(max(num_days, 1))]

    must_names = set(pc.must_visit)
    must = [p for p in pois if p.name in must_names or p.poi_id in must_names]
    others = [p for p in pois if p not in must]
    ordered = must + sorted(others, key=lambda p: -p.score)

    if policy == "preference" or pace_weight > 0.6:
        per_day = 3
    elif policy == "safe" or pace_weight < 0.4:
        per_day = 2
    else:
        per_day = 2
    per_day = min(per_day, max(1, len(ordered) // max(num_days, 1) + 1))

    days: list[list[POICandidate]] = [[] for _ in range(num_days)]
    idx = 0
    for d in range(num_days):
        for _ in range(per_day):
            if idx < len(ordered):
                days[d].append(ordered[idx])
                idx += 1
    while idx < len(ordered):
        days[idx % num_days].append(ordered[idx])
        idx += 1
    return days


def _intercity_end_position(row: dict[str, Any], target_city: str) -> str:
    end = row.get("To") or row.get("end") or target_city
    if row.get("type") == "airplane":
        return str(row.get("To") or row.get("end") or f"{target_city} Airport")
    if row.get("type") == "train":
        return str(row.get("To") or row.get("end") or f"{target_city} Station")
    return str(end)


def _goto(
    sandbox: SandboxClient,
    pc: PlanningConstraints,
    city: str,
    start: str,
    end: str,
    start_time: str,
    *,
    use_taxi: bool = False,
) -> tuple[list[dict[str, Any]], str]:
    if not start or not end:
        return [], start_time
    mode = "taxi" if use_taxi else "metro"
    if not pc.prefer_metro and pc.prefer_taxi_for_hotel:
        mode = "taxi"
    segments = sandbox.goto(
        city, start, end, start_time, mode,
        people=pc.people,
        taxi_cars=pc.taxi_cars,
    )
    if not segments and mode == "metro":
        segments = sandbox.goto(
            city, start, end, start_time, "taxi",
            people=pc.people,
            taxi_cars=pc.taxi_cars,
        )
    end_time = segments[-1]["end_time"] if segments else start_time
    return normalize_transports(segments, pc.people, pc.taxi_cars), end_time


def _append_meal(
    activities: list[dict],
    meal_type: str,
    restaurant: POICandidate | None,
    sandbox: SandboxClient,
    pc: PlanningConstraints,
    pos: str,
    current_time: str,
    fallback_name: str,
) -> tuple[str, str]:
    name = restaurant.name if restaurant else fallback_name
    price = _poi_price(restaurant, 35.0 if meal_type == "breakfast" else 50.0)
    duration = 45 if meal_type == "breakfast" else 60
    if restaurant and not sandbox.is_restaurant_open(pc.target_city, name, current_time):
        current_time = max_time(current_time, "11:30" if meal_type == "lunch" else "17:30")

    transports, arrive = _goto(sandbox, pc, pc.target_city, pos, name, current_time)
    t_start = transports[0]["start_time"] if transports else current_time
    t_end = add_minutes(arrive, duration)
    activities.append(make_activity(
        meal_type, t_start, t_end,
        price * pc.people, price, transports,
        position=name, tickets=pc.people,
    ))
    return name, add_minutes(t_end, 10)


def build_day_activities(
    day_index: int,
    num_days: int,
    day_pois: list[POICandidate],
    hotel: POICandidate | None,
    meals: tuple[POICandidate | None, POICandidate | None, POICandidate | None],
    pc: PlanningConstraints,
    sandbox: SandboxClient,
    *,
    current_time: str = "09:00",
    prev_position: str = "",
    skip_breakfast: bool = False,
) -> tuple[list[dict[str, Any]], str]:
    """构建单日 activity（餐饮/景点/住宿），满足票务与交通约束。"""
    target = pc.target_city
    activities: list[dict[str, Any]] = []
    pos = prev_position or (hotel.name if hotel else "")
    breakfast_r, lunch_r, dinner_r = meals

    if not skip_breakfast:
        pos, current_time = _append_meal(
            activities, "breakfast", breakfast_r, sandbox, pc, pos, current_time,
            f"{target} Breakfast Spot",
        )
    elif pos and time_to_minutes(current_time) < time_to_minutes("11:00"):
        current_time = "11:00"

    if not day_pois:
        pos, current_time = _append_meal(
            activities, "lunch", lunch_r, sandbox, pc, pos, current_time,
            f"{target} Lunch Spot",
        )

    for i, poi in enumerate(day_pois):
        visit_min = 90
        meta = poi.metadata or {}
        if meta.get("recommendmintime"):
            try:
                visit_min = int(float(meta["recommendmintime"]) * 60)
            except (TypeError, ValueError):
                pass

        if not sandbox.is_attraction_open(target, poi.name, current_time):
            current_time = max_time(current_time, "09:30")

        transports, arrive = _goto(sandbox, pc, target, pos, poi.name, current_time)
        t_start = transports[0]["start_time"] if transports else current_time
        t_end = add_minutes(arrive, visit_min)
        price = _poi_price(poi, 0.0)
        activities.append(make_activity(
            "attraction", t_start, t_end,
            price * pc.people, price, transports,
            position=poi.name, tickets=pc.activity_tickets or pc.people,
        ))
        pos = poi.name
        current_time = add_minutes(t_end, 15)

        if i == 0:
            pos, current_time = _append_meal(
                activities, "lunch", lunch_r, sandbox, pc, pos, current_time,
                f"{target} Lunch Spot",
            )

    pos, current_time = _append_meal(
        activities, "dinner", dinner_r, sandbox, pc, pos,
        max_time(current_time, "17:30"),
        f"{target} Dinner Spot",
    )

    if day_index < num_days and hotel:
        at0 = max_time(current_time, "20:00")
        hp = _poi_price(hotel, 300.0)
        transports, arrive = _goto(
            sandbox, pc, target, pos, hotel.name, at0, use_taxi=True,
        )
        at1 = add_minutes(arrive, 60)
        if time_to_minutes(at1) <= time_to_minutes(at0):
            at1 = add_minutes(at0, 120)
        rooms = max(1, (pc.people + 1) // 2)
        activities.append(make_activity(
            "accommodation", at0, at1,
            hp * rooms, hp, transports,
            position=hotel.name, tickets=pc.people,
            extra={"rooms": rooms, "room_type": 1},
        ))
        pos = hotel.name

    return activities, pos


def build_full_plan_dict(
    constraints: Constraints,
    candidates: CandidatePool,
    preferences,
    policy: str = "safe",
) -> dict[str, Any]:
    """构建完整官方 plan 字典。"""
    pc = extract_planning_constraints(constraints)
    lang = infer_lang(pc.target_city or pc.start_city)
    sandbox = get_sandbox(lang)

    pois, hotels, restaurants = _ensure_candidates(sandbox, pc.target_city, candidates)
    hotel = _select_hotel(sandbox, pc, hotels)
    meals = _select_restaurants(pc, restaurants)

    pace = getattr(preferences, "pace_weight", 0.5)
    poi_by_day = _pick_pois_per_day(pois, pc.days, pc, policy, pace)

    itinerary: list[dict] = []
    prev_pos = hotel.name if hotel else ""
    hotel_anchor = prev_pos

    for day_idx in range(pc.days):
        day_num = day_idx + 1
        acts: list[dict] = []
        current_time = "09:00"
        skip_breakfast = False

        if day_idx == 0:
            go = sandbox.select_intercity(
                pc.start_city, pc.target_city, pc.intercity_mode, "06:00",
            )
            if go:
                acts.append(make_intercity_activity(go, pc.people))
                prev_pos = _intercity_end_position(go, pc.target_city)
                current_time = add_minutes(
                    go.get("EndTime") or go.get("end_time") or "10:30", 30,
                )
                skip_breakfast = time_to_minutes(current_time) >= time_to_minutes("10:00")
        else:
            prev_pos = hotel_anchor or prev_pos

        day_acts, prev_pos = build_day_activities(
            day_num, pc.days, poi_by_day[day_idx], hotel, meals, pc, sandbox,
            current_time=current_time,
            prev_position=prev_pos,
            skip_breakfast=skip_breakfast,
        )
        acts.extend(day_acts)

        if day_idx == pc.days - 1:
            last_end = "18:00"
            for act in reversed(day_acts):
                if act.get("end_time"):
                    last_end = act["end_time"]
                    break
            back_time = max_time(last_end, "18:00")
            back = sandbox.select_intercity(
                pc.target_city, pc.start_city, pc.intercity_mode, back_time,
            )
            if back:
                acts.append(make_intercity_activity(back, pc.people, is_return=True))

        itinerary.append({"day": day_num, "activities": acts})

    return {
        "people_number": pc.people,
        "start_city": pc.start_city,
        "target_city": pc.target_city,
        "itinerary": itinerary,
        "_planning_constraints": pc,
    }
