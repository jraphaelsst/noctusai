/**
 * Email Marketing · Painel — `GET /api/email-marketing/analytics/dashboard`.
 *
 * The product's own mailing engine (Resend-backed), distinct from the
 * Mailchimp-proxy pages under /email-marketing/*. This is the overview:
 * audience size, send volume, and the open/click/bounce rates.
 *
 * Route: /email (App.tsx lazy routes + `email_painel` status_pagina, migration 085).
 */
import {
  AlertCircle,
  MousePointerClick,
  Send,
  TrendingDown,
  Mail,
  MailOpen,
  Users,
} from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

import { useEmDashboard, type EmDashboard } from "@/hooks/useEmailMarketing";

function Stat({
  icon,
  label,
  value,
  hint,
  testId,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  hint: string;
  testId: string;
}) {
  return (
    <Card data-testid={testId}>
      <CardContent className="pt-6">
        <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-muted-foreground">
          {icon}
          {label}
        </div>
        <p className="mt-2 text-3xl font-semibold">{value}</p>
        <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
      </CardContent>
    </Card>
  );
}

const int = (n: number | undefined) =>
  new Intl.NumberFormat("pt-BR").format(n ?? 0);
const pct = (n: number | undefined) => `${(n ?? 0).toFixed(1)}%`;

export default function EmailPainel() {
  const { data, isPending, isFetching, isError } = useEmDashboard();

  // Skeleton ONLY when there is nothing to show — bare `isLoading` is false
  // between retries and would render a blank page on a failed fetch.
  const showSkeleton = isPending || (isFetching && !data);

  const d = (data ?? null) as EmDashboard | null;

  return (
    <div className="flex flex-col gap-6 p-6" data-testid="email-painel-page">
      <header>
        <h1 className="text-lg font-semibold">Email Marketing</h1>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Visão geral do motor de envio próprio — base, volume e engajamento.
        </p>
      </header>

      {showSkeleton ? (
        <div
          className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4"
          data-testid="email-painel-loading"
        >
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <Skeleton key={i} className="h-28 w-full" />
          ))}
        </div>
      ) : isError ? (
        <Card className="border-destructive" data-testid="email-painel-error">
          <CardContent className="flex items-center gap-3 pt-6">
            <AlertCircle className="h-5 w-5 text-destructive" />
            <p className="text-sm text-destructive">
              Erro ao carregar as métricas. Tente novamente.
            </p>
          </CardContent>
        </Card>
      ) : !d ? (
        <div
          className="flex flex-col items-center justify-center gap-3 py-16 text-muted-foreground"
          data-testid="email-painel-empty"
        >
          <Mail className="h-10 w-10 opacity-20" />
          <p className="text-sm font-medium">Sem métricas ainda</p>
          <p className="max-w-sm text-center text-xs">
            Assim que a primeira campanha for enviada, os números aparecem aqui.
          </p>
        </div>
      ) : (
        <div
          className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4"
          data-testid="email-painel-stats"
        >
          <Stat
            testId="stat-contatos"
            icon={<Users className="h-3.5 w-3.5" />}
            label="Contatos"
            value={int(d.total_contacts)}
            hint={`${int(d.active_contacts)} ativos`}
          />
          <Stat
            testId="stat-campanhas"
            icon={<Mail className="h-3.5 w-3.5" />}
            label="Campanhas"
            value={int(d.total_campaigns)}
            hint="criadas até agora"
          />
          <Stat
            testId="stat-enviados"
            icon={<Send className="h-3.5 w-3.5" />}
            label="Enviados"
            value={int(d.total_sent)}
            hint="mensagens que saíram da fila"
          />
          <Stat
            testId="stat-aberturas"
            icon={<MailOpen className="h-3.5 w-3.5" />}
            label="Abertura"
            value={pct(d.open_rate)}
            hint={`${int(d.total_opened)} aberturas`}
          />
          <Stat
            testId="stat-cliques"
            icon={<MousePointerClick className="h-3.5 w-3.5" />}
            label="Cliques"
            value={pct(d.click_rate)}
            hint={`${int(d.total_clicked)} cliques`}
          />
          <Stat
            testId="stat-bounces"
            icon={<TrendingDown className="h-3.5 w-3.5" />}
            label="Bounces"
            value={int(d.total_bounced)}
            hint="entregas recusadas"
          />
        </div>
      )}
    </div>
  );
}
