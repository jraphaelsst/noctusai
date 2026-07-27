/**
 * AdsLeads — "Leads" subtab of the Anúncios (Meta Ads) network.
 *
 * Brings the Lead-Ads (Instant Form) leads home LIVE — no DB yet. Two
 * tiers of data, split by the Meta scope they need:
 *
 *  1. Form inventory + field SCHEMA + volume metrics — accessible with
 *     only a Page token. This is what a future DB model is built from:
 *     each form's questions ARE the lead's columns. Always shown.
 *  2. The per-lead RECORDS (name/phone/email + qualifying answers) —
 *     gated on the distinct `leads_retrieval` scope. Until it's granted,
 *     an actionable banner explains how to unlock; the moment it is, the
 *     records panel fills in with no code change.
 */
import { useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  ChevronDown,
  ClipboardList,
  FileText,
  Info,
  Layers,
  Loader2,
  RefreshCw,
  Users,
} from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { MetricCard } from "@/components/MetricCard";
import { formatNumber } from "@/lib/formatNumber";
import {
  useLeadForms,
  useLeadRecords,
  useLeadSync,
  useSyncJob,
  type LeadgenForm,
  type LeadgenQuestion,
} from "@/hooks/useMetaAds";
import { AdsError, AdsLoading, AdsNotConfigured } from "./adsShared";

function syncedLabel(iso: string | null): string {
  if (!iso) return "nunca sincronizado";
  const d = new Date(iso);
  return `sincronizado ${d.toLocaleDateString("pt-BR")} ${d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`;
}

const FIELD_TYPE_LABEL: Record<string, string> = {
  FULL_NAME: "Nome",
  EMAIL: "E-mail",
  PHONE: "Telefone",
  CITY: "Cidade",
  STATE: "Estado",
  CUSTOM: "Pergunta",
};

function fieldTypeBadge(type: string | null): string {
  return type ? FIELD_TYPE_LABEL[type] ?? type : "—";
}

function shortDate(iso: string | null): string {
  if (!iso) return "—";
  return iso.slice(0, 10).split("-").reverse().join("/");
}

/** One form row — status + count + an expandable field schema (the
 *  "columns" a lead from this form carries). */
function FormRow({ form }: { form: LeadgenForm }) {
  const [open, setOpen] = useState(false);
  const active = form.status === "ACTIVE";
  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <div className="rounded-lg border">
        <CollapsibleTrigger asChild>
          <button className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-muted/50">
            <span className="flex min-w-0 items-center gap-2">
              <ChevronDown
                className={`h-4 w-4 shrink-0 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`}
              />
              <span className="truncate font-medium">{form.name ?? form.form_id}</span>
              <Badge
                variant="outline"
                className={
                  active
                    ? "border-emerald-500/30 bg-emerald-500/15 text-emerald-600"
                    : "border-muted-foreground/30 text-muted-foreground"
                }
              >
                {active ? "Ativo" : (form.status ?? "—")}
              </Badge>
            </span>
            <span className="flex shrink-0 items-center gap-4 text-sm tabular-nums">
              <span className="text-muted-foreground">{shortDate(form.created_time)}</span>
              <span className="font-semibold">
                {formatNumber(form.leads_count ?? 0)}{" "}
                <span className="font-normal text-muted-foreground">leads</span>
              </span>
            </span>
          </button>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="border-t px-4 py-3">
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Campos do formulário ({form.questions.length}) — o esquema dos dados
            </p>
            <div className="space-y-1.5">
              {form.questions.map((q: LeadgenQuestion, i) => (
                <div key={`${q.key}-${i}`} className="flex items-start gap-2 text-sm">
                  <Badge variant="secondary" className="shrink-0 font-mono text-[11px]">
                    {fieldTypeBadge(q.type)}
                  </Badge>
                  <span className="min-w-0">
                    <span className="break-words">{q.label ?? q.key}</span>
                    {q.options.length > 0 && (
                      <span className="mt-0.5 flex flex-wrap gap-1">
                        {q.options.map((o) => (
                          <span
                            key={o.key}
                            className="rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground"
                          >
                            {o.value}
                          </span>
                        ))}
                      </span>
                    )}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  );
}

/** The gated records panel — renders real records when unlocked, else an
 *  actionable "grant leads_retrieval" banner. */
function RecordsPanel({
  forms,
  available,
}: {
  forms: LeadgenForm[];
  available: boolean;
}) {
  const withLeads = useMemo(
    () => forms.filter((f) => (f.leads_count ?? 0) > 0),
    [forms],
  );
  const [formId, setFormId] = useState<string>(withLeads[0]?.form_id ?? "");
  const selected = withLeads.find((f) => f.form_id === formId) ?? null;
  const recordsQ = useLeadRecords(
    formId || null,
    selected?.page_id ?? null,
    available,
  );

  if (!available) {
    return (
      <Card className="border-amber-500/30 bg-amber-500/5">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Info className="h-4 w-4 text-amber-600" />
            Registros de leads — requer permissão adicional
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-muted-foreground">
          <p>
            Os dados individuais de cada lead (nome, telefone, e-mail e as
            respostas) exigem a permissão <code className="font-mono">leads_retrieval</code>,
            que o token atual ainda não possui. Os formulários e as contagens
            acima já funcionam sem ela.
          </p>
          <p>
            Para liberar: gere um novo token do Usuário do Sistema com{" "}
            <code className="font-mono">leads_retrieval</code> marcada em{" "}
            <strong>Configurações do Negócio → Usuários do Sistema</strong> e
            atualize a credencial. Assim que liberada, esta seção mostra os
            registros automaticamente.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0">
        <div>
          <CardTitle className="text-base">Registros de leads</CardTitle>
          <CardDescription>Dados enviados em cada formulário</CardDescription>
        </div>
        <select
          className="h-9 rounded-md border bg-background px-2 text-sm"
          value={formId}
          onChange={(e) => setFormId(e.target.value)}
        >
          {withLeads.map((f) => (
            <option key={f.form_id} value={f.form_id}>
              {f.name ?? f.form_id} ({f.leads_count})
            </option>
          ))}
        </select>
      </CardHeader>
      <CardContent>
        {recordsQ.isPending || recordsQ.isFetching ? (
          <AdsLoading label="Carregando registros…" />
        ) : recordsQ.data?.gated ? (
          <p className="py-6 text-center text-sm text-muted-foreground">
            {recordsQ.data.reason}
          </p>
        ) : !recordsQ.data?.data.length ? (
          <p className="py-6 text-center text-sm text-muted-foreground">
            Sem registros neste formulário.
          </p>
        ) : (
          <div className="space-y-3">
            {recordsQ.data.data.map((lead) => (
              <div key={lead.id} className="rounded-lg border p-3">
                <div className="mb-2 flex items-center justify-between text-xs text-muted-foreground">
                  <span>{shortDate(lead.created_time)}</span>
                  <span className="flex items-center gap-2">
                    {lead.platform && <Badge variant="outline">{lead.platform}</Badge>}
                    {lead.campaign_name && (
                      <span className="truncate">{lead.campaign_name}</span>
                    )}
                  </span>
                </div>
                <div className="grid gap-x-6 gap-y-1 sm:grid-cols-2">
                  {lead.field_data.map((fd, i) => (
                    <div key={`${fd.name}-${i}`} className="flex gap-2 text-sm">
                      <span className="shrink-0 text-muted-foreground">{fd.name}:</span>
                      <span className="break-words font-medium">
                        {fd.values.join(", ")}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function AdsLeads() {
  const qc = useQueryClient();
  const formsQ = useLeadForms();

  // Lead ingest — fire the background job, poll it, refetch on completion.
  const sync = useLeadSync();
  const [jobId, setJobId] = useState<string | null>(null);
  const jobQ = useSyncJob(jobId);
  const jobStatus = jobQ.data?.status;
  const syncing = sync.isPending || jobStatus === "running";
  useEffect(() => {
    if (jobId && jobStatus && jobStatus !== "running") {
      qc.invalidateQueries({ queryKey: ["meta-ads", "lead-forms"] });
      qc.invalidateQueries({ queryKey: ["meta-ads", "lead-records"] });
      setJobId(null);
    }
  }, [jobId, jobStatus, qc]);

  const onSync = () =>
    sync.mutate(undefined, { onSuccess: (r) => setJobId(r.job_id) });

  if (formsQ.isPending || formsQ.isFetching) return <AdsLoading />;
  if (formsQ.isError) {
    const msg = (formsQ.error as Error)?.message ?? "";
    // A not-configured / gated account surfaces the actionable state, not
    // a raw error.
    if (/config|503|token/i.test(msg)) return <AdsNotConfigured detail={msg} />;
    return <AdsError message="Não foi possível carregar os leads." onRetry={() => formsQ.refetch()} />;
  }

  const s = formsQ.data;
  if (!s) return <AdsNotConfigured />;
  const avgPerForm =
    s.forms_with_leads > 0 ? Math.round(s.total_leads / s.forms_with_leads) : 0;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Leads</h2>
          <p className="text-sm text-muted-foreground">
            Formulários de cadastro (Instant Forms) das campanhas Meta.
            {s.source === "db"
              ? ` Armazenados no banco · ${syncedLabel(s.last_synced_at)}.`
              : " Ao vivo — clique em Sincronizar para armazenar."}
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={onSync} disabled={syncing}>
          {syncing ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="mr-2 h-4 w-4" />
          )}
          {syncing ? "Sincronizando…" : "Sincronizar leads"}
        </Button>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <MetricCard icon={Users} label="Total de leads" value={formatNumber(s.total_leads)} />
        <MetricCard icon={FileText} label="Formulários ativos" value={formatNumber(s.active_forms)} />
        <MetricCard
          icon={ClipboardList}
          label="Formulários com leads"
          value={formatNumber(s.forms_with_leads)}
        />
        <MetricCard
          icon={Layers}
          label="Média por formulário"
          value={formatNumber(avgPerForm)}
        />
      </div>

      <RecordsPanel forms={s.forms} available={s.records_available} />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Formulários ({formatNumber(s.forms_count)})
          </CardTitle>
          <CardDescription>
            Expanda um formulário para ver seu esquema de campos — a base para
            modelar os leads no banco.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {s.forms.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              Nenhum formulário de cadastro encontrado nas Páginas conectadas.
            </p>
          ) : (
            s.forms
              .filter((f) => (f.leads_count ?? 0) > 0 || f.status === "ACTIVE")
              .map((f) => <FormRow key={f.form_id} form={f} />)
          )}
        </CardContent>
      </Card>
    </div>
  );
}
