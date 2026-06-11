"""Budget and resource control for generated plans."""

from __future__ import annotations

from typing import Any

from src.data_layer.schema import Constraints, Plan, POICandidate
from src.planner.constraint_profile import extract_planning_constraints


def control_budget(plan: Plan, constraints: Constraints) -> Plan:
    """Actively reduce cost instead of only marking budget violations."""
    official = plan.metadata.get("official_plan") or {}
    if not official:
        return plan

    pc = extract_planning_constraints(constraints)
    candidates = plan.metadata.get("candidates")
    cheap_restaurants = sorted(getattr(candidates, "restaurants", []) or [], key=_candidate_price)
    cheap_hotels = sorted(getattr(candidates, "hotels", []) or [], key=_candidate_price)

    if pc.dining_budget is not None:
        _replace_meals(official, cheap_restaurants, pc.people, pc.dining_budget)
    if pc.accommodation_budget is not None:
        _replace_hotels(official, cheap_hotels, pc.people, pc.days, pc.accommodation_budget)

    if pc.total_budget is not None:
        _prefer_low_cost_transports(official)
        _trim_optional_attractions(official, pc, pc.total_budget)

    total = _plan_total_cost(official)
    plan.total_cost = total
    plan.metadata["official_plan"] = official
    plan.metadata["budget_report"] = {
        "total_cost": total,
        "total_budget": pc.total_budget,
        "dining_cost": _typed_cost(official, {"breakfast", "lunch", "dinner"}),
        "dining_budget": pc.dining_budget,
        "accommodation_cost": _typed_cost(official, {"accommodation"}),
        "accommodation_budget": pc.accommodation_budget,
        "over_total": pc.total_budget is not None and total > pc.total_budget + 0.1,
        "over_dining": pc.dining_budget is not None and _typed_cost(official, {"breakfast", "lunch", "dinner"}) > pc.dining_budget + 0.1,
        "over_accommodation": pc.accommodation_budget is not None and _typed_cost(official, {"accommodation"}) > pc.accommodation_budget + 0.1,
    }
    return plan


def _replace_meals(plan_dict: dict[str, Any], restaurants: list[POICandidate], people: int, budget: float) -> None:
    if not restaurants:
        return
    meals = _meal_activities(plan_dict)
    if not meals:
        return
    cap = budget / max(1, len(meals) * people)
    affordable = [r for r in restaurants if _candidate_price(r) <= cap] or restaurants[:3]
    for idx, act in enumerate(meals):
        if float(act.get("price", 0)) <= cap:
            continue
        rest = affordable[idx % len(affordable)]
        price = _candidate_price(rest)
        act["position"] = rest.name
        act["price"] = round(price, 2)
        act["cost"] = round(price * people, 2)


def _replace_hotels(plan_dict: dict[str, Any], hotels: list[POICandidate], people: int, days: int, budget: float) -> None:
    if not hotels:
        return
    rooms = max(1, (people + 1) // 2)
    nights = max(1, days - 1)
    affordable = [h for h in hotels if _candidate_price(h) * rooms * nights <= budget] or hotels[:1]
    hotel = affordable[0]
    price = _candidate_price(hotel)
    for act in _activities(plan_dict):
        if act.get("type") == "accommodation":
            act["position"] = hotel.name
            act["rooms"] = rooms
            act["price"] = round(price, 2)
            act["cost"] = round(price * rooms, 2)


def _prefer_low_cost_transports(plan_dict: dict[str, Any]) -> None:
    people = int(plan_dict.get("people_number", 1))
    for act in _activities(plan_dict):
        for seg in act.get("transports") or []:
            if seg.get("mode") == "taxi":
                seg["mode"] = "metro"
                seg["price"] = min(float(seg.get("price", 0)), 5.0)
                seg["cost"] = min(float(seg.get("cost", 0)), 5.0 * max(1, int(seg.get("tickets", 1))))
                seg.pop("cars", None)
                seg.setdefault("tickets", int(plan_dict.get("people_number", 1)))
        if act.get("type") in {"breakfast", "lunch", "dinner"}:
            act["cost"] = round(float(act.get("price", 0)) * people, 2)
        elif act.get("type") == "attraction":
            act["cost"] = round(float(act.get("price", 0)) * _activity_units(act), 2)


def _trim_optional_attractions(plan_dict: dict[str, Any], pc, budget: float) -> None:
    must_names = {m.lower() for m in pc.must_visit}
    while _plan_total_cost(plan_dict) > budget + 0.1:
        removed = False
        for day in reversed(plan_dict.get("itinerary", [])):
            activities = day.get("activities", [])
            for idx in range(len(activities) - 1, -1, -1):
                act = activities[idx]
                if act.get("type") != "attraction":
                    continue
                name = str(act.get("position", "")).lower()
                if any(m in name for m in must_names):
                    continue
                activities.pop(idx)
                removed = True
                break
            if removed:
                break
        if not removed:
            break


def _activity_units(act: dict[str, Any]) -> int:
    if act.get("type") in {"breakfast", "lunch", "dinner"}:
        return 1
    return int(act.get("tickets") or 1)


def _candidate_price(item: POICandidate) -> float:
    for key in ("price", "cost", "avg_price"):
        value = (item.metadata or {}).get(key)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                pass
    return 50.0


def _activities(plan_dict: dict[str, Any]) -> list[dict[str, Any]]:
    return [act for day in plan_dict.get("itinerary", []) for act in day.get("activities", [])]


def _meal_activities(plan_dict: dict[str, Any]) -> list[dict[str, Any]]:
    return [a for a in _activities(plan_dict) if a.get("type") in {"breakfast", "lunch", "dinner"}]


def _typed_cost(plan_dict: dict[str, Any], types: set[str]) -> float:
    return round(sum(float(a.get("cost", 0)) for a in _activities(plan_dict) if a.get("type") in types), 2)


def _plan_total_cost(plan_dict: dict[str, Any]) -> float:
    total = 0.0
    for act in _activities(plan_dict):
        total += float(act.get("cost", 0))
        for seg in act.get("transports") or []:
            total += float(seg.get("cost", 0))
    return round(total, 2)
