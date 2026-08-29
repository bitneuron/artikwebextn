from app.templates.spec import FilterField, ResultFieldSpec, TemplateSpec

TEMPLATE = TemplateSpec(
    id="home_finder",
    name="Home Finder",
    icon="🏠",
    category="lifestyle",
    short_description="Find homes for sale or rent within a location, budget, and feature set.",
    example_use_case="Find homes within a selected distance and budget with required features.",
    default_filters=[
        FilterField("location", "Target location", "text", required=True),
        FilterField("radius_miles", "Search radius (miles)", "number"),
        FilterField("purchase_or_rental", "Purchase or rental", "select", options=["Purchase", "Rental"]),
        FilterField("budget_max", "Budget (max)", "number", required=True),
        FilterField("property_type", "Property type", "text"),
        FilterField("bedrooms_min", "Minimum bedrooms", "number"),
        FilterField("bathrooms_min", "Minimum bathrooms", "number"),
        FilterField("required_features", "Required features", "text"),
        FilterField("exclusions", "Exclusions / deal-breakers", "text"),
        FilterField("max_results", "Maximum results per run", "number", placeholder="20"),
    ],
    supports_profile=False,
    result_categories=["listing"],
    result_fields=[
        ResultFieldSpec("price", "Price", "currency", tracked_for_changes=True),
        ResultFieldSpec("property_type", "Property type", "badge"),
        ResultFieldSpec("bedrooms", "Bedrooms", "number"),
        ResultFieldSpec("bathrooms", "Bathrooms", "number"),
        ResultFieldSpec("size_sqft", "Size (sq ft)", "number"),
        ResultFieldSpec("listing_date", "Listing date", "date"),
        ResultFieldSpec("drawbacks", "Important drawbacks", "text"),
    ],
    system_prompt_fragment=(
        "Analyze distance, estimated travel time, price, property details, taxes, fees, listing date/"
        "freshness, and preference match for homes matching the configured filters. Flag stale, incomplete, "
        "or unusually priced listings. Never rank neighborhoods using protected or sensitive demographic "
        "characteristics."
    ),
    detail_tabs=["overview", "results", "sources", "run_history", "logs", "settings"],
    default_alert_rules=[
        {"rule_type": "new_results", "channel": "in_app"},
        {"rule_type": "changed_results", "channel": "in_app"},
        {"rule_type": "run_error", "channel": "in_app"},
    ],
)
