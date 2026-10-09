/**
 * VisitadasLista — the imóveis actually visited on an answered roteiro, each
 * with a "Gerar proposta" button (CONTRACT sw-lead-to-contract §3.4).
 *
 * Smart component (owns its two hooks) so `RoteirosSection` stays
 * presentational: the section receives it through a render slot.
 * The button is disabled with "Proposta já criada" once a proposta exists.
 *
 * Loading: `showSkeleton = isPending && !data`, `isRefreshing = isFetching &&
 * !!data` — never `isLoading`.
 */
import { FilePlus2, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useGerarProposta } from "@/hooks/useGerarProposta";
import { useVisitadas } from "@/hooks/useRoteirosFeedback";
import { toastServerError } from "@/lib/erroServidor";

export function VisitadasLista({ clienteId, roteiroId }: { clienteId: string; roteiroId: string }) {
  const { data, isPending, isFetching, isError } = useVisitadas(clienteId, roteiroId);
  const gerar = useGerarProposta(clienteId);
  const showSkeleton = isPending && !data;
  const isRefreshing = isFetching && !!data;

  return (
    <div className="space-y-2 border-t p-3" data-testid={`visitadas-${roteiroId}`}>
      <div className="flex items-center gap-1.5">
        <h4 className="text-sm font-semibold">Imóveis visitados</h4>
        {isRefreshing && <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />}
      </div>
      {showSkeleton ? (
        <div className="h-10 animate-pulse rounded-md bg-muted" data-testid="visitadas-loading" />
      ) : isError || !data ? (
        <p className="text-sm text-destructive">Não foi possível carregar os imóveis visitados.</p>
      ) : data.length === 0 ? (
        <p className="text-sm italic text-muted-foreground" data-testid="visitadas-vazio">
          Nenhum imóvel foi visitado neste roteiro.
        </p>
      ) : (
        <ul className="divide-y">
          {data.map((v) => (
            <li key={v.visita_id} className="flex items-center justify-between gap-3 py-2">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">{v.titulo || v.imovel_codigo}</p>
                <p className="text-xs text-muted-foreground">{v.imovel_codigo}</p>
              </div>
              <Button
                size="sm"
                variant={v.proposta ? "outline" : "default"}
                disabled={!!v.proposta || (gerar.isPending && gerar.variables === v.visita_id)}
                onClick={() =>
                  gerar.mutate(v.visita_id, {
                    onError: (err) => toastServerError(err, "Não foi possível gerar a proposta."),
                  })
                }
                data-testid={`gerar-proposta-${v.visita_id}`}
              >
                {!v.proposta && <FilePlus2 className="mr-1.5 h-3.5 w-3.5" aria-hidden />}
                {v.proposta ? "Proposta já criada" : "Gerar proposta"}
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
