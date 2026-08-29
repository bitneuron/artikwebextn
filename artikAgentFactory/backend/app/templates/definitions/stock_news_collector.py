from app.templates.spec import FilterField, ResultFieldSpec, TemplateSpec

TEMPLATE = TemplateSpec(
    id="stock_news_collector",
    name="Stock News Collector",
    icon="📈",
    category="finance",
    short_description="Collect and classify news for tracked stock symbols, companies, or industries.",
    example_use_case="Track material news and sentiment for a watchlist of stock symbols.",
    supports_profile=False,
    default_filters=[
        FilterField("symbols", "Stock symbols / companies", "text", required=True),
        FilterField("industries", "Industries", "text"),
        FilterField("excluded_topics", "Excluded topics", "text"),
        FilterField("preferred_publications", "Preferred publications", "text"),
        FilterField("min_relevance", "Minimum relevance", "number", placeholder="0.5"),
        FilterField("max_results", "Maximum results per run", "number", placeholder="20"),
    ],
    result_categories=["article"],
    result_fields=[
        ResultFieldSpec("ticker", "Ticker", "badge"),
        ResultFieldSpec("event_type", "Event type (earnings/guidance/regulatory/M&A/leadership/...)", "badge"),
        ResultFieldSpec("sentiment", "Sentiment", "badge", tracked_for_changes=True),
        ResultFieldSpec("price", "Price at time of report", "currency"),
        ResultFieldSpec("pct_change", "Percent change", "percent"),
    ],
    system_prompt_fragment=(
        "Collect news for the configured symbols/companies/industries. Extract signal: sentiment "
        "(positive/neutral/negative) and material event type — earnings, guidance, regulatory action, "
        "product announcements, leadership changes, partnerships, acquisitions, material risks. Keep the "
        "result shape generic (this shares the same details page as every other template) while populating "
        "stock-specific fields."
    ),
    detail_tabs=["overview", "results", "articles", "sources", "run_history", "logs", "settings"],
    default_alert_rules=[
        {"rule_type": "new_results", "channel": "in_app"},
        {"rule_type": "high_priority_match", "channel": "in_app", "config": {"min_relevance": 0.8}},
        {"rule_type": "run_error", "channel": "in_app"},
    ],
)
