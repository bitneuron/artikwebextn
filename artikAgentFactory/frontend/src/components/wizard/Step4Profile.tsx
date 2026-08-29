import { Template } from "../../api/types";

const PROFILE_FIELDS: { key: string; label: string; placeholder?: string; type?: "text" | "textarea" }[] = [
  { key: "person_name", label: "Person's name" },
  { key: "current_school", label: "Current school / institution" },
  { key: "education_level", label: "Education level", placeholder: "High school / Undergraduate / Graduate" },
  { key: "expected_graduation", label: "Expected graduation" },
  { key: "location", label: "Location" },
  { key: "academic_interests", label: "Academic interests", type: "textarea" },
  { key: "intended_majors", label: "Intended majors" },
  { key: "research_interests", label: "Research interests", type: "textarea" },
  { key: "research_experience", label: "Research experience", type: "textarea" },
  { key: "technical_skills", label: "Technical skills" },
  { key: "career_goals", label: "Career goals", type: "textarea" },
  { key: "preferred_regions", label: "Preferred countries / regions" },
  { key: "eligibility_restrictions", label: "Citizenship / eligibility restrictions" },
  { key: "budget", label: "Budget" },
  { key: "financial_aid_needs", label: "Financial-aid requirements" },
  { key: "availability", label: "Availability" },
  { key: "risk_tolerance", label: "Risk tolerance", placeholder: "Low / Medium / High" },
  { key: "time_horizon", label: "Investment time horizon" },
  { key: "preferences", label: "Other preferences", type: "textarea" },
  { key: "exclusions", label: "Exclusions", type: "textarea" },
];

export default function Step4Profile({
  template, enabled, profile, onToggle, onField,
}: {
  template: Template | undefined; enabled: boolean; profile: Record<string, unknown>;
  onToggle: (enabled: boolean) => void; onField: (key: string, value: unknown) => void;
}) {
  return (
    <div className="space-y-4">
      <h2 className="font-display text-lg font-bold text-ink">Personal profile</h2>
      <p className="text-sm text-ink-dim">
        Optional. Personalizes research to a specific person's situation — never invented, only what you provide here.
      </p>

      <div className="flex items-center gap-3 rounded-xl border border-border bg-surface-2 px-4 py-3">
        <input id="profile-enabled" type="checkbox" className="h-4 w-4 accent-blue" checked={enabled}
          onChange={(e) => onToggle(e.target.checked)}
          disabled={template ? !template.supports_profile : false} />
        <label htmlFor="profile-enabled" className="text-sm text-ink">
          {template && !template.supports_profile
            ? "This template doesn't use a personal profile"
            : "Personalize this agent to a specific person"}
        </label>
      </div>

      {enabled && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {PROFILE_FIELDS.map((f) => (
            <div key={f.key} className={f.type === "textarea" ? "sm:col-span-2" : ""}>
              <label className="label" htmlFor={`profile-${f.key}`}>{f.label}</label>
              {f.type === "textarea" ? (
                <textarea id={`profile-${f.key}`} className="textarea" placeholder={f.placeholder}
                  value={(profile[f.key] as string) ?? ""} onChange={(e) => onField(f.key, e.target.value)} />
              ) : (
                <input id={`profile-${f.key}`} className="input" placeholder={f.placeholder}
                  value={(profile[f.key] as string) ?? ""} onChange={(e) => onField(f.key, e.target.value)} />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
