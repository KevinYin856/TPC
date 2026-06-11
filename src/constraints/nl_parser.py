"""Offline natural-language constraint extraction.

The competition mode cannot rely on external APIs or oracle hard_logic_py, so this
module uses a local dictionary/rule parser.  It intentionally extracts explicit
constraints from common ChinaTravel query phrasings and leaves ambiguous items as
soft preferences where possible.
"""

from __future__ import annotations

import re

from src.constraints.constraint_card import build_constraint_card
from src.data_layer.schema import ConstraintCard


AMOUNT_RE = r"([0-9]+(?:\.[0-9]+)?)"

ATTRACTION_TYPE_TERMS = {
    "park",
    "museum",
    "museum/memorial hall",
    "memorial hall",
    "red tourism sites",
    "natural scenery",
    "amusement park",
    "historical site",
    "cultural site",
    "temple",
    "zoo",
    "aquarium",
}

CUISINE_TERMS = {
    "local": "local",
    "local food": "local",
    "local cuisine": "local",
    "sichuan": "Sichuan cuisine",
    "hotpot": "hotpot",
    "tea house": "Teahouse",
    "teahouse": "Teahouse",
}


def parse_nature_language(text: str, start_index: int = 0) -> list[ConstraintCard]:
    """Extract constraint cards from natural-language query text."""
    if not text or not text.strip():
        return []

    cards: list[ConstraintCard] = []
    idx = start_index
    lowered = text.lower()

    def add_card(**kwargs) -> None:
        nonlocal idx
        kwargs.setdefault("card_id", f"nl_{idx}")
        cards.append(build_constraint_card(**kwargs))
        idx += 1

    # Pace as energy/time budget.
    if _contains_any(
        lowered,
        "not too tired",
        "not tired",
        "relaxed",
        "easy pace",
        "light schedule",
        "do not rush",
        "don't rush",
        "不要太累",
        "轻松",
    ):
        add_card(
            category="preference",
            description="Relaxed pace: fewer POIs, less travel, more buffer time",
            parameters={"pace": "relaxed", "max_pois_per_day": 2, "buffer_minutes": 30},
            is_hard=False,
            source="nature_language",
            priority=2,
        )

    if _contains_any(
        lowered,
        "as many as possible",
        "packed",
        "intensive",
        "tight schedule",
        "尽量多",
        "紧凑",
    ):
        add_card(
            category="preference",
            description="Intensive pace: visit more POIs per day when feasible",
            parameters={"pace": "intensive", "max_pois_per_day": 4, "buffer_minutes": 10},
            is_hard=False,
            source="nature_language",
            priority=2,
        )

    # Budget constraints.
    budget_patterns = [
        (rf"(?:dining|food|meal|restaurant)\s+budget\s*(?:is|below|under|<=|less than|no more than|:)?\s*{AMOUNT_RE}", "dining", "Dining budget"),
        (rf"budget\s+for\s+(?:dining|food|meal|restaurant)s?\s*(?:is|below|under|<=|less than|no more than|:)?\s*{AMOUNT_RE}", "dining", "Dining budget"),
        (rf"(?:accommodation|hotel|lodging)\s+budget\s*(?:is|below|under|<=|less than|no more than|:)?\s*{AMOUNT_RE}", "accommodation", "Accommodation budget"),
        (rf"(?:total|overall|travel)\s+budget\s*(?:is|below|under|<=|less than|no more than|:)?\s*{AMOUNT_RE}", "total", "Total budget"),
        (rf"预算[:：\s]*(?:不超过|低于|小于)?\s*{AMOUNT_RE}", "total", "Total budget"),
    ]
    for pattern, budget_type, label in budget_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            amount = float(match.group(1))
            add_card(
                category="budget",
                description=f"{label} <= {amount}",
                parameters={"budget_type": budget_type, "max_cost": amount},
                is_hard=True,
                source="nature_language",
                priority=4,
            )

    # Hotel/accommodation spatial anchor.
    hotel_distance_patterns = [
        rf"(?:accommodation|hotel|lodging)\s+(?:should\s+be\s+)?(?:within|less than|no more than|under)\s*{AMOUNT_RE}\s*(?:km|kilometers?)\s*(?:of|from|near)\s+([^.;,]+)",
        rf"(?:stay|hotel|accommodation)\s+(?:near|close to)\s+([^.;,]+)\s+(?:within|under|less than)\s*{AMOUNT_RE}\s*(?:km|kilometers?)",
    ]
    for pattern in hotel_distance_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            if len(match.groups()) == 2 and _is_number(match.group(1)):
                dist, anchor = float(match.group(1)), match.group(2).strip()
            else:
                anchor, dist = match.group(1).strip(), float(match.group(2))
            add_card(
                category="spatial",
                description=f"Accommodation within {dist} km of {anchor}",
                parameters={
                    "target": "accommodation",
                    "anchor_poi": _clean_entity(anchor),
                    "max_distance_km": dist,
                },
                is_hard=True,
                source="nature_language",
                priority=5,
            )

    # Required hotel features.
    if _contains_any(lowered, "free parking", "with parking", "parking hotel"):
        add_card(
            category="accommodation",
            description="Accommodation must include free parking",
            parameters={"required_type": "Free parking"},
            is_hard=True,
            source="nature_language",
            priority=4,
        )

    # Forbidden attractions/types before positive extraction.
    for phrase in _extract_forbidden_visit_phrases(text):
        _add_attraction_phrase_card(add_card, phrase, forbidden=True)

    # Positive must-visit or type requirements.
    for phrase in _extract_positive_visit_phrases(text):
        if _phrase_was_forbidden(text, phrase):
            continue
        _add_attraction_phrase_card(add_card, phrase, forbidden=False)

    # Cuisine and restaurant preferences.
    for term, canonical in CUISINE_TERMS.items():
        if term in lowered:
            add_card(
                category="dietary",
                description=f"Restaurant/cuisine preference: {canonical}",
                parameters={"cuisine_preference": canonical},
                is_hard=False,
                source="nature_language",
                priority=2,
            )

    # Transport requirements/preferences.
    if re.search(r"\b(by|take|use)\s+(train|rail)\b", lowered):
        add_card(
            category="transport",
            description="Intercity transport should use train",
            parameters={"intercity_mode": "train"},
            is_hard=True,
            source="nature_language",
            priority=4,
        )
    if re.search(r"\b(by|take|use)\s+(airplane|plane|flight)\b", lowered):
        add_card(
            category="transport",
            description="Intercity transport should use airplane",
            parameters={"intercity_mode": "airplane"},
            is_hard=True,
            source="nature_language",
            priority=4,
        )
    if "metro" in lowered or "subway" in lowered:
        add_card(
            category="transport",
            description="Prefer metro for inner-city transport",
            parameters={"innercity_mode": "metro"},
            is_hard=False,
            source="nature_language",
            priority=2,
        )
    if "taxi" in lowered:
        add_card(
            category="transport",
            description="Prefer taxi for inner-city transport",
            parameters={"innercity_mode": "taxi"},
            is_hard=False,
            source="nature_language",
            priority=2,
        )

    return cards


def _contains_any(text: str, *keywords: str) -> bool:
    return any(k.lower() in text for k in keywords)


def _is_number(value: str) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def _clean_entity(value: str) -> str:
    value = re.sub(r"\b(?:and|with|during|for)\b.*$", "", value.strip(), flags=re.IGNORECASE)
    return value.strip(" ,.;:，。；：")


def _looks_like_type(phrase: str) -> bool:
    p = phrase.lower().strip()
    if p in ATTRACTION_TYPE_TERMS:
        return True
    return any(term in p for term in ("museum", "memorial", "park", "tourism", "scenery", "temple", "site"))


def _split_visit_phrase(phrase: str) -> list[str]:
    phrase = _clean_entity(phrase)
    phrase = re.sub(r"^(?:the|a|an)\s+", "", phrase, flags=re.IGNORECASE)
    parts = re.split(r"\s+(?:and|or)\s+|[,，；;]\s*", phrase)
    return [_clean_entity(p) for p in parts if len(_clean_entity(p)) >= 2]


def _extract_forbidden_visit_phrases(text: str) -> list[str]:
    patterns = [
        r"(?:do\s+not|don't|do\s+not\s+wish\s+to|do\s+not\s+want\s+to|not\s+to)\s+visit\s+([^.;]+)",
        r"(?:avoid|exclude|without)\s+([^.;]+)",
        r"不(?:想|要|希望)?去\s*([^。；;,.，]+)",
    ]
    phrases: list[str] = []
    for pattern in patterns:
        phrases.extend(m.group(1).strip() for m in re.finditer(pattern, text, re.IGNORECASE))
    return phrases


def _extract_positive_visit_phrases(text: str) -> list[str]:
    patterns = [
        r"(?:must|need|want|would\s+like|wish|hope|plan)\s+to\s+visit\s+([^.;]+)",
        r"(?:we\s+want\s+to\s+visit|requirements:\s*visit)\s+([^.;]+)",
        r"(?:必须|一定|想|希望)去\s*([^。；;,.，]+)",
    ]
    phrases: list[str] = []
    for pattern in patterns:
        phrases.extend(m.group(1).strip() for m in re.finditer(pattern, text, re.IGNORECASE))
    return phrases


def _phrase_was_forbidden(text: str, phrase: str) -> bool:
    phrase_l = phrase.lower()
    text_l = text.lower()
    idx = text_l.find(phrase_l)
    if idx < 0:
        return False
    prefix = text_l[max(0, idx - 32):idx]
    return any(token in prefix for token in ("do not", "don't", "not ", "avoid", "exclude", "不想", "不要"))


def _add_attraction_phrase_card(add_card, phrase: str, *, forbidden: bool) -> None:
    for item in _split_visit_phrase(phrase):
        if _looks_like_type(item):
            param = "forbidden_attraction_type" if forbidden else "must_visit_type"
            add_card(
                category="attraction",
                description=("Forbidden" if forbidden else "Required") + f" attraction type: {item}",
                parameters={param: item},
                is_hard=True,
                source="nature_language",
                priority=5 if not forbidden else 4,
            )
        else:
            param = "forbidden_poi" if forbidden else "must_visit_poi"
            add_card(
                category="attraction",
                description=("Forbidden" if forbidden else "Must visit") + f" attraction: {item}",
                parameters={param: item},
                is_hard=True,
                source="nature_language",
                priority=5 if not forbidden else 4,
            )
