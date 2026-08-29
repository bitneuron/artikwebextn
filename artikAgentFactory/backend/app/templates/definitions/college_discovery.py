from app.templates.spec import FilterField, ResultFieldSpec, TemplateSpec

TEMPLATE = TemplateSpec(
    id="college_discovery",
    name="College Discovery",
    icon="🎓",
    category="education",
    short_description="Find colleges that match a student's academic and personal profile.",
    example_use_case="Find colleges that are a strong match for a student interested in AI and computational biology.",
    default_filters=[
        FilterField("required_keywords", "Required keywords", "text"),
        FilterField("excluded_keywords", "Excluded keywords", "text"),
        FilterField("preferred_locations", "Preferred locations/regions", "text"),
        FilterField("budget", "Budget / total cost ceiling", "number"),
        FilterField("preferred_sources", "Preferred sources", "text"),
        FilterField("excluded_sources", "Excluded sources", "text"),
        FilterField("max_results", "Maximum results per run", "number", placeholder="20"),
        FilterField("min_relevance", "Minimum relevance", "number", placeholder="0.5"),
    ],
    result_categories=["school"],
    result_fields=[
        ResultFieldSpec("department", "Relevant school/department", "text"),
        ResultFieldSpec("suggested_major", "Suggested major", "text"),
        ResultFieldSpec("why_it_matches", "Why it matches", "text"),
        ResultFieldSpec("admission_competitiveness", "Admission competitiveness", "badge"),
        ResultFieldSpec("planning_category", "Planning category (Likely/Target/Reach/High Reach)", "badge"),
        ResultFieldSpec("estimated_cost", "Estimated cost", "currency", tracked_for_changes=True),
        ResultFieldSpec("application_deadline", "Application deadline", "date", tracked_for_changes=True),
        ResultFieldSpec("undergrad_research", "Undergraduate research availability", "text"),
        ResultFieldSpec("special_programs", "Special programs", "text"),
        ResultFieldSpec("drawbacks", "Potential drawbacks", "text"),
    ],
    system_prompt_fragment=(
        "Research colleges against the configured student profile: academic fit, majors/minors/"
        "interdisciplinary programs, curriculum flexibility, relevant professors/labs/research centers, "
        "undergraduate research availability, class sizes and advising, honors/combined-degree programs, "
        "campus setting, student organizations, career services and outcomes, tuition and financial aid. "
        "When evidence supports it, classify each college as Likely, Target, Reach, or High Reach — these "
        "are planning categories, never admission guarantees or probabilities. Note real advantages and "
        "drawbacks for the specific student profile, not generic praise."
    ),
    detail_tabs=["overview", "results", "schools", "deadlines", "sources", "run_history", "logs", "settings"],
    default_alert_rules=[
        {"rule_type": "new_results", "channel": "in_app"},
        {"rule_type": "deadline_approaching", "channel": "in_app", "config": {"days_before": 30}},
        {"rule_type": "run_error", "channel": "in_app"},
    ],
)
