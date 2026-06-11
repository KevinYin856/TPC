"""Multi-day POI task assignment with policy-aware priorities."""

from __future__ import annotations

from src.data_layer.schema import CandidatePool, Constraints, DayAssignment, POICandidate, Plan
from src.planner.constraint_profile import extract_planning_constraints


def allocate_pois_to_days(
    constraints: Constraints,
    candidates: CandidatePool,
    policy: str = "safe",
) -> Plan:
    """Create a coarse day assignment before rolling-day planning.

    This is a travel-planning migration of task allocation: must-visit nodes are
    locked first, the daily capacity is policy/pace dependent, and budget mode
    prefers lower-cost POIs.
    """
    pc = extract_planning_constraints(constraints)
    pois = [p for p in (candidates.pois or []) if _allowed(p, pc)]
    must = [p for p in pois if _is_must(p, pc)]
    others = [p for p in pois if p not in must]
    if policy == "budget":
        others.sort(key=lambda p: _price(p))
    else:
        others.sort(key=lambda p: -p.score)
    ordered = _dedupe(must + others)

    assignments: list[DayAssignment] = []
    idx = 0
    for day_idx in range(pc.days):
        cap = _capacity(policy, pc, day_idx == pc.days - 1)
        day_ids: list[str] = []
        for _ in range(cap):
            if idx >= len(ordered):
                break
            day_ids.append(ordered[idx].poi_id)
            idx += 1
        assignments.append(DayAssignment(day_index=day_idx, date=f"Day{day_idx + 1}", poi_ids=day_ids))

    return Plan(
        query_id=constraints.query_id,
        policy=policy,
        day_assignments=assignments,
        metadata={"stage": "allocated", "assignment_policy": policy},
    )


def _capacity(policy: str, pc, is_final_day: bool) -> int:
    if pc.max_pois_per_day:
        cap = pc.max_pois_per_day
    elif policy == "safe" or pc.pace == "relaxed":
        cap = 2
    elif policy == "preference" or pc.pace == "intensive":
        cap = 4
    else:
        cap = 3
    if policy == "budget":
        cap = min(cap, 2)
    if is_final_day:
        cap = max(1, cap - 1)
    return max(1, cap)


def _allowed(poi: POICandidate, pc) -> bool:
    name_l = poi.name.lower()
    ptype = str((poi.metadata or {}).get("type", "")).lower()
    if any(f.lower() in name_l for f in pc.forbidden_pois):
        return False
    return not any(f.lower() in ptype or f.lower() in name_l for f in pc.forbidden_attraction_types)


def _is_must(poi: POICandidate, pc) -> bool:
    name_l = poi.name.lower()
    pid_l = poi.poi_id.lower()
    ptype = str((poi.metadata or {}).get("type", "")).lower()
    return any(m.lower() in name_l or m.lower() == pid_l for m in pc.must_visit) or any(
        t.lower() in ptype or t.lower() in name_l for t in pc.must_visit_types
    )


def _price(poi: POICandidate) -> float:
    for key in ("price", "cost"):
        value = (poi.metadata or {}).get(key)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                pass
    return 0.0


def _dedupe(items: list[POICandidate]) -> list[POICandidate]:
    seen: set[str] = set()
    out: list[POICandidate] = []
    for item in items:
        key = item.poi_id or item.name
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out
