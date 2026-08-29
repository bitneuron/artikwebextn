import { api } from "./client";

export type NotificationSettings = {
  workspace_id: number;
  slack_enabled: boolean;
  notify_on_run_completed: boolean;
  notify_on_new_results: boolean;
  notify_on_changed_results: boolean;
  notify_on_high_priority: boolean;
  notify_on_deadline_approaching: boolean;
  notify_on_run_error: boolean;
  min_severity: string;
  slack_configured: boolean;
  updated_at: string;
};

export const notificationSettingsApi = {
  get: () => api.get<NotificationSettings>("/api/notification-settings"),
  update: (body: Partial<NotificationSettings>) => api.put<NotificationSettings>("/api/notification-settings", body),
};
