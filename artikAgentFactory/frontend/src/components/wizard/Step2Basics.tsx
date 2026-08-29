import { AgentDraft, Template } from "../../api/types";

export default function Step2Basics({
  draft, template, onField,
}: { draft: AgentDraft; template: Template | undefined; onField: (field: keyof AgentDraft, value: unknown) => void }) {
  return (
    <div className="space-y-4">
      <h2 className="font-display text-lg font-bold text-ink">Basic information</h2>

      <div>
        <label className="label" htmlFor="agent-name">Agent name</label>
        <input
          id="agent-name" className="input" value={draft.name}
          onChange={(e) => onField("name", e.target.value)}
          placeholder={template ? `${template.name} — ${new Date().getFullYear()}` : "Agent name"}
        />
      </div>

      <div>
        <label className="label" htmlFor="agent-desc">Description</label>
        <input
          id="agent-desc" className="input" value={draft.description}
          onChange={(e) => onField("description", e.target.value)}
          placeholder="Optional short description shown on the dashboard card"
        />
      </div>

      <div>
        <label className="label" htmlFor="agent-objective">
          {template?.kind === "action" ? "What should this agent do?" : "What should this agent research?"}
        </label>
        <textarea
          id="agent-objective" className="textarea" value={draft.objective}
          onChange={(e) => onField("objective", e.target.value)}
          placeholder={template?.example_use_case ?? "Describe the research objective in your own words"}
        />
        {template && <p className="mt-1.5 text-[11px] text-ink-mute">Example: “{template.example_use_case}”</p>}
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <label className="label" htmlFor="agent-tags">Tags (comma separated)</label>
          <input
            id="agent-tags" className="input" value={draft.tags.join(", ")}
            onChange={(e) => onField("tags", e.target.value.split(",").map((t) => t.trim()).filter(Boolean))}
            placeholder="priority, akshobh, watchlist"
          />
        </div>
        <div>
          <label className="label" htmlFor="agent-lang">Result language</label>
          <select id="agent-lang" className="select" value={draft.result_language} onChange={(e) => onField("result_language", e.target.value)}>
            <option value="en">English</option>
            <option value="es">Spanish</option>
            <option value="fr">French</option>
            <option value="de">German</option>
          </select>
        </div>
      </div>

      <div className="flex items-center gap-3 rounded-xl border border-border bg-surface-2 px-4 py-3">
        <input
          id="agent-enabled" type="checkbox" className="h-4 w-4 accent-blue"
          checked={draft.status === "active"}
          onChange={(e) => onField("status", e.target.checked ? "active" : "paused")}
        />
        <label htmlFor="agent-enabled" className="text-sm text-ink">
          Enabled — this agent can run manually or on its schedule
        </label>
      </div>
    </div>
  );
}
