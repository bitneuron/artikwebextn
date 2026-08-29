from app.templates.spec import FilterField, ResultFieldSpec, TemplateSpec

TEMPLATE = TemplateSpec(
    id="investment_research",
    name="Investment Research",
    icon="📊",
    category="finance",
    short_description="Research upside/downside evidence for a security, sector, or strategy.",
    example_use_case="Research public evidence for and against an investment thesis.",
    supports_profile=True,
    default_filters=[
        FilterField("subject", "Security / sector / strategy", "text", required=True),
        FilterField("time_horizon", "Time horizon", "select", options=["Short-term", "Medium-term", "Long-term"]),
        FilterField("risk_tolerance", "Risk tolerance", "select", options=["Low", "Medium", "High"]),
        FilterField("max_results", "Maximum results per run", "number", placeholder="20"),
    ],
    result_categories=["article"],
    result_fields=[
        ResultFieldSpec("recommendation", "Recommendation (Strong match/Consider/Monitor/High risk/Avoid/Insufficient evidence)", "badge", tracked_for_changes=True),
        ResultFieldSpec("supporting_evidence", "Supporting evidence", "text"),
        ResultFieldSpec("opposing_evidence", "Opposing evidence", "text"),
        ResultFieldSpec("evidence_type", "Evidence type (fact/opinion/forecast/assumption/speculation)", "badge"),
        ResultFieldSpec("price_or_valuation", "Price / valuation", "currency", tracked_for_changes=True),
    ],
    system_prompt_fragment=(
        "Research potential upside, downside risk, volatility, liquidity, fees, valuation, financial "
        "condition, competition, and regulation for the configured subject. Clearly distinguish verified "
        "facts from analyst opinions, forecasts, assumptions, and speculation. Never guarantee returns — "
        "present findings as research, not personalized financial advice. Use only: Strong match, Consider, "
        "Worth monitoring, High risk, Avoid for now, or Insufficient evidence."
    ),
    detail_tabs=["overview", "results", "articles", "sources", "run_history", "logs", "settings"],
    default_alert_rules=[
        {"rule_type": "new_results", "channel": "in_app"},
        {"rule_type": "changed_results", "channel": "in_app"},
        {"rule_type": "run_error", "channel": "in_app"},
    ],
)
