from app.templates.spec import FilterField, TemplateSpec

TEMPLATE = TemplateSpec(
    id="custom_agent",
    name="Custom Agent",
    icon="🧩",
    category="custom",
    short_description="Fully open-ended agent — describe exactly what to research in your own words.",
    example_use_case="Any research objective not covered by the other templates.",
    default_filters=[
        FilterField("required_keywords", "Required keywords", "text"),
        FilterField("excluded_keywords", "Excluded keywords", "text"),
        FilterField("preferred_sources", "Preferred sources", "text"),
        FilterField("excluded_sources", "Excluded sources", "text"),
        FilterField("required_result_fields", "Required result fields", "text"),
        FilterField("user_urls", "Your own reference URLs", "url_list"),
        FilterField("user_notes", "Notes / context", "textarea"),
        FilterField("max_results", "Maximum results per run", "number", placeholder="20"),
    ],
    supports_profile=True,
    result_categories=["general"],
    result_fields=[],
    system_prompt_fragment=(
        "This is a fully custom research objective supplied by the user. Follow it literally, infer "
        "reasonable result fields from the objective and any 'required result fields' filter, and apply "
        "every shared research-agent rule (source citation, credibility, dedup, change detection, no "
        "fabrication)."
    ),
    detail_tabs=["overview", "results", "sources", "run_history", "logs", "settings"],
)
