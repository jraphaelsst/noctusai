/**
 * ImovelInteressadosCard — "Interessados": every lead/cliente ever interested
 * in this imóvel (CONTRACT §4.3), with contact data and last interaction so
 * old leads can be reached again. Paginated (`limit`/`offset`).
 *
 * Loading (lying-loading-state.md): `showSkeleton = isPending && !data`;
 * `isRefreshing = isFetching && !!data` (page change keeps the previous page
 * on screen — `keepPreviousData` in the hook).
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import { ChevronLeft, ChevronRight, Loader2, Mail, MessageCircle } from "lucide-react";

import { whatsappHref } from "@/components/interesses/contato";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useImovelInteressados } from "@/hooks/useImovelRelacionamentos";
import { formatDate } from "@/lib/utils";

const PAGE_SIZE = 20;

const ORIGEM_LABEL: Record<string, string> = {
  lead: "Lead",
  manual: "Manual",
  campanha: "Campanha",
  roteiro: "Roteiro",
  permuta: "Permuta",
};

export function ImovelInteressadosCard({ codigo }: { codigo: string }) {
  const [offset, setOffset] = useState(0);
  const query = useImovelInteressados(codigo, { limit: PAGE_SIZE, offset });

  const items = query.data?.items ?? [];
  const total = query.data?.total ?? 0;
  const showSkeleton = query.isPending && !query.data;
  const isRefreshing = query.isFetching && !!query.data;
  const pagina = Math.floor(offset / PAGE_SIZE) + 1;
  const paginas = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <Card data-testid="interessados-card">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="flex items-center gap-1.5 text-base">
          Interessados{query.data ? ` (${total})` : ""}
          {isRefreshing && (
            <Loader2
              className="h-3 w-3 animate-spin text-muted-foreground"
              data-testid="interessados-refreshing"
            />
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {showSkeleton ? (
          <div className="space-y-2" data-testid="interessados-loading">
            <div className="h-14 animate-pulse rounded-lg bg-muted" />
            <div className="h-14 animate-pulse rounded-lg bg-muted" />
          </div>
        ) : query.isError && !query.data ? (
          <p className="text-sm text-destructive" data-testid="interessados-erro">
            Não foi possível carregar os interessados.
          </p>
        ) : items.length === 0 ? (
          <p className="text-sm italic text-muted-foreground" data-testid="interessados-vazio">
            Ninguém registrou interesse neste imóvel ainda.
          </p>
        ) : (
          <ul className="divide-y rounded-lg border" data-testid="interessados-lista">
            {items.map((row) => {
              const wa = whatsappHref(row.telefone);
              return (
                <li
                  key={row.interesse_id}
                  className="flex flex-wrap items-center gap-x-4 gap-y-1 px-3 py-2"
                  data-testid={`interessado-${row.interesse_id}`}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <Link
                        to={`/clientes/${row.cliente_id}`}
                        className="text-sm font-semibold hover:underline"
                        data-testid="interessado-nome"
                      >
                        {row.nome}
                      </Link>
                      <Badge variant="secondary" className="text-[10px]">
                        {ORIGEM_LABEL[row.origem] ?? row.origem}
                      </Badge>
                      {row.tem_atendimento_aberto && (
                        <Badge className="text-[10px]" data-testid="interessado-atendimento-aberto">
                          Atendimento aberto
                        </Badge>
                      )}
                    </div>
                    <div className="mt-0.5 flex flex-wrap items-center gap-x-3 text-xs text-muted-foreground">
                      {row.telefone ? (
                        wa ? (
                          <a
                            href={wa}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 hover:underline"
                            data-testid="interessado-whatsapp"
                          >
                            <MessageCircle className="h-3 w-3" aria-hidden />
                            {row.telefone}
                          </a>
                        ) : (
                          <span>{row.telefone}</span>
                        )
                      ) : (
                        <span>Sem telefone</span>
                      )}
                      {row.email && (
                        <a
                          href={`mailto:${row.email}`}
                          className="inline-flex items-center gap-1 hover:underline"
                        >
                          <Mail className="h-3 w-3" aria-hidden />
                          {row.email}
                        </a>
                      )}
                    </div>
                  </div>
                  <div className="text-right text-xs text-muted-foreground">
                    <p>
                      Interesse em {formatDate(row.lead_created_at ?? row.interesse_created_at, false)}
                    </p>
                    <p data-testid="interessado-ultimo-contato">
                      Último contato:{" "}
                      {row.ultima_interacao_em ? formatDate(row.ultima_interacao_em, true) : "—"}
                    </p>
                  </div>
                </li>
              );
            })}
          </ul>
        )}

        {total > PAGE_SIZE && (
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>
              Página {pagina} de {paginas}
            </span>
            <div className="flex gap-1">
              <Button
                size="sm"
                variant="outline"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                data-testid="interessados-anterior"
              >
                <ChevronLeft className="h-4 w-4" />
                Anterior
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={offset + PAGE_SIZE >= total}
                onClick={() => setOffset(offset + PAGE_SIZE)}
                data-testid="interessados-proxima"
              >
                Próxima
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default ImovelInteressadosCard;
