import { FilterField, Template } from "../../api/types";

function FieldInput({ field, value, onChange }: { field: FilterField; value: unknown; onChange: (v: unknown) => void }) {
  const id = `filter-${field.key}`;
  switch (field.type) {
    case "boolean":
      return (
        <div className="flex items-center gap-2.5 rounded-lg border border-border bg-surface-2 px-3 py-2.5">
          <input id={id} type="checkbox" className="h-4 w-4 accent-blue" checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} />
          <label htmlFor={id} className="text-sm text-ink">{field.label}</label>
        </div>
      );
    case "number":
      return (
        <input id={id} type="number" className="input" value={(value as string | number) ?? ""} placeholder={field.placeholder ?? ""}
          onChange={(e) => onChange(e.target.value === "" ? undefined : Number(e.target.value))} />
      );
    case "select":
      return (
        <select id={id} className="select" value={(value as string) ?? ""} onChange={(e) => onChange(e.target.value)}>
          <option value="">Any</option>
          {(field.options ?? []).map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      );
    case "multiselect": {
      const arr = Array.isArray(value) ? (value as string[]) : [];
      return (
        <div className="flex flex-wrap gap-1.5">
          {(field.options ?? []).map((o) => {
            const active = arr.includes(o);
            return (
              <button
                type="button" key={o}
                className={active ? "badge-blue" : "badge-mute"}
                onClick={() => onChange(active ? arr.filter((x) => x !== o) : [...arr, o])}
              >
                {o}
              </button>
            );
          })}
        </div>
      );
    }
    case "textarea":
    case "url_list":
      return (
        <textarea id={id} className="textarea" value={(value as string) ?? ""} placeholder={field.placeholder ?? ""}
          onChange={(e) => onChange(e.target.value)} />
      );
    default:
      return (
        <input id={id} className="input" value={(value as string) ?? ""} placeholder={field.placeholder ?? ""}
          onChange={(e) => onChange(e.target.value)} />
      );
  }
}

export default function Step3Filters({
  template, filters, onFilter,
}: { template: Template | undefined; filters: Record<string, unknown>; onFilter: (key: string, value: unknown) => void }) {
  if (!template) return null;
  const isAction = template.kind === "action";
  return (
    <div className="space-y-4">
      <h2 className="font-display text-lg font-bold text-ink">{isAction ? "Configuration" : "Research filters"}</h2>
      <p className="text-sm text-ink-dim">
        {isAction ? "Every field is optional unless marked required." : "Narrow the scope. Every field is optional unless marked required."}
      </p>
      {template.default_filters.length === 0 && (
        <p className="rounded-lg bg-surface-2 px-4 py-3 text-sm text-ink-mute">This template has no preset filters — rely on the objective above.</p>
      )}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {template.default_filters.map((f) => (
          <div key={f.key} className={f.type === "textarea" || f.type === "multiselect" ? "sm:col-span-2" : ""}>
            <label className="label" htmlFor={`filter-${f.key}`}>
              {f.label}{f.required && <span className="text-bad"> *</span>}
            </label>
            <FieldInput field={f} value={filters[f.key]} onChange={(v) => onFilter(f.key, v)} />
          </div>
        ))}
      </div>
    </div>
  );
}
