from __future__ import annotations

from pydantic import BaseModel


class FilterFieldOut(BaseModel):
    key: str
    label: str
    type: str
    options: list[str] | None = None
    placeholder: str | None = None
    required: bool = False


class ResultFieldOut(BaseModel):
    key: str
    label: str
    type: str
    tracked_for_changes: bool = False


class TemplateOut(BaseModel):
    id: str
    name: str
    icon: str
    category: str
    short_description: str
    example_use_case: str
    default_filters: list[FilterFieldOut]
    supports_profile: bool
    result_categories: list[str]
    result_fields: list[ResultFieldOut]
    detail_tabs: list[str]
    default_alert_rules: list[dict]
