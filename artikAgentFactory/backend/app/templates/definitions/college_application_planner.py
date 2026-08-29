from app.templates.spec import FilterField, ResultFieldSpec, TemplateSpec

TEMPLATE = TemplateSpec(
    id="college_application_planner",
    name="College Application Planner",
    icon="📋",
    category="education",
    short_description="Track application platforms, deadlines, essays, and requirements per school.",
    example_use_case="Track application requirements and deadlines for a fixed list of target colleges.",
    default_filters=[
        FilterField("colleges", "Colleges to track", "text", required=True),
        FilterField("application_year", "Application cycle / year", "text", required=True),
        FilterField("intended_major", "Intended major", "text"),
        FilterField("max_results", "Maximum results per run", "number", placeholder="20"),
    ],
    result_categories=["application"],
    result_fields=[
        ResultFieldSpec("platform", "Application platform", "text"),
        ResultFieldSpec("plan", "Application plan (ED/EA/REA/Priority/RD/Rolling)", "badge"),
        ResultFieldSpec("binding", "Binding or nonbinding", "badge"),
        ResultFieldSpec("deadline", "Application deadline", "date", tracked_for_changes=True),
        ResultFieldSpec("fee", "Application fee", "currency", tracked_for_changes=True),
        ResultFieldSpec("essay_prompts", "Essay prompts", "text", tracked_for_changes=True),
        ResultFieldSpec("testing_policy", "Testing policy", "text", tracked_for_changes=True),
        ResultFieldSpec("recommendations", "Recommendation requirements", "text"),
        ResultFieldSpec("status", "Current status", "badge"),
        ResultFieldSpec("next_action", "Next action", "text"),
    ],
    system_prompt_fragment=(
        "Track, per configured college: application platform, opening date, Early Decision/Early Action/"
        "Restrictive Early Action/Priority/Regular Decision/rolling deadlines and whether each is binding, "
        "fees and fee waivers, essay/supplemental prompts, testing policy, transcript and recommendation "
        "requirements, financial-aid forms, scholarship applications, and decision/enrollment-deposit dates. "
        "Use the configured application year; clearly label anything from a previous cycle as historical. "
        "Never fabricate a deadline, prompt, or requirement — mark unverified items explicitly."
    ),
    detail_tabs=["overview", "results", "deadlines", "sources", "run_history", "logs", "settings"],
    default_alert_rules=[
        {"rule_type": "changed_results", "channel": "in_app"},
        {"rule_type": "deadline_approaching", "channel": "in_app", "config": {"days_before": 14}},
        {"rule_type": "run_error", "channel": "in_app"},
    ],
)
