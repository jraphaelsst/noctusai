/**
 * Headlines e Roteiros (`/media-creation/chat/headlines-e-roteiros`, estruturas-contract §11.3, FE-3): one row per
 * saved headline + its roteiro (and roteiros without a headline), with the Estruturas used, the source
 * conversation and the card. It folds Headlines Favoritas + Meus roteiros; the actions reuse their mutations.
 * Route + nav are wired by the tech-lead (FE-Z).
 */
import { useEffect, useState } from "react";
import { AlertCircle, Plus } from "lucide-react";
import { toast } from "sonner";

import { PaginaCabecalho, usePaginaPadding } from "@/components/geracao/PaginaCabecalho";
import { EditarHeadlineModal } from "@/components/geracao/headlines/EditarHeadlineModal";
import { FiltrosHR, type FiltrosHRValor } from "@/components/geracao/headlines-roteiros/FiltrosHR";
import { ItemLinha } from "@/components/geracao/headlines-roteiros/ItemLinha";
import { chaveDoItem, textoDoItem } from "@/components/geracao/headlines-roteiros/rotulos";
import { mensagemEstruturas } from "@/components/geracao/biblioteca/estruturas/erros";
import { EditarRoteiroModal } from "@/components/geracao/roteiro/EditarRoteiroModal";
import { RoteiroAvancadoModal } from "@/components/geracao/roteiro/RoteiroAvancadoModal";
import { MarcaSwitcher } from "@/components/pesquisa/MarcaSwitcher";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useEstruturas } from "@/hooks/geracao/useEstruturas";
import { useExcluirHeadlines, useFavoritarHeadline } from "@/hooks/geracao/useHeadlineMutations";
import {
  HR_PAGE_SIZE,
  useHeadlinesRoteiros,
  type RoteiroStatusFiltro,
} from "@/hooks/geracao/useHeadlinesRoteiros";
import { useExcluirRoteiros, useReprocessarRoteiro } from "@/hooks/geracao/useRoteiros";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { useMarcaPesquisa } from "@/hooks/useMarcaPesquisa";
import { useMarcas } from "@/hooks/useMarcas";
import type { HeadlineRoteiroItem } from "@/types/estruturas";

export default function HeadlinesRoteiros() {
  const padding = usePaginaPadding();
  const marcasQ = useMarcas();
  const marcas = marcasQ.data ?? [];
  const { marcaId, escolherMarca } = useMarcaPesquisa(marcas);

  const [filtros, setFiltros] = useState<FiltrosHRValor>({ busca: "", estruturaId: "", perfilId: "", status: "" });
  const q = useDebouncedValue(filtros.busca, 300);
  const [offset, setOffset] = useState(0);
  useEffect(() => setOffset(0), [marcaId, q, filtros.estruturaId, filtros.perfilId, filtros.status]);

  const lista = useHeadlinesRoteiros({
    marcaId,
    q,
    estruturaId: filtros.estruturaId || null,
    perfilId: filtros.perfilId || null,
    roteiroStatus: (filtros.status || null) as RoteiroStatusFiltro | null,
    offset,
  });
  const estruturasQ = useEstruturas({ marcaId, limit: 50 }, !!marcaId);
  const items = lista.data?.items ?? [];
  const total = lista.data?.total ?? 0;

  const favoritar = useFavoritarHeadline();
  const excluirHeadlines = useExcluirHeadlines();
  const excluirRoteiros = useExcluirRoteiros();
  const reprocessar = useReprocessarRoteiro();

  const [criar, setCriar] = useState<{ aberto: boolean; item: HeadlineRoteiroItem | null }>({ aberto: false, item: null });
  const [editando, setEditando] = useState<HeadlineRoteiroItem | null>(null);
  const [roteiroAberto, setRoteiroAberto] = useState<string | null>(null);
  const [excluindo, setExcluindo] = useState<HeadlineRoteiroItem | null>(null);

  function aoFavoritar(id: string, fav: boolean) {
    favoritar.mutate(
      { id, favoritar: fav },
      { onError: (e) => toast.error(mensagemEstruturas(e, "Não foi possível atualizar a favorita.")) },
    );
  }

  function aoReprocessar(id: string) {
    reprocessar.mutate(
      { id },
      {
        onSuccess: (novo) => {
          toast.success("Reprocessando o roteiro.");
          setRoteiroAberto(novo.id);
        },
        onError: (e) => toast.error(mensagemEstruturas(e, "Não foi possível reprocessar o roteiro.")),
      },
    );
  }

  async function confirmarExcluir() {
    const item = excluindo;
    if (!item) return;
    try {
      if (item.headline) await excluirHeadlines.mutateAsync([item.headline.id]);
      else if (item.roteiro) await excluirRoteiros.mutateAsync([item.roteiro.id]);
      toast.success(item.headline ? "Headline excluída." : "Roteiro excluído.");
      setExcluindo(null);
    } catch (e) {
      toast.error(mensagemEstruturas(e, "Não foi possível excluir."));
    }
  }
  const excluindoPendente = excluirHeadlines.isPending || excluirRoteiros.isPending;

  return (
    <div className={`space-y-6 ${padding}`}>
      <PaginaCabecalho
        titulo="Headlines e Roteiros"
        descricao="Suas headlines salvas e os roteiros criados a partir delas, com as estruturas usadas."
      >
        <MarcaSwitcher marcas={marcas} marcaId={marcaId} onChange={escolherMarca} />
        <Button onClick={() => setCriar({ aberto: true, item: null })} disabled={!marcaId}>
          <Plus className="mr-1 h-4 w-4" /> Criar roteiro
        </Button>
      </PaginaCabecalho>

      <FiltrosHR valor={filtros} onChange={setFiltros} estruturas={estruturasQ.data?.items ?? []} />

      {lista.showSkeleton && (
        <div className="space-y-2" data-testid="hr-skeleton">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
      )}

      {lista.isError && !lista.data && (
        <div role="alert" className="flex items-center justify-between rounded-md border p-4 text-sm">
          <span className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 text-destructive" />
            {mensagemEstruturas(lista.error, "Não foi possível carregar suas headlines e roteiros.")}
          </span>
          <Button size="sm" variant="outline" onClick={() => lista.refetch()}>
            Tentar novamente
          </Button>
        </div>
      )}

      {!!marcaId && lista.data && items.length === 0 && (
        <p className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground" data-testid="hr-vazio">
          {q.trim() || filtros.estruturaId || filtros.perfilId || filtros.status
            ? "Nada encontrado para estes filtros."
            : "Você ainda não salvou headlines nem criou roteiros. Converse no chat ou clique em Criar roteiro."}
        </p>
      )}

      {items.length > 0 && (
        <div className={lista.isRefreshing ? "opacity-80 transition-opacity" : undefined} aria-busy={lista.isRefreshing}>
          <ul className="space-y-3">
            {items.map((item) => (
              <ItemLinha
                key={chaveDoItem(item)}
                item={item}
                marcaId={marcaId}
                ocupado={favoritar.isPending || reprocessar.isPending}
                onFavoritar={aoFavoritar}
                onEditarHeadline={setEditando}
                onAbrirRoteiro={setRoteiroAberto}
                onCriarRoteiro={(i) => setCriar({ aberto: true, item: i })}
                onReprocessar={aoReprocessar}
                onExcluir={setExcluindo}
              />
            ))}
          </ul>
          {total > HR_PAGE_SIZE && (
            <div className="flex items-center justify-between pt-3 text-sm text-muted-foreground">
              <span>
                {offset + 1}–{Math.min(offset + HR_PAGE_SIZE, total)} de {total}
              </span>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - HR_PAGE_SIZE))}>
                  Anterior
                </Button>
                <Button size="sm" variant="outline" disabled={offset + HR_PAGE_SIZE >= total} onClick={() => setOffset(offset + HR_PAGE_SIZE)}>
                  Próxima
                </Button>
              </div>
            </div>
          )}
        </div>
      )}

      <RoteiroAvancadoModal
        open={criar.aberto}
        onOpenChange={(o) => setCriar((c) => ({ ...c, aberto: o }))}
        marcaId={marcaId}
        headlineInicial={criar.item?.headline ? { id: criar.item.headline.id, texto: criar.item.headline.texto } : null}
      />
      <EditarHeadlineModal
        open={!!editando}
        onOpenChange={(o) => !o && setEditando(null)}
        headline={editando?.headline ? { id: editando.headline.id, texto: editando.headline.texto, texto_original: null } : null}
        onSalvo={() => setEditando(null)}
      />
      <EditarRoteiroModal
        open={!!roteiroAberto}
        onOpenChange={(o) => !o && setRoteiroAberto(null)}
        roteiroId={roteiroAberto}
        onReprocessado={(novo) => setRoteiroAberto(novo.id)}
      />

      <AlertDialog open={!!excluindo} onOpenChange={(o) => !o && !excluindoPendente && setExcluindo(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{excluindo?.headline ? "Excluir headline" : "Excluir roteiro"}</AlertDialogTitle>
            <AlertDialogDescription>
              {excluindo ? `Excluir "${textoDoItem(excluindo)}"? Esta ação não pode ser desfeita.` : ""}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={excluindoPendente}>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              disabled={excluindoPendente}
              onClick={(e) => {
                e.preventDefault();
                void confirmarExcluir();
              }}
            >
              {excluindoPendente ? "Excluindo…" : "Excluir"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
