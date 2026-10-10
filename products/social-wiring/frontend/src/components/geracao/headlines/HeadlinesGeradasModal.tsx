/**
 * "Headlines Geradas" (contract §7.7, page-map-v2 §17): the result of one batch.
 * Per headline: ♥ favoritar, ✎ editar, Criar roteiro, the structure link `#codigo`
 * (→ ViralModal), "Itens da pesquisa usados" chips; batch warnings and Reprocessar.
 * Failed batches show the backend error instead of an empty list.
 */
import { useState } from "react";
import { AlertCircle, Heart, Pencil, RefreshCw, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { ViralModal } from "@/components/geracao/biblioteca/ViralModal";
import { MetricaPill } from "@/components/geracao/MetricaPill";
import { RoteiroAvancadoModal } from "@/components/geracao/roteiro/RoteiroAvancadoModal";
import { StatusBadge } from "@/components/geracao/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { CriarPostButton, NoPostBadge } from "@/components/geracao/PostEsteira";
import { useFavoritarHeadline } from "@/hooks/geracao/useHeadlineMutations";
import { useLote, useReprocessarLote } from "@/hooks/geracao/useHeadlines";
import { cn } from "@/lib/utils";
import type { Headline } from "@/types/geracao";
import { ORIGEM_ROTULO } from "../labels";
import { EditarHeadlineModal } from "./EditarHeadlineModal";
import { AvisosLote, mensagemErro } from "./lote";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  loteId: string | null;
  marcaId: string | null;
  /** The new batch created by Reprocessar (the old one is kept) — the page follows it. */
  onReprocessado?: (loteId: string) => void;
  /** Esteira post card: adds "Usar neste post" to each headline (binds it and the caller closes). */
  onUsarNoPost?: (h: Headline) => void;
}

export function HeadlinesGeradasModal({ open, onOpenChange, loteId, marcaId, onReprocessado, onUsarNoPost }: Props) {
  const q = useLote(open ? loteId : null);
  const lote = q.data;
  const favoritar = useFavoritarHeadline();
  const reprocessar = useReprocessarLote();

  const [editando, setEditando] = useState<Headline | null>(null);
  const [viralId, setViralId] = useState<string | null>(null);
  const [roteiroDe, setRoteiroDe] = useState<Headline | null>(null);

  async function alternarFavorita(h: Headline) {
    try {
      await favoritar.mutateAsync({ id: h.id, favoritar: !h.favorita });
      toast.success(h.favorita ? "Removida das favoritas." : "Adicionada às favoritas.");
    } catch (e) {
      toast.error(mensagemErro(e, "Não foi possível atualizar a favorita."));
    }
  }

  async function reprocessarLote() {
    if (!lote) return;
    try {
      const novo = await reprocessar.mutateAsync(lote.id);
      toast.success("Reprocessando — um novo lote foi criado.");
      onReprocessado?.(novo.id);
      onOpenChange(false);
    } catch (e) {
      toast.error(mensagemErro(e, "Não foi possível reprocessar."));
    }
  }

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-h-[90vh] max-w-3xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Headlines Geradas</DialogTitle>
            <DialogDescription>
              {lote ? `${ORIGEM_ROTULO[lote.origem]} · ${lote.resumo}` : "Carregando..."}
            </DialogDescription>
          </DialogHeader>

          {q.showSkeleton && (
            <div className="space-y-2" data-testid="lote-skeleton">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-16 w-full" />
              ))}
            </div>
          )}

          {q.isError && !lote && (
            <div role="alert" className="flex items-center justify-between rounded-md border p-4 text-sm">
              <span className="flex items-center gap-2">
                <AlertCircle className="h-4 w-4 text-destructive" /> Não foi possível carregar as headlines.
              </span>
              <Button size="sm" variant="outline" onClick={() => q.refetch()}>
                Tentar novamente
              </Button>
            </div>
          )}

          {lote && (
            <div className={cn("space-y-4", q.isRefreshing && "opacity-80 transition-opacity")} aria-busy={q.isRefreshing}>
              <div className="flex items-center gap-2">
                <StatusBadge status={lote.status} />
              </div>
              <AvisosLote lote={lote} />

              {lote.headlines.length === 0 && lote.status !== "falha" && (
                <p className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
                  Este lote ainda não tem headlines.
                </p>
              )}

              <ul className="space-y-3">
                {lote.headlines.map((h) => (
                  <li key={h.id} className="space-y-2 rounded-md border p-3" data-testid={`headline-${h.id}`}>
                    <p className="whitespace-pre-wrap text-sm">{h.texto}</p>
                    <NoPostBadge post={h.post} />
                    <div className="flex flex-wrap items-center gap-2 text-xs">
                      {h.viral && (
                        <>
                          <button
                            type="button"
                            className="underline"
                            aria-label={`Ver estrutura #${h.viral.codigo}`}
                            onClick={() => setViralId(h.viral!.id)}
                          >
                            #{h.viral.codigo}
                          </button>
                          <MetricaPill viral={h.viral} />
                        </>
                      )}
                      {h.template_metodo != null && (
                        <Badge variant="outline">Template do Método #{h.template_metodo}</Badge>
                      )}
                    </div>
                    {h.itens_usados.length > 0 && (
                      <div className="space-y-1">
                        <p className="text-xs font-medium text-muted-foreground">Itens da pesquisa usados</p>
                        <div className="flex flex-wrap gap-1">
                          {h.itens_usados.map((i) => (
                            <Badge key={`${i.slot}-${i.item_id}`} variant="secondary" title={i.slot}>
                              {i.conteudo}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    )}
                    <div className="flex flex-wrap justify-end gap-1">
                      <Button
                        size="sm"
                        variant="ghost"
                        aria-pressed={h.favorita}
                        aria-label={h.favorita ? "Desfavoritar headline" : "Favoritar headline"}
                        disabled={favoritar.isPending}
                        onClick={() => alternarFavorita(h)}
                      >
                        <Heart className={cn("h-4 w-4", h.favorita && "fill-current text-rose-600")} />
                      </Button>
                      <Button size="sm" variant="ghost" aria-label="Editar headline" onClick={() => setEditando(h)}>
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => setRoteiroDe(h)}>
                        <Sparkles className="mr-1 h-4 w-4" /> Criar roteiro
                      </Button>
                      {onUsarNoPost ? (
                        <Button size="sm" disabled={!!h.post} title={h.post ? `No post: ${h.post.titulo}` : undefined} onClick={() => onUsarNoPost(h)}>
                          Usar neste post
                        </Button>
                      ) : (
                        <CriarPostButton marcaId={marcaId} headlineId={h.id} post={h.post} />
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Fechar
            </Button>
            <Button
              disabled={!lote || lote.status === "criando" || lote.status === "processando" || reprocessar.isPending}
              onClick={reprocessarLote}
            >
              <RefreshCw className="mr-1 h-4 w-4" /> {reprocessar.isPending ? "Reprocessando…" : "Reprocessar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <EditarHeadlineModal open={!!editando} onOpenChange={(o) => !o && setEditando(null)} headline={editando} />
      <ViralModal open={!!viralId} onOpenChange={(o) => !o && setViralId(null)} marcaId={marcaId} viralId={viralId} />
      <RoteiroAvancadoModal
        open={!!roteiroDe}
        onOpenChange={(o) => !o && setRoteiroDe(null)}
        marcaId={marcaId}
        headlineInicial={roteiroDe ? { id: roteiroDe.id, texto: roteiroDe.texto } : null}
      />
    </>
  );
}
