"""Template specs are pure backend config, not database rows. Adding template #15
means adding one definitions/*.py file and one registry.py entry — zero migration,
zero scheduler change, zero new routes. See registry.py for the loaded dict."""
from __future__ import annotations

from dataclasses import dataclass, field

# The full set of detail-page tabs a template may opt into. Overview/Results/Sources/
# Run History/Logs/Settings are conventionally present for every template; the rest
# are template-specific pre-filtered views of `results` by category.
ALL_TABS = (
    "overview", "results", "schools", "programs", "opportunities", "articles",
    "sources", "deadlines", "run_history", "logs", "settings",
)


@dataclass(frozen=True)
class FilterField:
    key: str
    label: str
    type: str  # text|select|multiselect|number|date_range|boolean|url_list|textarea
    options: list[str] | None = None
    placeholder: str | None = None
    required: bool = False


@dataclass(frozen=True)
class ResultFieldSpec:
    key: str
    label: str
    type: str  # text|date|currency|percent|url|badge|number
    tracked_for_changes: bool = False


@dataclass(frozen=True)
class TemplateSpec:
    id: str
    name: str
    icon: str
    category: str  # education|finance|science|lifestyle|custom
    short_description: str
    example_use_case: str
    # research (default): objective -> web search -> extract -> dedup -> persist as
    # Results, run_service.execute_run's normal pipeline. action: no web search or
    # Results at all — the run itself performs a one-off side effect (e.g. sending an
    # email); see run_service._execute_action_run and templates/definitions/email_scheduler.py.
    kind: str = "research"
    default_filters: list[FilterField] = field(default_factory=list)
    supports_profile: bool = True
    result_categories: list[str] = field(default_factory=lambda: ["general"])
    result_fields: list[ResultFieldSpec] = field(default_factory=list)
    system_prompt_fragment: str = ""
    detail_tabs: list[str] = field(default_factory=lambda: [
        "overview", "results", "sources", "run_history", "logs", "settings",
    ])
    default_alert_rules: list[dict] = field(default_factory=lambda: [
        {"rule_type": "new_results", "channel": "in_app"},
        {"rule_type": "run_error", "channel": "in_app"},
    ])
