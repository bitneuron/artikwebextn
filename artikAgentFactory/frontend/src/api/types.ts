export type FilterField = {
  key: string;
  label: string;
  type: "text" | "select" | "multiselect" | "number" | "date_range" | "boolean" | "url_list" | "textarea";
  options: string[] | null;
  placeholder: string | null;
  required: boolean;
};

export type ResultFieldSpec = {
  key: string;
  label: string;
  type: "text" | "date" | "currency" | "percent" | "url" | "badge" | "number";
  tracked_for_changes: boolean;
};

export type DefaultAlertRule = { rule_type: string; channel?: string; config?: Record<string, unknown> };

export type Template = {
  id: string;
  name: string;
  icon: string;
  category: "education" | "finance" | "science" | "lifestyle" | "custom";
  short_description: string;
  example_use_case: string;
  kind: "research" | "action";
  default_filters: FilterField[];
  supports_profile: boolean;
  result_categories: string[];
  result_fields: ResultFieldSpec[];
  detail_tabs: string[];
  default_alert_rules: DefaultAlertRule[];
};

export type AgentStatus = "active" | "paused" | "archived";

export type AlertRule = {
  id: number;
  agent_id: number;
  rule_type: string;
  channel: "slack" | "in_app";
  is_enabled: boolean;
  config: Record<string, unknown>;
  created_at: string;
};

export type AlertRuleIn = {
  rule_type: string;
  channel: "slack" | "in_app";
  config: Record<string, unknown>;
  is_enabled: boolean;
};

export type ScheduleConfig = {
  mode: "manual" | "interval" | "preset";
  preset?: "daily" | "weekly" | "biweekly" | "monthly";
  interval_minutes?: number;
  hour_utc?: number;
  day_of_week?: number;
};

export type Agent = {
  id: number;
  template_id: string;
  name: string;
  description: string | null;
  objective: string;
  status: AgentStatus;
  tags: string[];
  result_language: string;
  time_zone: string;
  filters: Record<string, unknown>;
  profile: Record<string, unknown> | null;
  schedule: ScheduleConfig;
  is_schedule_enabled: boolean;
  last_run_id: number | null;
  last_run_at: string | null;
  last_run_status: string | null;
  next_run_at: string | null;
  alert_rules: AlertRule[];
  created_at: string;
  updated_at: string;
};

export type AgentListItem = {
  id: number;
  template_id: string;
  name: string;
  description: string | null;
  status: AgentStatus;
  tags: string[];
  is_schedule_enabled: boolean;
  last_run_at: string | null;
  last_run_status: string | null;
  next_run_at: string | null;
  result_count_total: number;
  result_count_new: number;
  result_count_changed: number;
  high_priority_count: number;
  can_manage: boolean;
  can_run: boolean;
  created_at: string;
  updated_at: string;
};

export type AgentDraft = {
  template_id: string;
  name: string;
  description: string;
  objective: string;
  tags: string[];
  result_language: string;
  time_zone: string;
  filters: Record<string, unknown>;
  profile: Record<string, unknown> | null;
  schedule: ScheduleConfig;
  is_schedule_enabled: boolean;
  alert_rules: AlertRuleIn[];
  status: AgentStatus;
  run_immediately: boolean;
};

export type RunStatus = "queued" | "running" | "completed" | "failed" | "partial";

export type Run = {
  id: number;
  agent_id: number;
  trigger: "manual" | "scheduled";
  status: RunStatus;
  started_at: string | null;
  completed_at: string | null;
  duration_seconds: number | null;
  result_count_new: number;
  result_count_changed: number;
  result_count_unchanged: number;
  result_count_total: number;
  error_message: string | null;
  queries: string[];
  stats: Record<string, unknown>;
  created_at: string;
};

export type RunLog = {
  id: number;
  run_id: number;
  ts: string;
  level: "info" | "warn" | "error";
  stage: string;
  message: string;
};

export type ResultSource = { id: number; url: string; title: string | null; retrieved_at: string; snippet: string | null };
export type Note = { id: number; result_id: number; body: string; created_at: string; updated_at: string };

export type ChangeStatus = "new" | "changed" | "unchanged";

export type Result = {
  id: number;
  agent_id: number;
  title: string;
  summary: string | null;
  url: string;
  source_name: string | null;
  published_or_updated_at: string | null;
  relevance_score: number;
  confidence_score: number;
  source_credibility: "high" | "medium" | "low";
  category: string;
  fields: Record<string, unknown>;
  change_status: ChangeStatus;
  changed_fields: Record<string, { old: unknown; new: unknown }>;
  is_saved: boolean;
  is_dismissed: boolean;
  priority_flag: boolean;
  first_seen_run_id: number | null;
  last_seen_run_id: number | null;
  created_at: string;
  updated_at: string;
};

export type ResultDetail = Result & { sources: ResultSource[]; notes: Note[] };

export type AlertEvent = {
  id: number;
  agent_id: number;
  run_id: number;
  rule_id: number | null;
  result_id: number | null;
  severity: "info" | "success" | "warning" | "error";
  title: string;
  message: string;
  delivered: boolean;
  created_at: string;
};

export type Dashboard = {
  total_agents: number;
  active_agents: number;
  paused_agents: number;
  error_agents: number;
  new_findings_7d: number;
  high_priority_alerts: number;
  sources_checked_7d: number;
  upcoming_deadlines: number;
  scheduler_running: boolean;
  recent_alerts: AlertEvent[];
};
