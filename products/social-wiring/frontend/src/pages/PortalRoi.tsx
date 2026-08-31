/**
 * PortalRoi — "ROI por Portal", `/portal-roi`.
 *
 * Origin (PROJECT.md §1, 2026-08-03 user quote): "the origem is for me to
 * create statistics based on my marketing portals to evaluate their
 * performances against investments x results." `vw_portal_roi` and the
 * `lead_campanhas`/`lead_vendas` tables that feed it already exist
 * (migration 043) — nothing above them did until this slice: no service, no
 * router, no page, no way to enter a single number.
 *
 * On day one, 23 of the 24 rows in `vw_portal_roi` have real lead volume
 * and ZERO recorded spend. Rendering that absence honestly — "não
 * informado", never "R$ 0,00" — IS the feature (§3.5); the day-one CTA is
 * "Registrar investimento" on 23 of 24 rows, not a chart.
 *
 * States: loading / error / empty (no `lead_sources` at all — organizações
 * that haven't configured a single origem yet) / success. "Empty" is
 * explicitly NOT "sources with no spend" — that is the normal day-one state
 * and renders the full table (§3.5).
 *
 * Route: /portal-roi. Nav entry lives in BOTH NAV_GROUPS and NAV_FALLBACK in
 * App.tsx (the Imóveis precedent — missing either one is a known trap), and
 * needs its own `status_pagina` row (owned by the B1/backend slice) or the
 * seed's `filterNavByPageStatus` gate hides the link with no error anywhere.
 */
import { useState } from "react";
import { AlertCircle, DollarSign, ShoppingCart, Target, TrendingUp } from "lucide-react";

import { StatTile, StatTileRow } from "@noctusai/lib/design-system";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

import { CampanhaManagerDialog } from "@/components/portal-roi/CampanhaManagerDialog";
import { PortaisTable } from "@/components/portal-roi/PortaisTable";
import {
  formatCount,
  formatMoneyOrNaoInformado,
  formatMultipleOrNaoInformado,
  formatPercentOrNaoInformado,
  usePortalRoiResumo,
} from "@/hooks/usePortalRoi";

export default function PortalRoi() {
  const resumo = usePortalRoiResumo();
  const [manager, setManager] = useState<{ origemId: string; origemLabel: string } | null>(null);

  // First load only — `isPending && !data`, never `isLoading` (TanStack v5's
  // `isLoading` is false mid-refetch, so an `isEmpty` branch keyed on it
  // would flash "nenhum portal" over data that still exists) and never a
  // bare `|| isFetching` either: a spend entry via CampanhaManagerDialog
  // invalidates this same resumo query, and the old gate replaced the whole
  // StatTileRow + PortaisTable with a skeleton right after every save.
  const loading = resumo.isPending && !resumo.data;
  const data = resumo.data;
  const portais = data?.portais ?? [];
  // "Empty" = no lead_sources configured at all — NOT "sources with no
  // spend recorded", which is the expected day-one state for 23 of 24 rows.
  const isEmpty = !loading && !resumo.isError && portais.length === 0;

  function openManager(origemId: string, origemLabel: string) {
    setManager({ origemId, origemLabel });
  }

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">ROI por Portal</h1>
        <p className="text-sm text-muted-foreground">
          Investimento x resultados por portal de captação de leads.
        </p>
      </div>

      {resumo.isError ? (
        <ErrorState onRetry={() => resumo.refetch()} />
      ) : loading ? (
        <LoadingState />
      ) : isEmpty ? (
        <EmptyState />
      ) : (
        <>
          <StatTileRow>
            <StatTile
              icon={DollarSign}
              label="Investimento total"
              value={formatMoneyOrNaoInformado(data!.totais.investimento)}
              hint={data!.periodo ? "no período" : "todo o período"}
            />
            <StatTile
              icon={Target}
              label="Leads"
              value={formatCount(data!.totais.total_leads)}
            />
            <StatTile
              icon={ShoppingCart}
              label="Vendas"
              value={formatCount(data!.totais.total_vendas)}
              hint={formatMoneyOrNaoInformado(data!.totais.valor_vendas)}
            />
            <StatTile
              icon={TrendingUp}
              label="CPL médio"
              value={formatMoneyOrNaoInformado(data!.totais.cpl)}
            />
            <StatTile
              icon={TrendingUp}
              label="ROI médio"
              value={formatMultipleOrNaoInformado(data!.totais.roi)}
            />
          </StatTileRow>

          <PortaisTable portais={portais} onManage={openManager} />
        </>
      )}

      {manager && (
        <CampanhaManagerDialog
          open={!!manager}
          onOpenChange={(open) => !open && setManager(null)}
          origemId={manager.origemId}
          origemLabel={manager.origemLabel}
        />
      )}
    </div>
  );
}

// ─── States ─────────────────────────────────────────────────────────────────

function LoadingState() {
  return (
    <div className="space-y-6" data-testid="portal-roi-loading">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-28 w-full rounded-lg" />
        ))}
      </div>
      <Skeleton className="h-96 w-full rounded-lg" />
    </div>
  );
}

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
        <AlertCircle className="h-10 w-10 text-destructive" />
        <p className="font-medium">Não foi possível carregar os dados de ROI por portal.</p>
        <Button variant="outline" onClick={onRetry}>
          Tentar novamente
        </Button>
      </CardContent>
    </Card>
  );
}

function EmptyState() {
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
        <Target className="h-10 w-10 text-muted-foreground" />
        <div>
          <p className="font-medium">Nenhuma origem de lead configurada ainda.</p>
          <p className="text-sm text-muted-foreground">
            Cadastre suas origens (portais, redes sociais…) na Configuração de Leads para
            começar a acompanhar o ROI de cada uma.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
