/**
 * FbVisaoGeral — Facebook "Visão geral" subtab: page insights.
 *
 * Metric names are read generically from `insights.metrics` (a
 * `Record<string, number>`) — the Wave 3 contract flags that many FB Page
 * Insights metrics were DEPRECATED 2026-06-15, so this renders whatever the
 * backend returns rather than hard-coding a metric list that may 400/dry up
 * mid-flight (see delivery note).
 */
import { useState } from "react";
import { BarChart3, CircleAlert } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { MetricCard } from "@/components/MetricCard";
import { formatNumber } from "@/lib/formatNumber";
import { useActiveMetaAccountId, useFbInsights } from "@/hooks/useMeta";
import {
  FbContextError,
  FbContextLoading,
  FbNoPages,
  FbPageSelect,
  useFbPages,
} from "./FbPageSelect";

function InsightsPanel({ accountId, pageId }: { accountId: string; pageId: string }) {
  // `isPending`, not `isLoading` — v5's `isLoading` goes FALSE mid-refetch
  // and would unmount these KPI tiles on every background refresh.
  // → KB § PATTERNS/frontend/lying-loading-state.md
  const { data, isPending, isError } = useFbInsights(accountId, pageId);

  if (isPending) {
    return (
      <div
        className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4"
        data-testid="fb-insights-loading"
      >
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-24 rounded-md" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div
        className="flex items-center gap-2 rounded-md border border-dashed p-4 text-sm text-destructive"
        data-testid="fb-insights-error"
      >
        <CircleAlert className="h-4 w-4 shrink-0" />
        Erro ao carregar métricas da página.
      </div>
    );
  }

  const entries = Object.entries(data?.metrics ?? {});

  if (entries.length === 0) {
    return (
      <div
        className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground"
        data-testid="fb-insights-empty"
      >
        Sem métricas disponíveis para esta página no momento.
      </div>
    );
  }

  return (
    <div
      className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4"
      data-testid="fb-insights-success"
    >
      {entries.map(([key, value]) => (
        <MetricCard key={key} icon={BarChart3} label={key.replace(/_/g, " ")} value={formatNumber(value)} />
      ))}
    </div>
  );
}

export default function FbVisaoGeral() {
  const accountId = useActiveMetaAccountId();
  // `isPending`, not `isLoading` — same rule, page-context fetch.
  const { data: context, isPending, isError } = useFbPages(accountId);
  const [pageId, setPageId] = useState<string | null>(null);

  if (!accountId) {
    return (
      <Card>
        <CardContent
          className="p-6 text-center text-sm text-muted-foreground"
          data-testid="fb-overview-no-account"
        >
          Selecione uma conta conectada acima para ver a visão geral do
          Facebook.
        </CardContent>
      </Card>
    );
  }

  if (isPending) return <FbContextLoading />;
  if (isError) return <FbContextError />;

  const pages = context?.pages ?? [];
  if (pages.length === 0) return <FbNoPages />;

  const resolvedPageId = pageId ?? pages[0].id;

  return (
    <Card>
      <CardHeader className="space-y-3">
        <CardTitle>Visão geral da página</CardTitle>
        <FbPageSelect
          accountId={accountId}
          pages={pages}
          selectedId={pageId}
          onSelect={setPageId}
        />
      </CardHeader>
      <CardContent>
        <InsightsPanel accountId={accountId} pageId={resolvedPageId} />
      </CardContent>
    </Card>
  );
}
