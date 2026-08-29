from app.templates.spec import FilterField, TemplateSpec

TEMPLATE = TemplateSpec(
    id="email_scheduler",
    name="Email Scheduler",
    icon="✉️",
    category="custom",
    short_description="Send a configured email to a recipient on a recurring schedule — no research involved.",
    example_use_case="Send myself a weekly reminder email every Monday morning.",
    kind="action",
    default_filters=[
        FilterField("from_email", "From", "text",
                    placeholder="Sends from the Gmail account configured on the server"),
        FilterField("to_email", "To", "text",
                    placeholder="recipient@example.com (separate multiple with a comma or semicolon)",
                    required=True),
        FilterField("subject", "Subject", "text", placeholder="e.g. Weekly status reminder", required=True),
        FilterField("message", "Message", "textarea", placeholder="Email body (plain text)", required=True),
    ],
    supports_profile=False,
    result_categories=[],
    result_fields=[],
    system_prompt_fragment="",
    detail_tabs=["overview", "run_history", "logs", "settings"],
    default_alert_rules=[{"rule_type": "run_error", "channel": "in_app"}],
)
