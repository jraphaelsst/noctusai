/**
 * Per-trigger config fields for the flow dialog (`trigger_config`), plus the
 * pure builder + execution-subject label helpers.
 *
 * Keys honoured by the backend (automation_triggers._matches):
 *   keyword_received       → keyword (required — empty never fires)
 *   pipeline_stage_entered → stage_id (optional, empty = any stage)
 *   lead_status_changed    → status "won"|"lost" (optional = either)
 * Unknown existing keys are preserved on save.
 */
import type { TriggerType } from "@/hooks/useAutomacao";

const MANAGED = ["keyword", "stage_id", "status"] as const;

export function buildTriggerConfig(
  trigger: TriggerType,
  existing: Record<string, unknown> | undefined,
  v: { keyword: string; stageId: string; leadStatus: string },
): { config?: Record<string, unknown>; error?: string } {
  const out: Record<string, unknown> = { ...(existing ?? {}) };
  for (const k of MANAGED) delete out[k];
  if (trigger === "keyword_received") {
    const kw = v.keyword.trim();
    if (!kw) return { error: "Informe a palavra-chave — sem ela o fluxo nunca dispara" };
    out.keyword = kw;
  } else if (trigger === "pipeline_stage_entered") {
    if (v.stageId) out.stage_id = v.stageId;
  } else if (trigger === "lead_status_changed") {
    if (v.leadStatus) out.status = v.leadStatus;
  }
  return { config: out };
}

const SUBJECT_LABELS: Record<string, string> = {
  lead: "Lead",
  client: "Cliente",
  task: "Tarefa",
  meeting: "Reunião",
};

export function subjectLabel(
  exec: { lead_id: string | null; subject_type?: string; subject_id?: string | null },
  leadName: (id: string) => string | undefined,
): string {
  const type = exec.subject_type || "lead";
  if (type === "lead") {
    if (!exec.lead_id) return "Lead removido ou indisponível";
    return leadName(exec.lead_id) ?? "Lead removido ou indisponível";
  }
  const short = exec.subject_id ? ` #${exec.subject_id.slice(0, 8)}` : "";
  return `${SUBJECT_LABELS[type] ?? type}${short}`;
}

const INPUT =
  "flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

export function TriggerConfigFields(props: {
  triggerType: TriggerType;
  keyword: string;
  onKeyword: (v: string) => void;
  stageId: string;
  onStageId: (v: string) => void;
  stages: { id: string; name: string }[];
  leadStatus: string;
  onLeadStatus: (v: string) => void;
  error?: string;
}) {
  const t = props.triggerType;
  if (t === "keyword_received") {
    return (
      <div>
        <label htmlFor="aut-keyword" className="mb-1 block text-sm font-medium text-foreground">
          Palavra-chave *
        </label>
        <input
          id="aut-keyword"
          value={props.keyword}
          onChange={(e) => props.onKeyword(e.target.value)}
          placeholder="Ex.: orçamento"
          className={INPUT}
        />
        <p className="mt-1 text-xs text-muted-foreground">
          Dispara quando a mensagem recebida contém esta palavra (sem diferenciar maiúsculas).
        </p>
        {props.error && <p role="alert" className="mt-1 text-xs text-destructive">{props.error}</p>}
      </div>
    );
  }
  if (t === "pipeline_stage_entered") {
    return (
      <div>
        <label htmlFor="aut-stage" className="mb-1 block text-sm font-medium text-foreground">
          Etapa do funil
        </label>
        <select id="aut-stage" value={props.stageId} onChange={(e) => props.onStageId(e.target.value)} className={INPUT}>
          <option value="">Qualquer etapa</option>
          {props.stages.map((s) => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </select>
      </div>
    );
  }
  if (t === "lead_status_changed") {
    return (
      <div>
        <label htmlFor="aut-status" className="mb-1 block text-sm font-medium text-foreground">
          Novo status
        </label>
        <select id="aut-status" value={props.leadStatus} onChange={(e) => props.onLeadStatus(e.target.value)} className={INPUT}>
          <option value="">Qualquer (ganho ou perdido)</option>
          <option value="won">Ganho</option>
          <option value="lost">Perdido</option>
        </select>
      </div>
    );
  }
  if (t === "meeting_created") {
    return (
      <p className="text-xs text-muted-foreground" data-testid="aut-meeting-note">
        Dispara para eventos do tipo Reunião.
      </p>
    );
  }
  return null;
}
