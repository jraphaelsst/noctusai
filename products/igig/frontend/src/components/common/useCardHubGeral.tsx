/**
 * The seed card hub's "Geral" subpage + activity column, wired to a
 * `createCardHubHooks` instance — ONE mapping for every igig card.
 *
 * igig mounts the SAME card organ (`CardHubDialog`) on two entities: the
 * negócio (`/api/comercial/negocios`, Comercial) and the cliente
 * (`/api/clientes`, Clientes — roadmap R9). The Geral spine (etiquetas,
 * membros, descrição, anexos, checklists) and the activity column (composer
 * + timeline) are entity-agnostic: only the hub instance differs. Before this
 * hook the ~150-line mapping lived inline in `NegocioCardDialog`; the cliente
 * card would have been its second copy.
 *
 * Returns the `geral` subpage (register it first in the dialog's registry),
 * the `activity` prop, and the card-resumo loading/error state for the
 * dialog's own `isLoading` / `error`.
 *
 * Members are `igig.profissional` rows for both cards, so the member list is
 * read here (`useProfissionais`) and the PUT body key is their FK.
 */
import { useState, type ReactNode } from "react";
import { ClipboardList } from "lucide-react";
import {
  GeralActions,
  GeralSubpage,
  cardHubLoadingState,
  flattenTimeline,
  type CardHubActivityProps,
  type CardHubHooks,
  type CardSubpage,
  type GeralPopoverKey,
} from "@noctusai/lib/components";
import { toast } from "sonner";

import { useProfissionais } from "@/hooks/useCustos";
import { describeError } from "@/lib/errors";

/** `igig.profissional` is the member source of both card hubs (`app/card_hub.py`). */
export const MEMBRO_IDS_FIELD = "profissional_ids";

export interface CardHubGeral {
  geral: CardSubpage<"geral">;
  activity: CardHubActivityProps;
  /** `isPending && !data` of the card resumo — the dialog's `isLoading`. */
  showSkeleton: boolean;
  /** pt-BR error for the dialog, or null. */
  error: string | null;
  /** The card title the server resolved (entity `nome`), when loaded. */
  nome: string | null;
}

const NONE = "__none__";

export function useCardHubGeral(
  hub: CardHubHooks,
  id: string | null,
  opts: { afterTags?: ReactNode } = {},
): CardHubGeral {
  const card = hub.useCardResumo(id);
  const timeline = hub.useTimeline(id);
  const tags = hub.useTags();
  const membros = useProfissionais();
  const checklists = hub.useChecklists(id);
  const documentos = hub.useDocumentos(id);
  const tipos = hub.useTiposDocumento();
  const notas = hub.useNotaMutations(id ?? NONE);
  const setTags = hub.useSetTagsMutation(id ?? NONE);
  const setMembros = hub.useSetMembrosMutation(id ?? NONE, MEMBRO_IDS_FIELD);
  const tagCatalogo = hub.useTagCatalogMutations();
  const checklistMut = hub.useChecklistMutations(id ?? NONE);
  const docMut = hub.useDocumentoMutations(id ?? NONE);

  const { showSkeleton } = cardHubLoadingState(card);
  const docsState = cardHubLoadingState(documentos);
  const [colorBlind, setColorBlind] = useState(false);
  const [popover, setPopover] = useState<GeralPopoverKey | null>(null);

  const erroToast = (fallback: string) => (err: unknown) => toast.error(describeError(err, fallback));

  function salvarDescricao(corpo: string) {
    const d = card.data?.descricao;
    if (d) notas.update.mutate({ notaId: d.id, corpo }, { onError: erroToast("Não foi possível salvar a descrição.") });
    else notas.create.mutate({ corpo, tipo: "descricao" }, { onError: erroToast("Não foi possível criar a descrição.") });
  }

  function alternar(atual: string[], alvo: string) {
    return atual.includes(alvo) ? atual.filter((x) => x !== alvo) : [...atual, alvo];
  }

  function editarTag(tagId: string) {
    const tag = tags.data?.find((t) => t.id === tagId);
    if (!tag) return;
    const novoNome = window.prompt("Renomear etiqueta", tag.nome);
    if (novoNome && novoNome.trim() && novoNome.trim() !== tag.nome) {
      tagCatalogo.update.mutate(
        { tagId, body: { nome: novoNome.trim() } },
        { onError: erroToast("Não foi possível renomear a etiqueta.") },
      );
    }
  }

  const selectedTags = card.data?.tags ?? [];
  const selectedMembros = card.data?.membros ?? [];

  const geral: CardSubpage<"geral"> = {
    key: "geral",
    label: "Geral",
    icon: ClipboardList,
    toolbar: (
      <GeralActions
        etiquetas={{
          allTags: tags.data ?? [],
          selectedTagIds: selectedTags.map((t) => t.id),
          onToggleTag: (tagId) =>
            setTags.mutate(alternar(selectedTags.map((t) => t.id), tagId), {
              onError: erroToast("Não foi possível atualizar as etiquetas."),
            }),
          onCreateTag: (nome, cor) =>
            tagCatalogo.create.mutate({ nome, cor }, { onError: erroToast("Não foi possível criar a etiqueta.") }),
          onEditTag: editarTag,
          colorBlindMode: colorBlind,
          onToggleColorBlindMode: setColorBlind,
          saving: setTags.isPending,
        }}
        membros={{
          allMembros: membros.profissionais.filter((p) => p.ativo).map((p) => ({ id: p.id, nome: p.nome })),
          selectedMembroIds: selectedMembros.map((m) => m.id),
          onToggleMembro: (membroId) =>
            setMembros.mutate(alternar(selectedMembros.map((m) => m.id), membroId), {
              onError: erroToast("Não foi possível atualizar os membros."),
            }),
          saving: setMembros.isPending,
        }}
        onCreateChecklist={(titulo) =>
          checklistMut.createChecklist.mutate(titulo, { onError: erroToast("Não foi possível criar o checklist.") })
        }
        checklistSaving={checklistMut.createChecklist.isPending}
        activePopover={popover}
        onActivePopoverChange={setPopover}
      />
    ),
    render: () => (
      <GeralSubpage
        tags={selectedTags}
        descricao={{
          corpo: card.data?.descricao?.corpo ?? "",
          onSave: salvarDescricao,
          saving: notas.create.isPending || notas.update.isPending,
        }}
        anexos={{
          documentos: documentos.data ?? [],
          tipos: tipos.data ?? [],
          loading: docsState.showSkeleton,
          refreshing: docsState.isRefreshing,
          uploading: docMut.upload.isPending,
          onUpload: (file, tipoDocumento) =>
            docMut.upload.mutate({ file, tipoDocumento }, { onError: erroToast("Não foi possível enviar o anexo.") }),
          onOpenDocumento: (documentoId) =>
            docMut.getUrl.mutate(
              { documentoId, intent: "view" },
              {
                onSuccess: (r) => window.open(r.url, "_blank", "noopener,noreferrer"),
                onError: erroToast("Não foi possível abrir o anexo."),
              },
            ),
          onDeleteDocumento: (documentoId, motivo) =>
            docMut.remove.mutate({ documentoId, motivo }, { onError: erroToast("Não foi possível remover o anexo.") }),
        }}
        checklists={{
          checklists: checklists.data ?? [],
          loading: checklists.isPending && !checklists.data,
          onRemoveChecklist: (cid) =>
            checklistMut.removeChecklist.mutate(cid, { onError: erroToast("Não foi possível remover o checklist.") }),
          onAddItem: (checklistId, texto) =>
            checklistMut.addItem.mutate({ checklistId, texto }, { onError: erroToast("Não foi possível adicionar o item.") }),
          onToggleItem: (checklistId, itemId, concluido) =>
            checklistMut.toggleItem.mutate(
              { checklistId, itemId, concluido },
              { onError: erroToast("Não foi possível atualizar o item.") },
            ),
          onRemoveItem: (checklistId, itemId) =>
            checklistMut.removeItem.mutate({ checklistId, itemId }, { onError: erroToast("Não foi possível remover o item.") }),
        }}
        slots={{ afterTags: opts.afterTags ?? null }}
      />
    ),
  };

  const activity: CardHubActivityProps = {
    composer: {
      onPost: (corpo) =>
        notas.create.mutate({ corpo, tipo: "comentario" }, { onError: erroToast("Não foi possível enviar o comentário.") }),
      posting: notas.create.isPending,
    },
    timeline: {
      entries: flattenTimeline(timeline.data?.pages),
      loading: timeline.isPending && !timeline.data,
      error: timeline.isError ? describeError(timeline.error, "Não foi possível carregar a atividade.") : null,
      hasMore: timeline.hasNextPage,
      loadingMore: timeline.isFetchingNextPage,
      onLoadMore: () => void timeline.fetchNextPage(),
    },
  };

  return {
    geral,
    activity,
    showSkeleton,
    error: card.isError ? describeError(card.error, "Não foi possível carregar o card.") : null,
    nome: (card.data as { nome?: string } | undefined)?.nome ?? null,
  };
}
