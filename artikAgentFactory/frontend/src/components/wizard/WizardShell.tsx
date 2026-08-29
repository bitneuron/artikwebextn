import { ReactNode } from "react";

const STEPS = [
  "Template", "Basics", "Filters", "Profile", "Schedule", "Alerts", "Review",
];

export default function WizardShell({
  step, onBack, onNext, canGoNext, nextLabel = "Continue", children, busy,
}: {
  step: number; onBack: () => void; onNext: () => void; canGoNext: boolean;
  nextLabel?: string; children: ReactNode; busy?: boolean;
}) {
  return (
    <div className="mx-auto max-w-3xl">
      <ol className="mb-8 flex flex-wrap items-center gap-x-1 gap-y-2" aria-label="Progress">
        {STEPS.map((label, i) => {
          const idx = i + 1;
          const state = idx === step ? "current" : idx < step ? "done" : "todo";
          return (
            <li key={label} className="flex items-center gap-1">
              <span
                className={`flex h-7 items-center gap-1.5 rounded-full px-2.5 text-[11px] font-semibold transition ${
                  state === "current"
                    ? "bg-grad-brand text-white"
                    : state === "done"
                    ? "bg-ok/15 text-ok"
                    : "bg-surface-2 text-ink-mute"
                }`}
              >
                {state === "done" ? "✓" : idx}
                <span className="hidden sm:inline">{label}</span>
              </span>
              {idx < STEPS.length && <span className="h-px w-3 bg-border sm:w-5" />}
            </li>
          );
        })}
      </ol>

      <div className="card animate-rise-in p-6 md:p-8">{children}</div>

      <div className="mt-6 flex items-center justify-between">
        <button className="btn-ghost" onClick={onBack} disabled={step === 1}>
          ← Back
        </button>
        <button className="btn-primary" onClick={onNext} disabled={!canGoNext || busy}>
          {busy ? "Saving…" : nextLabel}
        </button>
      </div>
    </div>
  );
}
