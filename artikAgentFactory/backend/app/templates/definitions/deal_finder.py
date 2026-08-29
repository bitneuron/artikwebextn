from app.templates.spec import FilterField, ResultFieldSpec, TemplateSpec

TEMPLATE = TemplateSpec(
    id="deal_finder",
    name="Deal Finder",
    icon="🏷️",
    category="lifestyle",
    short_description="Find genuine discounts on products, services, travel, and subscriptions.",
    example_use_case="Find genuine deals matching selected product/service preferences.",
    supports_profile=False,
    default_filters=[
        FilterField("product_or_service", "Product or service", "text", required=True),
        FilterField("category", "Category", "select", options=[
            "Retail", "Travel", "Services", "Subscriptions", "Events", "Real estate", "Other",
        ]),
        FilterField("budget_max", "Budget (max)", "number"),
        FilterField("required_features", "Required features", "text"),
        FilterField("exclusions", "Exclusions", "text"),
        FilterField("max_results", "Maximum results per run", "number", placeholder="20"),
    ],
    result_categories=["listing"],
    result_fields=[
        ResultFieldSpec("current_price", "Current price", "currency", tracked_for_changes=True),
        ResultFieldSpec("typical_price", "Typical price", "currency"),
        ResultFieldSpec("claimed_discount", "Claimed discount", "percent", tracked_for_changes=True),
        ResultFieldSpec("expiration", "Expiration", "date", tracked_for_changes=True),
        ResultFieldSpec("eligibility_restrictions", "Eligibility restrictions", "text"),
        ResultFieldSpec("seller_reputation", "Seller reputation", "text"),
    ],
    system_prompt_fragment=(
        "Research current price, typical price, previous price, claimed discount, expiration, eligibility "
        "restrictions, shipping/fees, seller reputation, return policy, and coupon/membership requirements "
        "for the configured product or service. Distinguish genuine discounts from marketing claims. Design "
        "for future extension across retail/travel/services/subscriptions/events/real-estate categories "
        "without requiring new tables."
    ),
    detail_tabs=["overview", "results", "sources", "run_history", "logs", "settings"],
    default_alert_rules=[
        {"rule_type": "new_results", "channel": "in_app"},
        {"rule_type": "changed_results", "channel": "in_app"},
        {"rule_type": "run_error", "channel": "in_app"},
    ],
)
