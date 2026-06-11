"""Lightweight local checker before official/schema verification."""

from __future__ import annotations

from src.data_layer.schema import Constraints, Plan
from src.planner.constraint_profile import extract_planning_constraints
from src.planner.plan_utils import time_to_minutes


def run_local_checker(plan: Plan, constraints: Constraints) -> Plan:
    pc = extract_planning_constraints(constraints)
    official = plan.metadata.get("official_plan") or {}
    issues: list[str] = []

    for field in ("people_number", "start_city", "target_city", "itinerary"):
        if field not in official:
            issues.append(f"FORMAT missing {field}")

    present_attractions: set[str] = set()
    for day in official.get("itinerary", []):
        day_acts = day.get("activities", [])
        meal_types = {a.get("type") for a in day_acts if a.get("type") in {"breakfast", "lunch", "dinner"}}
        if "lunch" not in meal_types:
            issues.append(f"MEAL day={day.get('day')} missing lunch")
        if "dinner" not in meal_types:
            issues.append(f"MEAL day={day.get('day')} missing dinner")

        last_end = -1
        for act in day_acts:
            atype = act.get("type", "")
            for req in ("type", "start_time", "end_time", "cost", "price", "transports"):
                if req not in act:
                    issues.append(f"FORMAT activity missing {req}")
            try:
                start = time_to_minutes(act.get("start_time", "00:00"))
                end = time_to_minutes(act.get("end_time", "00:00"))
                if end <= start or start < last_end:
                    issues.append(f"TIME conflict day={day.get('day')} type={atype}")
                last_end = max(last_end, end)
            except Exception:
                issues.append(f"TIME invalid day={day.get('day')} type={atype}")

            if atype == "attraction":
                present_attractions.add(str(act.get("position", "")).lower())
            if atype in ("attraction", "airplane", "train") and act.get("tickets") != pc.activity_tickets:
                issues.append(f"TICKET {atype} tickets={act.get('tickets')} expected={pc.activity_tickets}")
            for seg in act.get("transports") or []:
                mode = seg.get("mode", "")
                if mode == "metro" and seg.get("tickets") != pc.metro_tickets:
                    issues.append(f"TRANSPORT metro tickets={seg.get('tickets')} expected={pc.metro_tickets}")
                if mode == "taxi" and seg.get("cars") != pc.taxi_cars:
                    issues.append(f"TRANSPORT taxi cars={seg.get('cars')} expected={pc.taxi_cars}")

    for name in pc.must_visit:
        if not any(name.lower() in p for p in present_attractions):
            issues.append(f"MUST_VISIT missing {name}")

    budget = plan.metadata.get("budget_report") or {}
    if budget.get("over_total") or budget.get("over_dining") or budget.get("over_accommodation"):
        issues.append(f"BUDGET {budget}")

    plan.metadata["local_check_issues"] = issues
    return plan
