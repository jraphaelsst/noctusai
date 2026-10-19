/**
 * Lais › Agente (`/lais/agente`) — the Julia control page (contract 6 + 11).
 *
 * Four cards over ONE query (`GET /api/lais/agente`): the Agents link (token +
 * health), the per-connection switch, the handoff target (both in
 * `JuliaConexoesCard`) and the privacy notice editor. Reads are for any org
 * member; every write is core owner/admin (server-enforced — `useIsOrgAdmin`
 * only decides what the UI offers).
 *
 * Loading = two signals off `data` (never `isLoading`):
 * `showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data`.
 */
import { AlertCircle, Loader2 } from "lucide-react";
import { useIsOrgAdmin } from "@noctusai/lib/design-system";

import { Button } from "@/components/ui/button";
import { AgentsLinkCard } from "@/components/lais/AgentsLinkCard";
import { AvisoPrivacidadeCard } from "@/components/lais/AvisoPrivacidadeCard";
import { JuliaConexoesCard } from "@/components/lais/JuliaConexoesCard";
import { useLaisAgente } from "@/hooks/useLaisAgente";
import { LAIS_LABEL, LAIS_PAGES } from "@/nav/lais";

export default function LaisAgente() {
  const isAdmin = useIsOrgAdmin();
  const q = useLaisAgente();
  const showSkeleton = q.isPending && !q.data;
  const isRefreshing = q.isFetching && !!q.data;

  return (
    <div className="container max-w-4xl space-y-6 py-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">
            {LAIS_LABEL} · {LAIS_PAGES.agente.name}
          </h1>
          <p className="text-sm text-muted-foreground">
            A Julia atende os leads novos no WhatsApp. Aqui você liga, desliga e acompanha o agente.
          </p>
        </div>
        {isRefreshing && (
          <span className="flex items-center gap-1 text-xs text-muted-foreground" data-testid="agente-refreshing">
            <Loader2 className="h-3 w-3 animate-spin" /> Atualizando…
          </span>
        )}
      </header>

      {showSkeleton ? (
        <div className="space-y-4" data-testid="agente-skeleton">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-40 animate-pulse rounded-lg bg-muted" />
          ))}
        </div>
      ) : q.data ? (
        <>
          <AgentsLinkCard data={q.data} isAdmin={isAdmin} />
          <JuliaConexoesCard data={q.data} isAdmin={isAdmin} />
          <AvisoPrivacidadeCard isAdmin={isAdmin} />
        </>
      ) : (
        <div className="flex flex-col items-center gap-3 py-16 text-muted-foreground" data-testid="agente-erro">
          <AlertCircle className="h-8 w-8 text-destructive" />
          <p className="text-sm">Não foi possível carregar os dados da Julia.</p>
          <Button variant="outline" size="sm" onClick={() => q.refetch()}>
            Tentar de novo
          </Button>
        </div>
      )}
    </div>
  );
}
