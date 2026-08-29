from app.templates.spec import FilterField, ResultFieldSpec, TemplateSpec

TEMPLATE = TemplateSpec(
    id="student_research_finder",
    name="Student Research Opportunity Finder",
    icon="🔬",
    category="education",
    short_description="Find REUs, research assistantships, summer programs, and lab volunteering.",
    example_use_case="Find currently open research opportunities matching a student's interests.",
    default_filters=[
        FilterField("interests", "Interests (e.g. AI, biology, drug discovery)", "text", required=True),
        FilterField("education_level", "Education level", "select", options=[
            "High school", "Undergraduate", "Graduate",
        ]),
        FilterField("remote_ok", "Remote acceptable", "boolean"),
        FilterField("max_results", "Maximum results per run", "number", placeholder="20"),
    ],
    result_categories=["opportunity"],
    result_fields=[
        ResultFieldSpec("program_type", "Program type", "text"),
        ResultFieldSpec("location", "Location", "text"),
        ResultFieldSpec("remote", "Remote availability", "badge"),
        ResultFieldSpec("deadline", "Deadline", "date", tracked_for_changes=True),
        ResultFieldSpec("program_dates", "Program dates", "text", tracked_for_changes=True),
        ResultFieldSpec("compensation", "Compensation / stipend", "currency", tracked_for_changes=True),
        ResultFieldSpec("prerequisites", "Prerequisites", "text"),
        ResultFieldSpec("status", "Status (Apply now/Prepare/Monitor/Needs verification/Closed)", "badge", tracked_for_changes=True),
    ],
    system_prompt_fragment=(
        "Search for high-school and undergraduate research programs, Research Experiences for "
        "Undergraduates (REUs), research assistant positions, summer research programs, laboratory "
        "volunteering, professor-led projects, science competitions, and remote research/mentorship "
        "programs matching the configured interests. Verify application status, deadline, program dates, "
        "location, education-level and citizenship requirements, and compensation. Classify each as Apply "
        "now, Prepare for upcoming deadline, Monitor for next cycle, Eligibility needs verification, or "
        "Closed or expired — never describe an old listing as currently open without verification."
    ),
    detail_tabs=["overview", "results", "opportunities", "deadlines", "sources", "run_history", "logs", "settings"],
    default_alert_rules=[
        {"rule_type": "new_results", "channel": "in_app"},
        {"rule_type": "deadline_approaching", "channel": "in_app", "config": {"days_before": 14}},
        {"rule_type": "run_error", "channel": "in_app"},
    ],
)
