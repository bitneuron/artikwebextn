import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { templatesApi } from "../api/templates";
import { Template } from "../api/types";

const CATEGORY_LABEL: Record<string, string> = {
  education: "Education", finance: "Finance", science: "Science", lifestyle: "Lifestyle", custom: "Custom",
};
const CATEGORY_ACCENT: Record<string, string> = {
  education: "badge-blue", finance: "badge-ok", science: "badge-violet", lifestyle: "badge-warn", custom: "badge-mute",
};

export default function TemplatesGallery() {
  const nav = useNavigate();
  const [templates, setTemplates] = useState<Template[] | null>(null);

  useEffect(() => {
    templatesApi.list().then(setTemplates);
  }, []);

  return (
    <div className="mx-auto max-w-7xl">
      <div className="mb-8">
        <h1 className="font-display text-2xl font-extrabold tracking-tight text-ink md:text-3xl">Agent Templates</h1>
        <p className="mt-1.5 max-w-2xl text-sm text-ink-dim">
          Every template ships with sensible defaults for filters, result fields, and alerts — pick one to start, then
          customize everything in the next step.
        </p>
      </div>

      {templates === null && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => <div key={i} className="skeleton h-40 rounded-2xl" />)}
        </div>
      )}

      {templates && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {templates.map((t, i) => (
            <button
              key={t.id}
              onClick={() => nav(`/agents/new?template=${t.id}`)}
              className="card card-hover group animate-rise-in p-5 text-left"
              style={{ animationDelay: `${Math.min(i, 10) * 40}ms` }}
            >
              <div className="flex items-start justify-between">
                <div className="grid h-11 w-11 place-items-center rounded-xl bg-surface-2 text-xl transition group-hover:bg-gradient-to-br group-hover:from-blue/20 group-hover:to-violet/20">
                  {t.icon}
                </div>
                <span className={CATEGORY_ACCENT[t.category]}>{CATEGORY_LABEL[t.category]}</span>
              </div>
              <h3 className="mt-3 font-display text-base font-bold text-ink">{t.name}</h3>
              <p className="mt-1.5 text-xs leading-relaxed text-ink-dim">{t.short_description}</p>
              <p className="mt-3 rounded-lg bg-surface-2 px-3 py-2 text-[11px] italic text-ink-mute">
                “{t.example_use_case}”
              </p>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
