from app.templates.spec import FilterField, TemplateSpec

TEMPLATE = TemplateSpec(
    id="general_research",
    name="General Research",
    icon="🔎",
    category="custom",
    short_description="Monitor any legitimate research topic and report important findings/changes.",
    example_use_case="Monitor any custom topic and report important changes.",
    default_filters=[
        FilterField("required_keywords", "Required keywords", "text"),
        FilterField("excluded_keywords", "Excluded keywords", "text"),
        FilterField("preferred_sources", "Preferred sources", "text"),
        FilterField("excluded_sources", "Excluded sources", "text"),
        FilterField("user_urls", "Your own reference URLs", "url_list"),
        FilterField("user_notes", "Notes / context", "textarea"),
        FilterField("max_results", "Maximum results per run", "number", placeholder="20"),
    ],
    result_categories=["general"],
    result_fields=[],
    system_prompt_fragment=(
        "Interpret the configured objective, identify the result fields that matter for this specific "
        "topic, build a search plan, evaluate evidence, and produce a structured, cited answer. Treat any "
        "user-provided URLs or articles as additional evidence to consider, not automatically verified fact."
    ),
    detail_tabs=["overview", "results", "sources", "run_history", "logs", "settings"],
)
