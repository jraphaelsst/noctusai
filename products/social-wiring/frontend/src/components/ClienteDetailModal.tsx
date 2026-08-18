/**
 * `<ClienteDetailModal/>` — the product's ONE cliente card detail view.
 *
 * Mirrors `LeadDetailModal.tsx`'s split exactly: chrome + interaction comes
 * from the presentational organ (`ClienteCardDialog`, `components/card/**`,
 * S3-presentational per PROJECT.md §0), this file owns only "which record,
 * how to get it, and where the mutations go" — `useCardHub` (the ONE file
 * every card query/mutation lives in, per ruling S3).
 *
 * Mountable from BOTH `ClientesBoard` (wired this slice) and, once slice
 * `054` lands, the funil card — just render `<ClienteDetailModal
 * clienteId={id} open onClose={...} />` from either surface.
 *
 * CONTRACT GAP, surfaced rather than silently resolved (PROJECT.md §5's
 * "do not invent a field" anti-goal): `cliente_notas` (§2) covers BOTH
 * Trello's *Descrição* (one field, editable) and *Comentários* (a growing
 * thread) with NO discriminator column. This build treats the OLDEST
 * loaded `nota` timeline entry as "the description" and every other nota
 * as a comment; the composer always POSTs a new note, never touching the
 * description note. This only see the descrição correctly once the
 * timeline has paged back far enough to include the very first note — an
 * accepted, disclosed limitation for now (`drift-found:` below), not
 * silently patched over. The clean fix is a backend discriminator (e.g. a
 * dedicated `clientes.descricao` column, or a `tipo` flag on
 * `cliente_notas`).
 */
import { useMemo, useState } from "react";

import { useLeadCorretores } from "@/hooks/useLeadsCorretores";
import {
  flattenTimeline,
  useCardResumo,
  useChecklistMutations,
  useChecklists,
  useDatasMutation,
  useDocumentoMutations,
  useDocumentos,
  useNotaMutations,
  useSetCardMembrosMutation,
  useSetClienteTagsMutation,
  useTagCatalogMutations,
  useTags,
  useTimeline,
  useTiposDocumento,
} from "@/hooks/useCardHub";

import { ClienteCardDialog } from "@/components/card/ClienteCardDialog";
import type { TimelineNotaEntry } from "@/types/cardHub";

export interface ClienteDetailModalProps {
  clienteId: string | null;
  open: boolean;
  onClose: () => void;
}

export function ClienteDetailModal({ clienteId, open, onClose }: ClienteDetailModalProps) {
  // Colour-blind mode has no persistence surface in this contract (a Trello
  // account-level preference; nothing in §2/§3 models one) — kept as
  // session-local UI state rather than inventing a field.
  const [colorBlindMode, setColorBlindMode] = useState(false);

  const shouldFetch = open && !!clienteId;
  const id = shouldFetch ? (clienteId as string) : null;

  const card = useCardResumo(id);
  const timeline = useTimeline(id);
  const tags = useTags();
  const corretores = useLeadCorretores();
  const checklists = useChecklists(id);
  const documentos = useDocumentos(id);
  const tiposDocumento = useTiposDocumento();

  const notaMutations = useNotaMutations(id ?? "__none__");
  const tagCatalogMutations = useTagCatalogMutations();
  const setTagsMutation = useSetClienteTagsMutation(id ?? "__none__");
  const setMembrosMutation = useSetCardMembrosMutation(id ?? "__none__");
  const datasMutation = useDatasMutation(id ?? "__none__");
  const checklistMutations = useChecklistMutations(id ?? "__none__");
  const documentoMutations = useDocumentoMutations(id ?? "__none__");

  const timelineEntries = flattenTimeline(timeline.data?.pages);

  // See docblock — the oldest LOADED `nota` entry stands in for "the
  // description" until the backend carries a real discriminator.
  const descricaoNota = useMemo(() => {
    const notas = timelineEntries.filter(
      (e): e is TimelineNotaEntry => e.kind === "nota" && !e.deleted_at,
    );
    if (notas.length === 0) return null;
    return notas.reduce((oldest, cur) =>
      new Date(cur.ocorrido_em) < new Date(oldest.ocorrido_em) ? cur : oldest,
    );
  }, [timelineEntries]);

  const loading = card.isPending || card.isFetching;
  const isError = card.isError;
  const notFound = !loading && !isError && shouldFetch && card.data === undefined;

  function handleSaveDescricao(corpo: string) {
    if (descricaoNota) {
      notaMutations.update.mutate({ notaId: descricaoNota.id, corpo });
    } else {
      notaMutations.create.mutate(corpo);
    }
  }

  function handleToggleTag(tagId: string) {
    if (!card.data) return;
    const current = card.data.tags.map((t) => t.id);
    const next = current.includes(tagId) ? current.filter((t) => t !== tagId) : [...current, tagId];
    setTagsMutation.mutate(next);
  }

  function handleToggleMembro(membroId: string) {
    if (!card.data) return;
    const current = card.data.membros.map((m) => m.id);
    const next = current.includes(membroId)
      ? current.filter((m) => m !== membroId)
      : [...current, membroId];
    setMembrosMutation.mutate(next);
  }

  function handleEditTag(tagId: string) {
    const tag = tags.data?.find((t) => t.id === tagId);
    if (!tag) return;
    const novoNome = window.prompt("Renomear etiqueta", tag.nome);
    if (novoNome && novoNome.trim() && novoNome.trim() !== tag.nome) {
      tagCatalogMutations.update.mutate({ tagId, body: { nome: novoNome.trim() } });
    }
  }

  function handleOpenDocumento(documentoId: string) {
    documentoMutations.getUrl.mutate(documentoId, {
      onSuccess: (res) => {
        window.open(res.url, "_blank", "noopener,noreferrer");
      },
    });
  }

  if (!clienteId) return null;

  return (
    <ClienteCardDialog
      open={open}
      onClose={onClose}
      isLoading={loading}
      error={isError ? "Não foi possível carregar este cartão." : null}
      notFound={notFound}
      nome={card.data?.cliente.nome ?? ""}
      allTags={tags.data ?? []}
      selectedTags={card.data?.tags ?? []}
      onToggleTag={handleToggleTag}
      onCreateTag={(nome, cor) => tagCatalogMutations.create.mutate({ nome, cor })}
      onEditTag={handleEditTag}
      colorBlindMode={colorBlindMode}
      onToggleColorBlindMode={setColorBlindMode}
      tagsSaving={setTagsMutation.isPending}
      datas={card.data?.datas ?? null}
      onSaveDatas={(body) => datasMutation.mutate(body)}
      onRemoveDatas={() =>
        datasMutation.mutate({
          data_inicio: null,
          data_entrega: null,
          entrega_concluida: false,
          lembrete_minutos_antes: null,
          recorrencia: null,
        })
      }
      datasSaving={datasMutation.isPending}
      allMembros={corretores.data ?? []}
      selectedMembros={card.data?.membros ?? []}
      onToggleMembro={handleToggleMembro}
      membrosSaving={setMembrosMutation.isPending}
      descricaoCorpo={descricaoNota?.corpo ?? ""}
      onSaveDescricao={handleSaveDescricao}
      descricaoSaving={notaMutations.create.isPending || notaMutations.update.isPending}
      documentos={documentos.data ?? []}
      documentosLoading={documentos.isPending || documentos.isFetching}
      tiposDocumento={tiposDocumento.data ?? []}
      onUploadDocumento={(file, tipoDocumento) => documentoMutations.upload.mutate({ file, tipoDocumento })}
      uploadingDocumento={documentoMutations.upload.isPending}
      onOpenDocumento={handleOpenDocumento}
      onDeleteDocumento={(documentoId, motivo) => documentoMutations.remove.mutate({ documentoId, motivo })}
      checklists={checklists.data ?? []}
      checklistsLoading={checklists.isPending || checklists.isFetching}
      onCreateChecklist={(titulo) => checklistMutations.createChecklist.mutate(titulo)}
      onRemoveChecklist={(checklistId) => checklistMutations.removeChecklist.mutate(checklistId)}
      onAddItem={(checklistId, texto) => checklistMutations.addItem.mutate({ checklistId, texto })}
      onToggleItem={(checklistId, itemId, concluido) =>
        checklistMutations.toggleItem.mutate({ checklistId, itemId, concluido })
      }
      onRemoveItem={(checklistId, itemId) => checklistMutations.removeItem.mutate({ checklistId, itemId })}
      timelineEntries={timelineEntries}
      timelineLoading={timeline.isPending || timeline.isFetching}
      timelineError={timeline.isError ? "boom" : null}
      timelineHasMore={!!timeline.hasNextPage}
      timelineLoadingMore={timeline.isFetchingNextPage}
      onTimelineLoadMore={() => timeline.fetchNextPage()}
      onPostComentario={(corpo) => notaMutations.create.mutate(corpo)}
      postingComentario={notaMutations.create.isPending}
    />
  );
}
