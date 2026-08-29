"""Deterministic string composition — no LLM call here, keeps cost/latency down."""
from __future__ import annotations

_HINT_KEYS = (
    "required_keywords", "symbols", "industries", "interests", "assets",
    "product_or_service", "subject", "location", "colleges", "colleges_or_fields",
    "research_interests", "focus_areas", "diseases_or_targets",
)


def build_queries(objective: str, filters: dict, profile: dict | None, max_queries: int) -> list[str]:
    objective = (objective or "").strip()
    base_parts = [objective] if objective else []
    for key in _HINT_KEYS:
        v = filters.get(key)
        if v:
            base_parts.append(str(v))
    excluded = filters.get("excluded_keywords") or filters.get("excluded_topics") or filters.get("exclusions")
    base = " ".join(base_parts) or "general research"
    if excluded:
        base += f" -{excluded}"

    queries = [base]
    if profile:
        personal = profile.get("academic_interests") or profile.get("research_interests") or profile.get("intended_majors")
        if personal:
            queries.append(f"{objective} {personal}".strip())
    if filters.get("preferred_locations"):
        queries.append(f"{objective} {filters['preferred_locations']}".strip())

    seen: list[str] = []
    for q in queries:
        q = q.strip()
        if q and q not in seen:
            seen.append(q)
    return seen[:max_queries] if seen else [objective or "general research"]
