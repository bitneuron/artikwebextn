import { AgentStatus, RunStatus } from "../api/types";

const AGENT_STYLES: Record<AgentStatus, string> = {
  active: "badge-ok",
  paused: "badge-warn",
  archived: "badge-mute",
};

export function AgentStatusBadge({ status }: { status: AgentStatus }) {
  return (
    <span className={AGENT_STYLES[status]}>
      {status === "active" && <span className="live-dot" />}
      {status}
    </span>
  );
}

const RUN_STYLES: Record<RunStatus, string> = {
  queued: "badge-mute",
  running: "badge-blue",
  completed: "badge-ok",
  failed: "badge-bad",
  partial: "badge-warn",
};

export function RunStatusBadge({ status }: { status: RunStatus }) {
  return <span className={RUN_STYLES[status]}>{status}</span>;
}
