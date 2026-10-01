/**
 * ImovelSimilaresCard — "Imóveis similares" by the PROPERTY profile
 * (CONTRACT §4.4, permutas matching engine): rows like the busca rows plus the
 * score and reason chips. Action per row: "Adicionar ao interesse de…" — pick
 * one of this imóvel's interessados, then `POST /api/clientes/{id}/interesses`
 * (§4.1, origem "manual") with the similar's código.
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import { Loader2, UserPlus } from "lucide-react";
import { toast } from "sonner";

import { ImovelLinhaInfo } from "@/components/interesses/ImovelLinhaInfo";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useInteresseMutations } from "@/hooks/useInteresses";
import { useImovelInteressados, useImovelSimilares } from "@/hooks/useImovelRelacionamentos";
import type { SimilarItem } from "@/types/interesses";

function mensagemDe(err: unknown, fallback: string) {
  return err instanceof Error && err.message ? err.message : fallback;
}

export function ImovelSimilaresCard({ codigo }: { codigo: string }) {
  const query = useImovelSimilares(codigo);
  const [alvo, setAlvo] = useState<SimilarItem | null>(null);

  const items = query.data?.items ?? [];
  const showSkeleton = query.isPending && !query.data;
  const isRefreshing = query.isFetching && !!query.data;

  return (
    <Card data-testid="similares-card">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="flex items-center gap-1.5 text-base">
          Imóveis similares
          {isRefreshing && (
            <Loader2
              className="h-3 w-3 animate-spin text-muted-foreground"
              data-testid="similares-refreshing"
            />
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {showSkeleton ? (
          <div className="space-y-2" data-testid="similares-loading">
            <div className="h-16 animate-pulse rounded-lg bg-muted" />
            <div className="h-16 animate-pulse rounded-lg bg-muted" />
          </div>
        ) : query.isError && !query.data ? (
          <p className="text-sm text-destructive" data-testid="similares-erro">
            Não foi possível carregar os imóveis similares.
          </p>
        ) : items.length === 0 ? (
          <p className="text-sm italic text-muted-foreground" data-testid="similares-vazio">
            {query.data?.aviso ?? "Nenhum imóvel similar encontrado."}
          </p>
        ) : (
          <ul className="divide-y rounded-lg border" data-testid="similares-lista">
            {items.map((item) => (
              <li
                key={item.codigo}
                className="flex items-start gap-3 px-3 py-2"
                data-testid={`similar-${item.codigo}`}
              >
                <ImovelLinhaInfo
                  imovel={item}
                  extra={
                    <div className="mt-1 flex flex-wrap items-center gap-1">
                      <Badge className="text-[10px]" data-testid="similar-score">
                        {Math.round(item.score)} pts
                      </Badge>
                      {item.reasons.map((r) => (
                        <Badge key={r} variant="outline" className="text-[10px] font-normal">
                          {r}
                        </Badge>
                      ))}
                    </div>
                  }
                />
                <div className="flex shrink-0 flex-col gap-1">
                  <Button asChild size="sm" variant="ghost">
                    <Link to={`/imoveis/${encodeURIComponent(item.codigo)}`}>Abrir</Link>
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setAlvo(item)}
                    data-testid={`similar-adicionar-${item.codigo}`}
                  >
                    <UserPlus className="mr-1.5 h-3.5 w-3.5" />
                    Adicionar ao interesse de…
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>

      {alvo && (
        <EscolherInteressadoDialog
          origemCodigo={codigo}
          similar={alvo}
          onClose={() => setAlvo(null)}
        />
      )}
    </Card>
  );
}

/** Pick which interessado of THIS imóvel gets the similar in their list. The
 *  interessados query is only issued once the dialog mounts. */
function EscolherInteressadoDialog({
  origemCodigo,
  similar,
  onClose,
}: {
  origemCodigo: string;
  similar: SimilarItem;
  onClose: () => void;
}) {
  const interessados = useImovelInteressados(origemCodigo, { limit: 200 });
  const [clienteId, setClienteId] = useState("");
  // The mutation hook is per-cliente; the target is only known after the pick,
  // so it is keyed on the current selection.
  const { add } = useInteresseMutations(clienteId || "__none__");

  const rows = interessados.data?.items ?? [];
  const showSkeleton = interessados.isPending && !interessados.data;

  function confirmar() {
    if (!clienteId) return;
    add.mutate(
      { codigo: similar.codigo, origem: "manual" },
      {
        onSuccess: () => {
          toast.success(`${similar.codigo} adicionado à lista de interesses.`);
          onClose();
        },
        onError: (err) => toast.error(mensagemDe(err, "Não foi possível adicionar o interesse.")),
      },
    );
  }

  return (
    <Dialog open onOpenChange={(aberto) => !aberto && onClose()}>
      <DialogContent className="max-w-md" data-testid="similar-interessado-dialog">
        <DialogHeader>
          <DialogTitle>Adicionar {similar.codigo} ao interesse de…</DialogTitle>
          <DialogDescription>
            Escolha quem, entre os interessados em {origemCodigo}, deve receber este imóvel
            como alternativa.
          </DialogDescription>
        </DialogHeader>

        {showSkeleton ? (
          <div className="h-10 animate-pulse rounded bg-muted" />
        ) : interessados.isError && !interessados.data ? (
          <p className="text-sm text-destructive">Não foi possível carregar os interessados.</p>
        ) : rows.length === 0 ? (
          <p className="text-sm italic text-muted-foreground">
            Este imóvel ainda não tem interessados.
          </p>
        ) : (
          <select
            value={clienteId}
            onChange={(e) => setClienteId(e.target.value)}
            className="h-9 w-full rounded-md border bg-background px-3 text-sm"
            aria-label="Interessado"
            data-testid="similar-interessado-select"
          >
            <option value="">Selecione…</option>
            {rows.map((r) => (
              <option key={r.interesse_id} value={r.cliente_id}>
                {r.nome}
              </option>
            ))}
          </select>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={add.isPending}>
            Cancelar
          </Button>
          <Button
            onClick={confirmar}
            disabled={!clienteId || add.isPending}
            data-testid="similar-interessado-confirmar"
          >
            {add.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Adicionar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default ImovelSimilaresCard;
