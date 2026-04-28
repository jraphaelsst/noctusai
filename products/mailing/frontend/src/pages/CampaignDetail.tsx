import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { toast } from "sonner";
import {
  useCampaign,
  useSendCampaign,
  usePauseCampaign,
  useCancelCampaign,
  useScheduleCampaign,
  Campaign,
  CampaignStats,
} from "@/hooks/useCampaigns";
import { Loader2, AlertCircle, ArrowLeft, Send, Pause, XCircle, Clock, Play } from "lucide-react";
import { CampaignDebriefSection } from "@/components/CampaignDebriefSection";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function pct(a: number, b: number) {
  if (!b) return "0%";
  return `${((a / b) * 100).toFixed(1)}%`;
}

function fmtDate(iso?: string) {
  if (!iso) return "--";
  return new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

const STATUS_BADGE: Record<Campaign["status"], { label: string; cls: string }> = {
  rascunho: { label: "Rascunho", cls: "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300" },
  agendada: { label: "Agendada", cls: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300" },
  enviando: { label: "Enviando", cls: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300" },
  enviada: { label: "Enviada", cls: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300" },
  pausada: { label: "Pausada", cls: "bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-300" },
  cancelada: { label: "Cancelada", cls: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300" },
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function CampaignDetail() {
  const { id } = useParams<{ id: string }>();
  const { data, isLoading, isError } = useCampaign(id!);
  const campaign: Campaign | null = data?.data ?? null;
  const stats: CampaignStats | null = campaign?.stats ?? null;

  const sendMut = useSendCampaign();
  const pauseMut = usePauseCampaign();
  const cancelMut = useCancelCampaign();
  const scheduleMut = useScheduleCampaign();

  const [scheduleDate, setScheduleDate] = useState("");
  const [showSchedule, setShowSchedule] = useState(false);

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
        <p className="text-sm text-muted-foreground">Carregando campanha...</p>
      </div>
    );
  }

  if (isError || !campaign) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3">
        <AlertCircle className="h-8 w-8 text-destructive" />
        <p className="text-sm text-muted-foreground">Erro ao carregar campanha.</p>
        <Link to="/campaigns" className="text-sm text-primary hover:underline">Voltar para campanhas</Link>
      </div>
    );
  }

  const badge = STATUS_BADGE[campaign.status];
  const progressPct = campaign.total_recipients ? (campaign.total_sent / campaign.total_recipients) * 100 : 0;
  const anyPending = sendMut.isPending || pauseMut.isPending || cancelMut.isPending || scheduleMut.isPending;

  function handleSend() {
    sendMut.mutate(id!, {
      onSuccess: () => toast.success("Campanha iniciada!"),
      onError: () => toast.error("Erro ao enviar campanha."),
    });
  }

  function handlePause() {
    pauseMut.mutate(id!, {
      onSuccess: () => toast.success("Campanha pausada."),
      onError: () => toast.error("Erro ao pausar campanha."),
    });
  }

  function handleCancel() {
    cancelMut.mutate(id!, {
      onSuccess: () => toast.success("Campanha cancelada."),
      onError: () => toast.error("Erro ao cancelar campanha."),
    });
  }

  function handleSchedule() {
    if (!scheduleDate) return;
    scheduleMut.mutate(
      { id: id!, scheduled_at: new Date(scheduleDate).toISOString() },
      {
        onSuccess: () => { toast.success("Campanha agendada!"); setShowSchedule(false); },
        onError: () => toast.error("Erro ao agendar campanha."),
      }
    );
  }

  // Stats cards data
  const statCards = [
    { label: "Destinatarios", value: campaign.total_recipients.toLocaleString("pt-BR") },
    { label: "Enviados", value: campaign.total_sent.toLocaleString("pt-BR") },
    { label: "Aberturas", value: stats ? stats.opened.toLocaleString("pt-BR") : "--" },
    { label: "Cliques", value: stats ? stats.clicked.toLocaleString("pt-BR") : "--" },
    { label: "Bounced", value: stats ? stats.bounced.toLocaleString("pt-BR") : "--" },
    { label: "Falharam", value: stats ? stats.failed.toLocaleString("pt-BR") : "--" },
  ];

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <Link to="/campaigns" className="text-muted-foreground hover:text-foreground transition-colors">
            <ArrowLeft className="h-5 w-5" />
          </Link>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold text-foreground">{campaign.nome}</h1>
              <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${badge.cls}`}>
                {badge.label}
              </span>
            </div>
            <p className="text-sm text-muted-foreground">Criada em {fmtDate(campaign.created_at)}</p>
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex gap-2 flex-wrap">
          {campaign.status === "rascunho" && (
            <>
              <button
                onClick={handleSend}
                disabled={anyPending}
                className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
              >
                <Send className="h-4 w-4" /> Enviar Agora
              </button>
              <button
                onClick={() => setShowSchedule(!showSchedule)}
                disabled={anyPending}
                className="inline-flex items-center gap-2 rounded-md border border-input bg-background px-4 py-2 text-sm font-medium hover:bg-muted transition-colors disabled:opacity-50"
              >
                <Clock className="h-4 w-4" /> Agendar
              </button>
            </>
          )}
          {campaign.status === "agendada" && (
            <button
              onClick={handleCancel}
              disabled={anyPending}
              className="inline-flex items-center gap-2 rounded-md bg-destructive px-4 py-2 text-sm font-medium text-destructive-foreground hover:bg-destructive/90 transition-colors disabled:opacity-50"
            >
              <XCircle className="h-4 w-4" /> Cancelar
            </button>
          )}
          {campaign.status === "enviando" && (
            <button
              onClick={handlePause}
              disabled={anyPending}
              className="inline-flex items-center gap-2 rounded-md bg-orange-500 px-4 py-2 text-sm font-medium text-white hover:bg-orange-600 transition-colors disabled:opacity-50"
            >
              <Pause className="h-4 w-4" /> Pausar
            </button>
          )}
          {campaign.status === "pausada" && (
            <button
              onClick={handleSend}
              disabled={anyPending}
              className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              <Play className="h-4 w-4" /> Retomar
            </button>
          )}
          {campaign.status === "enviada" && campaign.completed_at && (
            <p className="text-sm text-muted-foreground self-center">
              Concluida em {fmtDate(campaign.completed_at)}
            </p>
          )}
        </div>
      </div>

      {/* Schedule picker */}
      {showSchedule && (
        <div className="flex items-end gap-3 rounded-lg border border-border bg-card p-4 max-w-md">
          <div className="flex-1">
            <label className="mb-1 block text-sm font-medium text-foreground">Data e Hora</label>
            <input
              type="datetime-local"
              value={scheduleDate}
              onChange={(e) => setScheduleDate(e.target.value)}
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>
          <button
            onClick={handleSchedule}
            disabled={!scheduleDate || scheduleMut.isPending}
            className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
          >
            {scheduleMut.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Confirmar
          </button>
        </div>
      )}

      {/* Stats Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
        {statCards.map((s) => (
          <div key={s.label} className="rounded-lg border border-border bg-card p-4 space-y-1">
            <p className="text-xs font-medium text-muted-foreground">{s.label}</p>
            <p className="text-2xl font-bold text-foreground">{s.value}</p>
          </div>
        ))}
      </div>

      {/* Progress Bar */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">Progresso de envio</span>
          <span className="font-medium text-foreground">{progressPct.toFixed(1)}%</span>
        </div>
        <div className="h-3 w-full rounded-full bg-muted overflow-hidden">
          <div
            className="h-full rounded-full bg-primary transition-all duration-500"
            style={{ width: `${Math.min(progressPct, 100)}%` }}
          />
        </div>
        <p className="text-xs text-muted-foreground">
          {campaign.total_sent.toLocaleString("pt-BR")} de {campaign.total_recipients.toLocaleString("pt-BR")} enviados
        </p>
      </div>

      {/* AI campaign-debrief — gated by `mailing.campaign_debrief` consent.
          Only shown for sent campaigns; the backend will 412 otherwise. */}
      {campaign.status === "enviada" && id && (
        <CampaignDebriefSection campaignId={id} />
      )}

      {/* Campaign Info */}
      <div className="rounded-lg border border-border bg-card p-5 space-y-3">
        <h2 className="text-lg font-semibold text-foreground">Informacoes da Campanha</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
          <div>
            <p className="text-muted-foreground">Template</p>
            <p className="font-medium text-foreground">{campaign.template_id ?? "--"}</p>
          </div>
          <div>
            <p className="text-muted-foreground">Lista</p>
            <p className="font-medium text-foreground">{campaign.list_id ?? "--"}</p>
          </div>
          <div>
            <p className="text-muted-foreground">Agendada para</p>
            <p className="font-medium text-foreground">{fmtDate(campaign.scheduled_at)}</p>
          </div>
          <div>
            <p className="text-muted-foreground">Iniciada em</p>
            <p className="font-medium text-foreground">{fmtDate(campaign.started_at)}</p>
          </div>
        </div>
      </div>
    </div>
  );
}
