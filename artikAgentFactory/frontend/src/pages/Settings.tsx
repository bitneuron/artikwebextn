import { useEffect, useState } from "react";
import { notificationSettingsApi, NotificationSettings } from "../api/notificationSettings";
import { useAuth } from "../contexts/AuthContext";

const TOGGLES: { key: keyof NotificationSettings; label: string }[] = [
  { key: "notify_on_run_completed", label: "Every successful run" },
  { key: "notify_on_new_results", label: "New results" },
  { key: "notify_on_changed_results", label: "Changed results" },
  { key: "notify_on_high_priority", label: "High-priority matches" },
  { key: "notify_on_deadline_approaching", label: "Approaching deadlines" },
  { key: "notify_on_run_error", label: "Run errors" },
];

export default function Settings() {
  const { user } = useAuth();
  const [ns, setNs] = useState<NotificationSettings | null>(null);

  useEffect(() => {
    if (user?.role === "administrator") notificationSettingsApi.get().then(setNs);
  }, [user]);

  async function toggle(key: keyof NotificationSettings) {
    if (!ns) return;
    const updated = await notificationSettingsApi.update({ [key]: !ns[key] });
    setNs(updated);
  }

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="font-display text-2xl font-extrabold tracking-tight text-ink">Settings</h1>
      <p className="mt-1.5 text-sm text-ink-dim">Workspace defaults for new agents.</p>

      <div className="card mt-6 p-6">
        <h2 className="font-display text-sm font-bold text-ink">Defaults</h2>
        <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label className="label">Default result language</label>
            <select className="select" defaultValue="en">
              <option value="en">English</option>
              <option value="es">Spanish</option>
              <option value="fr">French</option>
            </select>
          </div>
          <div>
            <label className="label">Default time zone</label>
            <input className="input" defaultValue={Intl.DateTimeFormat().resolvedOptions().timeZone} disabled />
          </div>
        </div>
        <p className="mt-4 text-xs text-ink-mute">
          Per-agent alert channels, schedules, and search behavior are configured on each agent individually.
        </p>
      </div>

      {user?.role === "administrator" && (
        <div className="card mt-6 p-6">
          <div className="flex items-center justify-between">
            <h2 className="font-display text-sm font-bold text-ink">Slack notifications (#artik-agent-notify)</h2>
            {ns && (
              <span className={ns.slack_configured ? "badge-ok" : "badge-warn"}>
                {ns.slack_configured ? "configured" : "not configured"}
              </span>
            )}
          </div>
          {!ns ? (
            <div className="skeleton mt-4 h-24 rounded-lg" />
          ) : (
            <>
              {!ns.slack_configured && (
                <p className="mt-2 rounded-lg bg-warn/10 px-3 py-2 text-xs text-warn">
                  No Slack webhook is configured yet — add SLACK_WEBHOOK_URL to Secrets Manager. Notifications stay
                  silently disabled until then.
                </p>
              )}
              <div className="mt-4 flex items-center gap-3 rounded-xl border border-border bg-surface-2 px-4 py-3">
                <input id="slack-enabled" type="checkbox" className="h-4 w-4 accent-blue"
                  checked={ns.slack_enabled} onChange={() => toggle("slack_enabled")} />
                <label htmlFor="slack-enabled" className="text-sm font-semibold text-ink">
                  Slack notifications enabled workspace-wide
                </label>
              </div>
              <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
                {TOGGLES.map((t) => (
                  <div key={String(t.key)} className="flex items-center gap-2.5 rounded-lg bg-surface-2 px-3 py-2">
                    <input
                      id={String(t.key)} type="checkbox" className="h-4 w-4 accent-blue"
                      checked={Boolean(ns[t.key])} disabled={!ns.slack_enabled}
                      onChange={() => toggle(t.key)}
                    />
                    <label htmlFor={String(t.key)} className="text-xs text-ink">{t.label}</label>
                  </div>
                ))}
              </div>
              <p className="mt-3 text-[11px] text-ink-mute">
                This is a workspace-wide gate layered on top of each agent's own alert rules — a rule must be
                configured with the Slack channel AND enabled here to actually deliver.
              </p>
            </>
          )}
        </div>
      )}
    </div>
  );
}
