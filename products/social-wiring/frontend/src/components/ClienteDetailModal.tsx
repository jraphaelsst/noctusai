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
 * DESCRIÇÃO vs. COMENTÁRIOS (backend correction, landed on `origin/dev`
 * after this slice's first pass surfaced the gap): `cliente_notas` now
 * carries a `tipo: "descricao" | "comentario"` discriminator
 * (`card_hub/schemas.py::NotaCreateBody`). `CardResumo.descricao` is the
 * single description note (or `null`) — the timeline never contains it
 * (`card_hub/timeline_service.py::_gather_notas` filters `tipo=
 * "comentario"` explicitly). The description editor below edits-by-id
 * when `card.data.descricao` exists, or creates with `tipo: "descricao"`
 * when it doesn't; the composer always creates with the default
 * `tipo: "comentario"`. The backend enforces at most one non-deleted
 * description per cliente (a partial unique index) and returns a typed
 * 409 on a second create — surfaced here via a toast with the server's
 * own message, not left to read as a network failure.
 */
import type { ReactNode } from "react";
import { useState } from "react";
import { toast } from "sonner";

import { useLeadCorretores } from "@/hooks/useLeadsCorretores";
import {
  flattenTimeline,
  useCardResumo,
  useChecklistMutations,
  useChecklists,
  useAgendamentoMutations,
  useAgendamentos,
  useDocumentoChecklist,
  useDocumentoChecklistMutation,
  useExtracaoSugestaoMutation,
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

export interface ClienteDetailModalProps {
  clienteId: string | null;
  open: boolean;
  onClose: () => void;
  /** Board-specific actions for the card header (see `ClienteCardDialogProps.acoes`). */
  acoes?: ReactNode;
}

/** The server's own message when a mutation fails — never a silently
 *  swallowed rejection (e.g. the 409 on a second `descricao`, or the
 *  400 naming exactly which upload limit was hit). */
function toastServerError(err: unknown, fallback: string) {
  const message = err instanceof Error && err.message ? err.message : fallback;
  toast.error(message);
}

export function ClienteDetailModal({ clienteId, open, onClose, acoes }: ClienteDetailModalProps) {
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
  const documentoChecklist = useDocumentoChecklist(id);
  const tiposDocumento = useTiposDocumento();

  const notaMutations = useNotaMutations(id ?? "__none__");
  const tagCatalogMutations = useTagCatalogMutations();
  const setTagsMutation = useSetClienteTagsMutation(id ?? "__none__");
  const setMembrosMutation = useSetCardMembrosMutation(id ?? "__none__");
  const agendamentos = useAgendamentos(id);
  const agendamentoMutations = useAgendamentoMutations(id ?? "__none__");
  const checklistMutations = useChecklistMutations(id ?? "__none__");
  const documentoMutations = useDocumentoMutations(id ?? "__none__");
  const documentoChecklistMutation = useDocumentoChecklistMutation(id ?? "__none__");
  const sugestaoMutation = useExtracaoSugestaoMutation(id ?? "__none__");

  const timelineEntries = flattenTimeline(timeline.data?.pages);

  // `isPending` ONLY — deliberately not `|| isFetching`.
  //
  // Every mutation invalidates the card, so `isFetching` goes true on each one
  // and the whole dialog flashed a skeleton after every checklist tick, tag
  // toggle and comment. The user's words: "It's reloading the card on every
  // move i make inside of it."
  //
  // This does NOT reintroduce the lying-loading-state class (`CLAUDE.md` §1).
  // That rule exists so an `isEmpty` branch cannot render "no data" OVER data
  // that is merely refetching. Here `isPending` is true exactly when there is
  // no data yet, and `notFound` below is gated on `card.data === undefined` —
  // which cannot hold during a background refetch, because a refetch by
  // definition has previous data. The skeleton is now first-load only; updates
  // land in place, optimistically (see `useCardHub`).
  const loading = card.isPending;
  const isError = card.isError;
  const notFound = !loading && !isError && shouldFetch && card.data === undefined;

  function handleSaveDescricao(corpo: string) {
    const descricao = card.data?.descricao;
    if (descricao) {
      notaMutations.update.mutate(
        { notaId: descricao.id, corpo },
        { onError: (err) => toastServerError(err, "Não foi possível salvar a descrição.") },
      );
    } else {
      notaMutations.create.mutate(
        { corpo, tipo: "descricao" },
        {
          // The backend's 409 on a duplicate description lands here —
          // shown with its own message, never a generic failure.
          onError: (err) => toastServerError(err, "Não foi possível criar a descrição."),
        },
      );
    }
  }

  function handlePostComentario(corpo: string) {
    notaMutations.create.mutate(
      { corpo, tipo: "comentario" },
      { onError: (err) => toastServerError(err, "Não foi possível enviar o comentário.") },
    );
  }

  function handleToggleTag(tagId: string) {
    if (!card.data) return;
    const current = card.data.tags.map((t) => t.id);
    const next = current.includes(tagId) ? current.filter((t) => t !== tagId) : [...current, tagId];
    setTagsMutation.mutate(next, {
      onError: (err) => toastServerError(err, "Não foi possível atualizar as etiquetas."),
    });
  }

  function handleToggleMembro(membroId: string) {
    if (!card.data) return;
    const current = card.data.membros.map((m) => m.id);
    const next = current.includes(membroId)
      ? current.filter((m) => m !== membroId)
      : [...current, membroId];
    setMembrosMutation.mutate(next, {
      onError: (err) => toastServerError(err, "Não foi possível atualizar os membros."),
    });
  }

  function handleEditTag(tagId: string) {
    const tag = tags.data?.find((t) => t.id === tagId);
    if (!tag) return;
    const novoNome = window.prompt("Renomear etiqueta", tag.nome);
    if (novoNome && novoNome.trim() && novoNome.trim() !== tag.nome) {
      tagCatalogMutations.update.mutate(
        { tagId, body: { nome: novoNome.trim() } },
        { onError: (err) => toastServerError(err, "Não foi possível renomear a etiqueta.") },
      );
    }
  }

  function handleOpenDocumento(documentoId: string) {
    documentoMutations.getUrl.mutate(documentoId, {
      onSuccess: (res) => {
        window.open(res.url, "_blank", "noopener,noreferrer");
      },
      onError: (err) => toastServerError(err, "Não foi possível abrir o anexo."),
    });
  }

  if (!clienteId) return null;

  return (
    <ClienteCardDialog
      open={open}
      onClose={onClose}
      acoes={acoes}
      isLoading={loading}
      error={isError ? "Não foi possível carregar este cartão." : null}
      notFound={notFound}
      nome={card.data?.cliente.nome ?? ""}
      atendimentos={card.data?.atendimentos}
      allTags={tags.data ?? []}
      selectedTags={card.data?.tags ?? []}
      onToggleTag={handleToggleTag}
      onCreateTag={(nome, cor) =>
        tagCatalogMutations.create.mutate(
          { nome, cor },
          { onError: (err) => toastServerError(err, "Não foi possível criar a etiqueta.") },
        )
      }
      onEditTag={handleEditTag}
      colorBlindMode={colorBlindMode}
      onToggleColorBlindMode={setColorBlindMode}
      tagsSaving={setTagsMutation.isPending}
      agendamentos={agendamentos.data ?? []}
      agendamentosLoading={agendamentos.isPending}
      onCreateAgendamento={(body) =>
        agendamentoMutations.create.mutate(body, {
          // The 409 when a person has several open atendimentos arrives with
          // the candidate ids; surfaced with the server's own message rather
          // than a generic failure, because only it can say what to pick.
          onError: (err) => toastServerError(err, "Não foi possível criar o agendamento."),
        })
      }
      onRemoveAgendamento={(id) =>
        agendamentoMutations.remove.mutate(id, {
          onError: (err) => toastServerError(err, "Não foi possível remover o agendamento."),
        })
      }
      agendamentoSaving={agendamentoMutations.create.isPending}
      allMembros={corretores.data ?? []}
      selectedMembros={card.data?.membros ?? []}
      onToggleMembro={handleToggleMembro}
      membrosSaving={setMembrosMutation.isPending}
      descricaoCorpo={card.data?.descricao?.corpo ?? ""}
      onSaveDescricao={handleSaveDescricao}
      descricaoSaving={notaMutations.create.isPending || notaMutations.update.isPending}
      onResolverSugestao={(documentoId, acao, itemKey) =>
        sugestaoMutation.mutate(
          { documentoId, acao, itemKey },
          {
            onError: (err) =>
              toastServerError(
                err,
                acao === "confirmar"
                  ? "Não foi possível confirmar o dado extraído."
                  : "Não foi possível descartar a sugestão.",
              ),
          },
        )
      }
      sugestaoSaving={sugestaoMutation.isPending}
      documentoChecklist={documentoChecklist.data?.items ?? []}
      documentoChecklistLoading={documentoChecklist.isPending}
      sugestoesExtras={documentoChecklist.data?.sugestoes_extras}
      nomeOficial={documentoChecklist.data?.nome_oficial}
      nomeRegistro={documentoChecklist.data?.nome_registro}
      onToggleDocumentoChecklist={(key, concluido) =>
        documentoChecklistMutation.mutate(
          { key, concluido },
          {
            // The optimistic tick has already rolled back by the time this
            // runs; the toast says WHY it snapped back rather than leaving the
            // checkbox to look flaky.
            onError: (err) =>
              toastServerError(err, "Não foi possível atualizar a lista de dados."),
          },
        )
      }
      documentos={documentos.data ?? []}
      documentosLoading={documentos.isPending}
      tiposDocumento={tiposDocumento.data ?? []}
      onUploadDocumento={(file, tipoDocumento) =>
        documentoMutations.upload.mutate(
          { file, tipoDocumento },
          {
            // The 400 naming the exact limit/type it hit (contract §3) —
            // never a client-side guess at the ceiling, which is a
            // platform constant subject to change out from under this UI.
            onError: (err) => toastServerError(err, "Não foi possível enviar o anexo."),
          },
        )
      }
      uploadingDocumento={documentoMutations.upload.isPending}
      onOpenDocumento={handleOpenDocumento}
      onDeleteDocumento={(documentoId, motivo) =>
        documentoMutations.remove.mutate(
          { documentoId, motivo },
          { onError: (err) => toastServerError(err, "Não foi possível remover o anexo.") },
        )
      }
      checklists={checklists.data ?? []}
      checklistsLoading={checklists.isPending}
      onCreateChecklist={(titulo) => checklistMutations.createChecklist.mutate(titulo)}
      onRemoveChecklist={(checklistId) => checklistMutations.removeChecklist.mutate(checklistId)}
      onAddItem={(checklistId, texto) => checklistMutations.addItem.mutate({ checklistId, texto })}
      onToggleItem={(checklistId, itemId, concluido) =>
        checklistMutations.toggleItem.mutate({ checklistId, itemId, concluido })
      }
      onRemoveItem={(checklistId, itemId) => checklistMutations.removeItem.mutate({ checklistId, itemId })}
      timelineEntries={timelineEntries}
      timelineLoading={timeline.isPending}
      timelineError={timeline.isError ? "boom" : null}
      timelineHasMore={!!timeline.hasNextPage}
      timelineLoadingMore={timeline.isFetchingNextPage}
      onTimelineLoadMore={() => timeline.fetchNextPage()}
      onPostComentario={handlePostComentario}
      postingComentario={notaMutations.create.isPending}
    />
  );
}
