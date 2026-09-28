import { api } from "../api/client";
import type { Reminder } from "../api/types";

/** Apply a reminder lifecycle action; returns true if the list should reload. */
export async function reminderAction(action: string, r: Reminder): Promise<boolean> {
  switch (action) {
    case "complete":
      await api.post(`/api/reminders/${r.id}/complete`); return true;
    case "restore":
      await api.post(`/api/reminders/${r.id}/restore`); return true;
    case "archive":
      await api.post(`/api/reminders/${r.id}/archive`); return true;
    case "duplicate":
      await api.post(`/api/reminders/${r.id}/duplicate`); return true;
    case "snooze": {
      const mins = Number(prompt("Snooze for how many minutes?", "60"));
      if (!mins || mins < 1) return false;
      await api.post(`/api/reminders/${r.id}/snooze`, { minutes: mins }); return true;
    }
    case "delete":
      if (!confirm(`Delete "${r.title}"?`)) return false;
      await api.del(`/api/reminders/${r.id}`); return true;
    default:
      return false;
  }
}
