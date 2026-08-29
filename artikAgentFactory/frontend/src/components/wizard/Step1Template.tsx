import { Template } from "../../api/types";

export default function Step1Template({
  templates, selectedId, onSelect,
}: { templates: Template[]; selectedId: string; onSelect: (t: Template) => void }) {
  return (
    <div>
      <h2 className="font-display text-lg font-bold text-ink">Choose an agent type</h2>
      <p className="mt-1 text-sm text-ink-dim">Every template has sensible defaults you can fully customize later.</p>
      <div className="mt-5 grid grid-cols-1 gap-2.5 sm:grid-cols-2">
        {templates.map((t) => (
          <button
            key={t.id}
            onClick={() => onSelect(t)}
            className={`rounded-xl border p-3.5 text-left transition ${
              selectedId === t.id
                ? "border-blue/50 bg-blue/10 shadow-glow"
                : "border-border bg-surface-2 hover:border-border-hover"
            }`}
          >
            <div className="flex items-center gap-2.5">
              <span className="text-lg">{t.icon}</span>
              <span className="font-display text-sm font-bold text-ink">{t.name}</span>
            </div>
            <p className="mt-1.5 text-xs text-ink-dim">{t.short_description}</p>
          </button>
        ))}
      </div>
    </div>
  );
}
