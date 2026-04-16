import { useDashboardMetrics, DashboardMetrics } from "@/hooks/useAnalytics";
import {
  Loader2,
  AlertCircle,
  Users,
  Send,
  MailOpen,
  MousePointerClick,
  UserCheck,
  AlertTriangle,
  Megaphone,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtPct(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function fmtNum(value: number) {
  return value.toLocaleString("pt-BR");
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function Analytics() {
  const { data, isLoading, isError } = useDashboardMetrics();
  const m: DashboardMetrics | null = data?.data ?? null;

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
        <p className="text-sm text-muted-foreground">Carregando analytics...</p>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3">
        <AlertCircle className="h-8 w-8 text-destructive" />
        <p className="text-sm text-muted-foreground">Erro ao carregar analytics. Tente novamente.</p>
      </div>
    );
  }

  const mainCards = [
    { label: "Total Contatos", value: m ? fmtNum(m.total_contacts) : "--", icon: Users, sub: "Base de contatos" },
    { label: "Total Enviados", value: m ? fmtNum(m.total_sent) : "--", icon: Send, sub: "E-mails enviados" },
    { label: "Taxa de Abertura", value: m ? fmtPct(m.open_rate) : "--%", icon: MailOpen, sub: "Media geral" },
    { label: "Taxa de Clique", value: m ? fmtPct(m.click_rate) : "--%", icon: MousePointerClick, sub: "Click-through rate" },
  ];

  const extraCards = [
    { label: "Contatos Ativos", value: m ? fmtNum(m.active_contacts) : "--", icon: UserCheck },
    { label: "Total Bounced", value: m ? fmtNum(m.total_bounced) : "--", icon: AlertTriangle },
    { label: "Total Campanhas", value: m ? fmtNum(m.total_campaigns) : "--", icon: Megaphone },
  ];

  // Visual bar representation of open_rate vs click_rate
  const openPct = m ? m.open_rate * 100 : 0;
  const clickPct = m ? m.click_rate * 100 : 0;
  const maxBar = Math.max(openPct, clickPct, 1); // avoid /0

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">Analytics</h1>
        <p className="text-sm text-muted-foreground">
          Acompanhe as metricas de desempenho das suas campanhas e automacoes de e-mail.
        </p>
      </div>

      {/* Main Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {mainCards.map((card) => {
          const Icon = card.icon;
          return (
            <div key={card.label} className="rounded-lg border border-border bg-card p-5 space-y-2">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-muted-foreground">{card.label}</p>
                <Icon className="h-4 w-4 text-muted-foreground" />
              </div>
              <p className="text-3xl font-bold text-foreground">{card.value}</p>
              <p className="text-xs text-muted-foreground">{card.sub}</p>
            </div>
          );
        })}
      </div>

      {/* Open Rate vs Click Rate visual */}
      <div className="rounded-lg border border-border bg-card p-5 space-y-4">
        <h2 className="text-lg font-semibold text-foreground">Abertura vs Clique</h2>
        <div className="space-y-4">
          <div className="space-y-1">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Taxa de Abertura</span>
              <span className="font-medium text-foreground">{m ? fmtPct(m.open_rate) : "--%"}</span>
            </div>
            <div className="h-6 w-full rounded bg-muted overflow-hidden">
              <div
                className="h-full rounded bg-blue-500 transition-all duration-700"
                style={{ width: `${(openPct / maxBar) * 100}%` }}
              />
            </div>
          </div>
          <div className="space-y-1">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Taxa de Clique</span>
              <span className="font-medium text-foreground">{m ? fmtPct(m.click_rate) : "--%"}</span>
            </div>
            <div className="h-6 w-full rounded bg-muted overflow-hidden">
              <div
                className="h-full rounded bg-green-500 transition-all duration-700"
                style={{ width: `${(clickPct / maxBar) * 100}%` }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Additional Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {extraCards.map((card) => {
          const Icon = card.icon;
          return (
            <div key={card.label} className="rounded-lg border border-border bg-card p-5 space-y-1">
              <div className="flex items-center gap-2">
                <Icon className="h-4 w-4 text-muted-foreground" />
                <p className="text-sm font-medium text-muted-foreground">{card.label}</p>
              </div>
              <p className="text-2xl font-bold text-foreground">{card.value}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
