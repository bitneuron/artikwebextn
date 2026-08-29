from app.templates.spec import FilterField, ResultFieldSpec, TemplateSpec

TEMPLATE = TemplateSpec(
    id="college_special_programs",
    name="College Special Programs",
    icon="✨",
    category="education",
    short_description="Find honors colleges, combined degrees, BS/MD tracks, and research scholars programs.",
    example_use_case="Find distinctive honors, research, medical, AI, and interdisciplinary college programs.",
    default_filters=[
        FilterField("colleges", "Colleges to search (blank = broad search)", "text"),
        FilterField("program_types", "Program types of interest", "multiselect", options=[
            "Honors college", "Combined/accelerated degree", "BS/MD or BS/DO", "Dual degree",
            "Undergraduate research scholars", "Summer bridge", "Co-op", "Entrepreneurship incubator",
            "Study abroad", "Fellowship",
        ]),
        FilterField("max_results", "Maximum results per run", "number", placeholder="20"),
        FilterField("min_relevance", "Minimum relevance", "number", placeholder="0.5"),
    ],
    result_categories=["program"],
    result_fields=[
        ResultFieldSpec("college", "College", "text"),
        ResultFieldSpec("why_it_matches", "Why it matches", "text"),
        ResultFieldSpec("eligibility", "Eligibility", "text", tracked_for_changes=True),
        ResultFieldSpec("separate_application", "Separate application required", "badge"),
        ResultFieldSpec("deadline", "Deadline", "date", tracked_for_changes=True),
        ResultFieldSpec("cost_or_stipend", "Cost / scholarship / stipend", "text", tracked_for_changes=True),
        ResultFieldSpec("commitments", "Commitments", "text"),
    ],
    system_prompt_fragment=(
        "Search for honors colleges/programs, scholars programs, living-learning communities, accelerated "
        "or combined bachelor's/master's degrees, BS/MD or BS/DO and pre-medical assurance tracks, dual "
        "degrees, cross-registration, interdisciplinary AI/life-science programs, undergraduate research "
        "scholars programs, first-year research initiatives, co-op/internship programs, entrepreneurship "
        "incubators, study abroad, and institutional fellowships. Report eligibility, whether a separate "
        "application is required, deadlines, and cost/stipend for each."
    ),
    detail_tabs=["overview", "results", "programs", "deadlines", "sources", "run_history", "logs", "settings"],
    default_alert_rules=[
        {"rule_type": "new_results", "channel": "in_app"},
        {"rule_type": "deadline_approaching", "channel": "in_app", "config": {"days_before": 21}},
        {"rule_type": "run_error", "channel": "in_app"},
    ],
)
