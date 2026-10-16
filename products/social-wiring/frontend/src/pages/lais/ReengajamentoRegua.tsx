/** Lais › Reengajamento › régua (`/lais/reengajamento/reguas/:id`). */
import { Link, useParams } from "react-router-dom";
import { AlertCircle, ArrowLeft, Loader2 } from "lucide-react";
import { useIsOrgAdmin } from "@noctusai/lib/design-system";

import { Button } from "@/components/ui/button";
import { ReguaRegrasCard } from "@/components/lais/reengajamento/ReguaRegrasCard";
import { TentativasCard } from "@/components/lais/reengajamento/TentativasCard";
import { useRegua } from "@/hooks/useLaisReengajamento";
import { LAIS_LABEL, LAIS_PAGES } from "@/nav/lais";

export default function LaisReengajamentoRegua() {
  const { id } = useParams<{ id: string }>();
  const isAdmin = useIsOrgAdmin();
  const q = useRegua(id);
  const showSkeleton = q.isPending && !q.data;
  const isRefreshing = q.isFetching && !!q.data;

  return (
    <div className="container max-w-4xl space-y-6 py-6">
      <header className="space-y-2">
        <Link
          to={`${LAIS_PAGES.reengajamento.href}?tab=reguas`}
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:underline"
        >
          <ArrowLeft className="h-4 w-4" /> Réguas de reengajamento
        </Link>
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">
            {LAIS_LABEL} · {q.data?.nome ?? "Régua de reengajamento"}
          </h1>
          {isRefreshing && (
            <span className="flex items-center gap-1 text-xs text-muted-foreground" data-testid="regua-refreshing">
              <Loader2 className="h-3 w-3 animate-spin" /> Atualizando…
            </span>
          )}
        </div>
      </header>
      {showSkeleton ? (
        <div className="space-y-4" data-testid="regua-skeleton">
          {[0, 1].map((i) => (
            <div key={i} className="h-40 animate-pulse rounded-lg bg-muted" />
          ))}
        </div>
      ) : q.data ? (
        <>
          <ReguaRegrasCard regua={q.data} isAdmin={isAdmin} />
          <TentativasCard regua={q.data} isAdmin={isAdmin} />
        </>
      ) : (
        <div className="flex flex-col items-center gap-3 py-16 text-muted-foreground" data-testid="regua-erro">
          <AlertCircle className="h-8 w-8 text-destructive" />
          <p className="text-sm">Não foi possível carregar a régua.</p>
          <Button variant="outline" size="sm" onClick={() => q.refetch()}>
            Tentar de novo
          </Button>
        </div>
      )}
    </div>
  );
}
