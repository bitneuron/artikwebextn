from app.templates.spec import FilterField, ResultFieldSpec, TemplateSpec

TEMPLATE = TemplateSpec(
    id="scholarship_finder",
    name="Scholarship and Financial Aid Finder",
    icon="💰",
    category="education",
    short_description="Find institutional, merit, need-based, and external scholarships and aid.",
    example_use_case="Find scholarships and financial aid matching a student's profile and target schools.",
    default_filters=[
        FilterField("colleges_or_fields", "Colleges or fields of study", "text"),
        FilterField("citizenship_residency", "Citizenship / residency restrictions", "text"),
        FilterField("min_award", "Minimum award amount", "number"),
        FilterField("max_results", "Maximum results per run", "number", placeholder="20"),
    ],
    result_categories=["scholarship"],
    result_fields=[
        ResultFieldSpec("provider", "Provider", "text"),
        ResultFieldSpec("eligibility", "Eligibility", "text", tracked_for_changes=True),
        ResultFieldSpec("award_amount", "Award amount", "currency", tracked_for_changes=True),
        ResultFieldSpec("renewable", "Renewable", "badge"),
        ResultFieldSpec("deadline", "Deadline", "date", tracked_for_changes=True),
        ResultFieldSpec("required_materials", "Required materials", "text"),
        ResultFieldSpec("status", "Status (Apply now/Prepare/Monitor/Needs verification/Closed)", "badge", tracked_for_changes=True),
    ],
    system_prompt_fragment=(
        "Search institutional, merit-based, need-based, departmental, and external scholarships, "
        "fellowships, grants, and research/travel funding. Verify eligibility, deadline, award amount, "
        "renewable status, required materials, and citizenship/residency restrictions. Classify each as "
        "Apply now, Prepare, Monitor, Eligibility needs verification, or Closed or expired."
    ),
    detail_tabs=["overview", "results", "deadlines", "sources", "run_history", "logs", "settings"],
    default_alert_rules=[
        {"rule_type": "new_results", "channel": "in_app"},
        {"rule_type": "deadline_approaching", "channel": "in_app", "config": {"days_before": 14}},
        {"rule_type": "run_error", "channel": "in_app"},
    ],
)
