import { AgentDraft, Template } from "../api/types";

export function emptyDraft(): AgentDraft {
  return {
    template_id: "",
    name: "",
    description: "",
    objective: "",
    tags: [],
    result_language: "en",
    time_zone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
    filters: {},
    profile: null,
    schedule: { mode: "manual" },
    is_schedule_enabled: false,
    alert_rules: [],
    status: "active",
    run_immediately: false,
  };
}

export type WizardAction =
  | { type: "SET_TEMPLATE"; template: Template }
  | { type: "SET_FIELD"; field: keyof AgentDraft; value: unknown }
  | { type: "SET_FILTER"; key: string; value: unknown }
  | { type: "SET_PROFILE_FIELD"; key: string; value: unknown }
  | { type: "TOGGLE_PROFILE"; enabled: boolean }
  | { type: "SET_SCHEDULE"; value: AgentDraft["schedule"] }
  | { type: "SET_ALERT_RULES"; value: AgentDraft["alert_rules"] }
  | { type: "HYDRATE"; draft: AgentDraft };

export function wizardReducer(state: AgentDraft, action: WizardAction): AgentDraft {
  switch (action.type) {
    case "SET_TEMPLATE":
      return {
        ...state,
        template_id: action.template.id,
        alert_rules: action.template.default_alert_rules.map((r) => ({
          rule_type: r.rule_type, channel: (r.channel as "slack" | "in_app") ?? "in_app",
          config: r.config ?? {}, is_enabled: true,
        })),
        profile: action.template.supports_profile ? state.profile : null,
      };
    case "SET_FIELD":
      return { ...state, [action.field]: action.value };
    case "SET_FILTER":
      return { ...state, filters: { ...state.filters, [action.key]: action.value } };
    case "SET_PROFILE_FIELD":
      return { ...state, profile: { ...(state.profile ?? {}), [action.key]: action.value } };
    case "TOGGLE_PROFILE":
      return { ...state, profile: action.enabled ? (state.profile ?? {}) : null };
    case "SET_SCHEDULE":
      return { ...state, schedule: action.value, is_schedule_enabled: action.value.mode !== "manual" };
    case "SET_ALERT_RULES":
      return { ...state, alert_rules: action.value };
    case "HYDRATE":
      return action.draft;
    default:
      return state;
  }
}
