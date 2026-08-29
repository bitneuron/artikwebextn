from app.templates.spec import FilterField, ResultFieldSpec, TemplateSpec

TEMPLATE = TemplateSpec(
    id="professor_lab_finder",
    name="Professor and Lab Finder",
    icon="🧑‍🔬",
    category="education",
    short_description="Identify professors and labs whose research aligns with a student's interests.",
    example_use_case="Identify professors and laboratories matching a student's AI/biology research interests.",
    default_filters=[
        FilterField("research_interests", "Research interests", "text", required=True),
        FilterField("institutions", "Institutions (blank = broad search)", "text"),
        FilterField("max_results", "Maximum results per run", "number", placeholder="20"),
    ],
    result_categories=["professor"],
    result_fields=[
        ResultFieldSpec("institution", "Institution", "text"),
        ResultFieldSpec("department", "Department", "text"),
        ResultFieldSpec("research_focus", "Research focus", "text"),
        ResultFieldSpec("recent_publications", "Relevant recent publications", "text", tracked_for_changes=True),
        ResultFieldSpec("why_it_matches", "Why it matches", "text"),
        ResultFieldSpec("student_opportunities_mentioned", "Student opportunities mentioned", "badge"),
        ResultFieldSpec("outreach_angle", "Suggested outreach angle", "text"),
    ],
    system_prompt_fragment=(
        "Identify professors and laboratories aligned with the configured research interests. Report "
        "institution, department, research focus, relevant recent publications and projects, why the work "
        "matches, the lab/faculty webpage, and whether student opportunities are mentioned publicly. Only "
        "surface publicly listed professional contact information — never collect or expose private contact "
        "details, and never draft or send outreach automatically."
    ),
    detail_tabs=["overview", "results", "sources", "run_history", "logs", "settings"],
)
