/**
 * "Visitas sem resposta" — roteiros whose visit date passed with nobody having
 * answered "a visita aconteceu?" (CONTRACT sw-lead-to-contract §3.2). Each row
 * opens the card. The count doubles as the badge in the card's header.
 */
import { Link } from "react-router-dom";

import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useRoteirosPendentesFeedback } from "@/hooks/useRoteirosFeedback";

function dataBR(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
}

export function VisitasSemResposta() {
  const { data, isPending, isFetching, isError } = useRoteirosPendentesFeedback();
  const showSkeleton = isPending && !data;
  const isRefreshing = isFetching && !!data;

  return (
    <Card data-testid="painel-visitas-sem-resposta">
      <CardContent className="p-5">
        <div className="mb-3 flex items-center justify-between gap-2">
          <h2 className="font-semibold">Visitas sem resposta</h2>
          {data && data.length > 0 && (
            <span
              className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-900"
              data-testid="painel-visitas-sem-resposta-badge"
            >
              {data.length}
              {isRefreshing ? "…" : ""}
            </span>
          )}
        </div>
        {showSkeleton ? (
          <div data-testid="painel-visitas-sem-resposta-loading">
            <Skeleton className="h-16" />
          </div>
        ) : isError || !data ? (
          <p className="py-6 text-center text-sm text-destructive">
            Não foi possível carregar as visitas.
          </p>
        ) : data.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">
            Nenhuma visita aguardando resposta.
          </p>
        ) : (
          <ul className="divide-y">
            {data.map((r) => (
              <li key={r.roteiro_id}>
                <Link
                  to={`/clientes/${r.cliente_id}?aba=roteiros`}
                  className="flex items-center justify-between gap-3 py-2.5 hover:bg-muted/40"
                  data-testid={`painel-visita-pendente-${r.roteiro_id}`}
                >
                  <p className="min-w-0 truncate text-sm font-medium">
                    Visita de {r.cliente_nome || "cliente"} aconteceu?
                  </p>
                  <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                    {dataBR(r.data_visita)}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
