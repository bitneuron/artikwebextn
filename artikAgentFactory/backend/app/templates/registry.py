from __future__ import annotations

from app.templates.definitions import (
    ai_drug_discovery,
    college_application_planner,
    college_discovery,
    college_special_programs,
    crypto_research,
    custom_agent,
    deal_finder,
    email_scheduler,
    general_research,
    home_finder,
    investment_research,
    professor_lab_finder,
    scholarship_finder,
    stock_news_collector,
    student_research_finder,
)
from app.templates.spec import TemplateSpec

_ALL = (
    college_discovery.TEMPLATE, college_application_planner.TEMPLATE,
    college_special_programs.TEMPLATE, scholarship_finder.TEMPLATE,
    student_research_finder.TEMPLATE, professor_lab_finder.TEMPLATE,
    ai_drug_discovery.TEMPLATE, stock_news_collector.TEMPLATE,
    investment_research.TEMPLATE, crypto_research.TEMPLATE, home_finder.TEMPLATE,
    deal_finder.TEMPLATE, general_research.TEMPLATE, custom_agent.TEMPLATE,
    email_scheduler.TEMPLATE,
)

TEMPLATES: dict[str, TemplateSpec] = {t.id: t for t in _ALL}


def get_template(template_id: str) -> TemplateSpec | None:
    return TEMPLATES.get(template_id)


def list_templates() -> list[TemplateSpec]:
    return list(TEMPLATES.values())
