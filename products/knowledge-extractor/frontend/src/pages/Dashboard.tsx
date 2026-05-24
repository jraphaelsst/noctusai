/**
 * Dashboard — overview of the processed-knowledge catalog + recent runs.
 *
 *   1. KPI cards row (Módulos / Aulas / Transcrições / Resumos)
 *   2. "Processamentos recentes" list (latest runs, live-polled)
 *
 * Read-only; data from GET /api/catalog totals + GET /api/runs.
 */
import {
  BookOpen,
  FileText,
  GraduationCap,
  Layers,
  RefreshCw,
  ScrollText,
  type LucideIcon,
} from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

import { useCatalog } from "@/hooks/useCatalog";
import { useRuns } from "@/hooks/useRuns";
import { RunStatusBadge } from "@/components/RunStatusBadge";

function KpiCard({
  icon: Icon,
  label,
  value,
  loading,
}: {
  icon: LucideIcon;
  label: string;
  value: number;
  loading: boolean;
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-4 p-5">
        <div className="rounded-md bg-primary/10 p-3">
          <Icon className="h-5 w-5 text-primary" />
        </div>
        <div className="min-w-0">
          <p className="text-xs uppercase tracking-wide text-muted-foreground">
            {label}
          </p>
          {loading ? (
            <Skeleton className="mt-1 h-7 w-16" />
          ) : (
            <p className="text-2xl font-semibold tabular-nums text-foreground">
              {value.toLocaleString("pt-BR")}
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export default function Dashboard() {
  const { data: catalog, loading: catalogLoading, error: catalogError, reload } =
    useCatalog();
  const { data: runs, loading: runsLoading } = useRuns(4000);

  const recent = runs.slice(0, 8);

  return (
    <div className="container max-w-6xl space-y-6 py-6">
      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex items-center gap-3">
          <GraduationCap className="h-6 w-6 text-primary" />
          <div>
            <h1 className="text-2xl font-semibold text-foreground">Dashboard</h1>
            <p className="text-sm text-muted-foreground">
              Visão geral do conhecimento processado + atividade recente.
            </p>
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={reload}>
          <RefreshCw className="mr-2 h-4 w-4" />
          Atualizar
        </Button>
      </div>

      {catalogError && (
        <Card>
          <CardContent className="p-4 text-sm text-destructive">
            {catalogError.message}
          </CardContent>
        </Card>
      )}

      {/* KPI row */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          icon={Layers}
          label="Módulos"
          value={catalog.totals.modules}
          loading={catalogLoading}
        />
        <KpiCard
          icon={BookOpen}
          label="Aulas"
          value={catalog.totals.lessons}
          loading={catalogLoading}
        />
        <KpiCard
          icon={FileText}
          label="Transcrições"
          value={catalog.totals.transcripts}
          loading={catalogLoading}
        />
        <KpiCard
          icon={ScrollText}
          label="Resumos"
          value={catalog.totals.summaries}
          loading={catalogLoading}
        />
      </div>

      {/* Recent runs */}
      <Card>
        <CardHeader>
          <CardTitle>Processamentos recentes</CardTitle>
          <CardDescription>
            Os últimos jobs de extração — atualiza automaticamente.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {runsLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-12 rounded" />
              ))}
            </div>
          ) : recent.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-8 text-center text-sm text-muted-foreground">
              <FileText className="h-8 w-8" />
              Nenhum processamento ainda. Vá em Processamentos para iniciar.
            </div>
          ) : (
            <div className="divide-y divide-border">
              {recent.map((run) => (
                <div
                  key={run.run_id}
                  className="flex items-center justify-between gap-4 py-3"
                >
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-mono text-sm text-foreground">
                      {run.run_id}
                    </div>
                    <div className="truncate text-xs text-muted-foreground">
                      {run.mode} · iniciado{" "}
                      {new Date(run.started_at).toLocaleString("pt-BR")}
                      {run.detail ? ` · ${run.detail}` : ""}
                    </div>
                  </div>
                  <RunStatusBadge status={run.status} />
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
