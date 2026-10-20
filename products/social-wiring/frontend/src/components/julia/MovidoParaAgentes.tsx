/**
 * Read-only notice for a Julia page that moved to the agents app (julia-v2 Q1/Q6): same route, so old bookmarks keep
 * working, but nothing is edited here any more and SW shows no content of the moved page. The data is NOT deleted.
 */
import { AlertCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ConfigurarNoAgentes } from "@/components/julia/ConfigurarNoAgentes";
import { useJuliaRoteamento } from "@/hooks/useJuliaRoteamento";
import { JULIA_LABEL } from "@/nav/julia";

export function MovidoParaAgentes({ pagina, explicacao }: { pagina: string; explicacao: string }) {
  const q = useJuliaRoteamento();
  const showSkeleton = q.isPending && !q.data;
  return (
    <div className="container max-w-4xl space-y-6 py-6">
      <header>
        <h1 className="text-2xl font-bold">
          {JULIA_LABEL} · {pagina}
        </h1>
      </header>
      <Card data-testid="movido-para-agentes">
        <CardContent className="space-y-3 py-6">
          <p className="text-sm font-medium">Agora é configurado no app de agentes.</p>
          <p className="text-sm text-muted-foreground">{explicacao}</p>
          {showSkeleton ? (
            <div className="h-5 w-64 animate-pulse rounded bg-muted" data-testid="movido-skeleton" />
          ) : q.data ? (
            <ConfigurarNoAgentes agentsUrl={q.data.agents_url} />
          ) : (
            <div className="flex items-center gap-3 text-sm" data-testid="movido-erro">
              <AlertCircle className="h-4 w-4 text-destructive" />
              <span>Não foi possível obter o endereço do app de agentes.</span>
              <Button variant="outline" size="sm" onClick={() => q.refetch()}>
                Tentar de novo
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
