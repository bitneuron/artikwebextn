import { useEffect, useMemo, useReducer, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { agentsApi } from "../api/agents";
import { templatesApi } from "../api/templates";
import { Template } from "../api/types";
import WizardShell from "../components/wizard/WizardShell";
import Step1Template from "../components/wizard/Step1Template";
import Step2Basics from "../components/wizard/Step2Basics";
import Step3Filters from "../components/wizard/Step3Filters";
import Step4Profile from "../components/wizard/Step4Profile";
import Step5Schedule from "../components/wizard/Step5Schedule";
import Step6Alerts from "../components/wizard/Step6Alerts";
import Step7Review from "../components/wizard/Step7Review";
import { emptyDraft, wizardReducer } from "../lib/wizardReducer";

export default function CreateAgentWizard({ mode }: { mode: "create" | "edit" }) {
  const nav = useNavigate();
  const { id } = useParams();
  const [params] = useSearchParams();
  const [templates, setTemplates] = useState<Template[] | null>(null);
  const [step, setStep] = useState(mode === "edit" ? 2 : 1);
  const [draft, dispatch] = useReducer(wizardReducer, emptyDraft());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(mode === "create");

  useEffect(() => {
    templatesApi.list().then((list) => {
      setTemplates(list);
      const presetId = params.get("template");
      if (mode === "create" && presetId) {
        const t = list.find((x) => x.id === presetId);
        if (t) dispatch({ type: "SET_TEMPLATE", template: t });
      }
    });
  }, []);

  useEffect(() => {
    if (mode !== "edit" || !id) return;
    agentsApi.get(Number(id)).then((agent) => {
      dispatch({
        type: "HYDRATE",
        draft: {
          template_id: agent.template_id, name: agent.name, description: agent.description ?? "",
          objective: agent.objective, tags: agent.tags, result_language: agent.result_language,
          time_zone: agent.time_zone, filters: agent.filters, profile: agent.profile,
          schedule: agent.schedule, is_schedule_enabled: agent.is_schedule_enabled,
          alert_rules: agent.alert_rules.map((r) => ({ rule_type: r.rule_type, channel: r.channel, config: r.config, is_enabled: r.is_enabled })),
          status: agent.status, run_immediately: false,
        },
      });
      setLoaded(true);
    });
  }, [mode, id]);

  const template = useMemo(() => templates?.find((t) => t.id === draft.template_id), [templates, draft.template_id]);

  if (!loaded || templates === null) {
    return <div className="mx-auto max-w-3xl"><div className="skeleton h-96 rounded-2xl" /></div>;
  }

  const canGoNext = (() => {
    if (step === 1) return Boolean(draft.template_id);
    if (step === 2) return draft.name.trim().length > 0 && draft.objective.trim().length > 0;
    return true;
  })();

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      if (mode === "create") {
        const agent = await agentsApi.create(draft);
        nav(`/agents/${agent.id}`);
      } else if (id) {
        await agentsApi.update(Number(id), draft);
        nav(`/agents/${id}`);
      }
    } catch (e: any) {
      setError(e.message ?? "Failed to save agent");
    } finally {
      setBusy(false);
    }
  }

  function next() {
    if (step === 7) {
      submit();
      return;
    }
    setStep((s) => Math.min(7, s + 1));
  }

  return (
    <div>
      <h1 className="mx-auto mb-6 max-w-3xl font-display text-2xl font-extrabold tracking-tight text-ink">
        {mode === "create" ? "Create Agent" : `Edit — ${draft.name}`}
      </h1>

      {error && (
        <div className="mx-auto mb-4 max-w-3xl rounded-xl border border-bad/30 bg-bad/10 px-4 py-3 text-sm text-bad">{error}</div>
      )}

      <WizardShell
        step={step}
        onBack={() => setStep((s) => Math.max(1, s - 1))}
        onNext={next}
        canGoNext={canGoNext}
        nextLabel={step === 7 ? (mode === "create" ? "Save and Run" : "Save changes") : "Continue"}
        busy={busy}
      >
        {step === 1 && (
          <Step1Template templates={templates} selectedId={draft.template_id} onSelect={(t) => dispatch({ type: "SET_TEMPLATE", template: t })} />
        )}
        {step === 2 && <Step2Basics draft={draft} template={template} onField={(f, v) => dispatch({ type: "SET_FIELD", field: f, value: v })} />}
        {step === 3 && <Step3Filters template={template} filters={draft.filters} onFilter={(k, v) => dispatch({ type: "SET_FILTER", key: k, value: v })} />}
        {step === 4 && (
          <Step4Profile
            template={template} enabled={draft.profile !== null} profile={draft.profile ?? {}}
            onToggle={(en) => dispatch({ type: "TOGGLE_PROFILE", enabled: en })}
            onField={(k, v) => dispatch({ type: "SET_PROFILE_FIELD", key: k, value: v })}
          />
        )}
        {step === 5 && (
          <Step5Schedule
            schedule={draft.schedule} runImmediately={draft.run_immediately}
            onChange={(s) => dispatch({ type: "SET_SCHEDULE", value: s })}
            onRunImmediately={(v) => dispatch({ type: "SET_FIELD", field: "run_immediately", value: v })}
          />
        )}
        {step === 6 && <Step6Alerts rules={draft.alert_rules} onChange={(r) => dispatch({ type: "SET_ALERT_RULES", value: r })} />}
        {step === 7 && <Step7Review draft={draft} template={template} />}
      </WizardShell>

      {step === 1 && (
        <div className="mx-auto mt-4 max-w-3xl text-right">
          <button className="btn-ghost btn-sm" onClick={() => nav("/")}>Cancel</button>
        </div>
      )}
    </div>
  );
}
