from app.templates.spec import FilterField, ResultFieldSpec, TemplateSpec

TEMPLATE = TemplateSpec(
    id="crypto_research",
    name="Bitcoin and Cryptocurrency Research",
    icon="₿",
    category="finance",
    short_description="Research adoption, regulation, and risk evidence for Bitcoin and crypto assets.",
    example_use_case="Research public evidence for and against investing in Bitcoin.",
    default_filters=[
        FilterField("assets", "Assets (e.g. Bitcoin, Ethereum)", "text", required=True),
        FilterField("max_results", "Maximum results per run", "number", placeholder="20"),
    ],
    result_categories=["article"],
    result_fields=[
        ResultFieldSpec("asset", "Asset", "badge"),
        ResultFieldSpec("supporting_argument", "Supporting argument", "text"),
        ResultFieldSpec("opposing_argument", "Opposing argument", "text"),
        ResultFieldSpec("topic", "Topic (adoption/regulation/security/volatility/...)", "badge"),
    ],
    system_prompt_fragment=(
        "Research adoption, network activity, supply, institutional participation, regulation, custody, "
        "security, volatility, liquidity, fees, environmental considerations, and macroeconomic exposure "
        "for the configured assets. Provide evidence both for and against holding/investing. Never issue an "
        "unconditional instruction to buy or sell."
    ),
    detail_tabs=["overview", "results", "articles", "sources", "run_history", "logs", "settings"],
)
