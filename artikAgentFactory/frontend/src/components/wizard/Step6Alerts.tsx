import { AlertRuleIn } from "../../api/types";

const RULE_LABELS: Record<string, string> = {
  run_completed: "Every successful run",
  new_results: "Every new result",
  changed_results: "Material changes to existing results",
  high_priority_match: "High-confidence / high-relevance matches",
  deadline_approaching: "Approaching deadlines",
  run_error: "Run errors",
};

const AVAILABLE_RULES = Object.keys(RULE_LABELS);

export default function Step6Alerts({
  rules, onChange,
}: { rules: AlertRuleIn[]; onChange: (rules: AlertRuleIn[]) => void }) {
  function toggle(ruleType: string) {
    const exists = rules.find((r) => r.rule_type === ruleType);
    if (exists) onChange(rules.filter((r) => r.rule_type !== ruleType));
    else onChange([...rules, { rule_type: ruleType, channel: "in_app", config: {}, is_enabled: true }]);
  }
  function setChannel(ruleType: string, channel: "slack" | "in_app") {
    onChange(rules.map((r) => (r.rule_type === ruleType ? { ...r, channel } : r)));
  }
  function setDays(ruleType: string, days: number) {
    onChange(rules.map((r) => (r.rule_type === ruleType ? { ...r, config: { ...r.config, days_before: days } } : r)));
  }

  return (
    <div className="space-y-3">
      <h2 className="font-display text-lg font-bold text-ink">Alerts</h2>
      <p className="text-sm text-ink-dim">Choose what should notify you, and where.</p>

      <div className="space-y-2">
        {AVAILABLE_RULES.map((ruleType) => {
          const rule = rules.find((r) => r.rule_type === ruleType);
          const active = Boolean(rule);
          return (
            <div key={ruleType} className={`rounded-xl border px-4 py-3 transition ${active ? "border-blue/40 bg-blue/5" : "border-border bg-surface-2"}`}>
              <div className="flex flex-wrap items-center gap-3">
                <input
                  id={`rule-${ruleType}`} type="checkbox" className="h-4 w-4 accent-blue" checked={active}
                  onChange={() => toggle(ruleType)}
                />
                <label htmlFor={`rule-${ruleType}`} className="flex-1 text-sm font-medium text-ink">{RULE_LABELS[ruleType]}</label>
                {active && (
                  <div className="flex items-center gap-2">
                    {ruleType === "deadline_approaching" && (
                      <select
                        className="select w-auto !py-1 text-xs" value={(rule?.config?.days_before as number) ?? 7}
                        onChange={(e) => setDays(ruleType, Number(e.target.value))}
                      >
                        {[30, 14, 7, 3, 1].map((d) => <option key={d} value={d}>{d} days before</option>)}
                      </select>
                    )}
                    <select
                      className="select w-auto !py-1 text-xs" value={rule?.channel ?? "in_app"}
                      onChange={(e) => setChannel(ruleType, e.target.value as "slack" | "in_app")}
                    >
                      <option value="in_app">In-app</option>
                      <option value="slack">Slack</option>
                    </select>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
