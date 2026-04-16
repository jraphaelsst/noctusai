import { useDashboardMetrics, DashboardMetrics } from "@/hooks/useAnalytics";
import { Loader2, Users, Send, MailOpen, MousePointerClick, Megaphone, AlertCircle } from "lucide-react";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const METRIC_CARDS = [
  { key: "total_contacts" as const, label: "Total Contatos", sub: "Contatos ativos na base", icon: Users, format: "number" },
  { key: "total_sent" as const, label: "Enviados", sub: "E-mails enviados", icon: Send, format: "number" },
  { key: "open_rate" as const, label: "Taxa de Abertura", sub: "Media das campanhas", icon: MailOpen, format: "percent" },
  { key: "click_rate" as const, label: "Taxa de Clique", sub: "Click-through rate medio", icon: MousePointerClick, format: "percent" },
];

function formatMetric(value: number, format: string) {
  if (format === "percent") return `${(value * 100).toFixed(1)}%`;
  return value.toLocaleString("pt-BR");
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function Dashboard() {
  const { data, isLoading, isError } = useDashboardMetrics();
  const metrics: DashboardMetrics | null = data?.data ?? null;

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
        <p className="text-sm text-muted-foreground">Carregando metricas...</p>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3">
        <AlertCircle className="h-8 w-8 text-destructive" />
        <p className="text-sm text-muted-foreground">Erro ao carregar metricas. Tente novamente.</p>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">Dashboard</h1>
        <p className="text-sm text-muted-foreground">
          Visao geral das suas campanhas de e-mail e metricas de engajamento.
        </p>
      </div>

      {/* Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {METRIC_CARDS.map((card) => {
          const Icon = card.icon;
          const value = metrics ? metrics[card.key] : 0;
          return (
            <div key={card.key} className="rounded-lg border border-border bg-card p-5 space-y-2">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-muted-foreground">{card.label}</p>
                <Icon className="h-4 w-4 text-muted-foreground" />
              </div>
              <p className="text-3xl font-bold text-foreground">
                {metrics ? formatMetric(value, card.format) : "--"}
              </p>
              <p className="text-xs text-muted-foreground">{card.sub}</p>
            </div>
          );
        })}
      </div>

      {/* Campaigns Summary */}
      <div className="space-y-4">
        <h2 className="text-lg font-semibold text-foreground">Resumo</h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="rounded-lg border border-border bg-card p-5 space-y-1">
            <div className="flex items-center gap-2">
              <Megaphone className="h-4 w-4 text-muted-foreground" />
              <p className="text-sm font-medium text-muted-foreground">Campanhas</p>
            </div>
            <p className="text-2xl font-bold text-foreground">
              {metrics?.total_campaigns ?? 0}
            </p>
          </div>
          <div className="rounded-lg border border-border bg-card p-5 space-y-1">
            <div className="flex items-center gap-2">
              <Users className="h-4 w-4 text-muted-foreground" />
              <p className="text-sm font-medium text-muted-foreground">Contatos Ativos</p>
            </div>
            <p className="text-2xl font-bold text-foreground">
              {metrics?.active_contacts ?? 0}
            </p>
          </div>
          <div className="rounded-lg border border-border bg-card p-5 space-y-1">
            <div className="flex items-center gap-2">
              <AlertCircle className="h-4 w-4 text-muted-foreground" />
              <p className="text-sm font-medium text-muted-foreground">Bounced</p>
            </div>
            <p className="text-2xl font-bold text-foreground">
              {metrics?.total_bounced ?? 0}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
