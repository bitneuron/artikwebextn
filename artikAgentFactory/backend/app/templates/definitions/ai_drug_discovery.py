from app.templates.spec import FilterField, ResultFieldSpec, TemplateSpec

TEMPLATE = TemplateSpec(
    id="ai_drug_discovery",
    name="AI Drug Discovery Intelligence",
    icon="🧬",
    category="science",
    short_description="Track developments in AI-powered drug discovery: models, trials, partnerships.",
    example_use_case="Track meaningful developments in AI-powered drug discovery.",
    default_filters=[
        FilterField("focus_areas", "Focus areas (e.g. protein folding, target ID, ADMET)", "text"),
        FilterField("diseases_or_targets", "Diseases / biological targets of interest", "text"),
        FilterField("max_results", "Maximum results per run", "number", placeholder="20"),
    ],
    result_categories=["article"],
    result_fields=[
        ResultFieldSpec("organization", "Organization / research team", "text"),
        ResultFieldSpec("technology", "Technology", "text"),
        ResultFieldSpec("target", "Disease or biological target", "text"),
        ResultFieldSpec("validation_stage", "Validation stage", "badge"),
        ResultFieldSpec("limitations", "Limitations", "text"),
        ResultFieldSpec("why_it_matters", "Why it matters", "text"),
    ],
    system_prompt_fragment=(
        "Track generative molecular models, protein structure/interaction prediction, target ID/validation, "
        "virtual screening, drug repurposing, ADMET/toxicity prediction, biological foundation models, "
        "laboratory automation, clinical trials, and pharma/biotech partnerships, funding, and acquisitions "
        "in AI drug discovery. For every development, explicitly classify the validation stage — "
        "computational prediction, laboratory validation, animal/preclinical evidence, human clinical "
        "trials, or regulatory approval — and never present a press release or computational/preclinical "
        "result as proof that a treatment works in humans."
    ),
    detail_tabs=["overview", "results", "articles", "sources", "run_history", "logs", "settings"],
)
