/**
 * The "Lembretes" subpage, wired to a `createCardHubHooks` instance — same
 * shape as `useCardHubGeral.tsx`'s mapping, ONE for every igig card (cliente
 * and negócio both mount `LembretesSubpage`). `CardHubConfig.lembretes_crud`
 * is `True` on both `app/card_hub.py` configs, so the routes exist for
 * either entity.
 *
 * "Responsável" options are `igig.profissional` — the SAME source `useCardHubGeral`
 * reads for "Membros" (any active team member, not just the card's currently
 * assigned ones: `create_lembrete`/`update_lembrete` accept any
 * `member_source.table` row, matching the backend's own permissiveness).
 */
import { Bell } from "lucide-react";
import {
  cardHubLoadingState,
  type CardHubHooks,
  type CardSubpage,
  LembretesSubpage,
} from "@noctusai/lib/components";
import { toast } from "sonner";

import { useProfissionais } from "@/hooks/useCustos";
import { describeError } from "@/lib/errors";

const NONE = "__none__";

export function useLembretesSubpage(hub: CardHubHooks, id: string | null): CardSubpage<"lembretes"> {
  const lembretes = hub.useLembretes(id);
  const mut = hub.useLembreteMutations(id ?? NONE);
  const profissionais = useProfissionais();
  const { showSkeleton, isRefreshing } = cardHubLoadingState(lembretes);

  const erroToast = (fallback: string) => (err: unknown) => toast.error(describeError(err, fallback));

  // Which single row (if any) is mid-`PATCH`/`DELETE` — both mutations are
  // ONE shared instance across every row (matches `checklistMut`'s shape),
  // so `.variables` of whichever is `isPending` names the row.
  const editandoId = mut.atualizar.isPending ? mut.atualizar.variables?.lembreteId : undefined;
  const excluindoId = mut.remover.isPending ? mut.remover.variables : undefined;
  const savingId = editandoId ?? excluindoId ?? null;

  return {
    key: "lembretes",
    label: "Lembretes",
    icon: Bell,
    render: () => (
      <LembretesSubpage
        lembretes={lembretes.data ?? []}
        loading={showSkeleton}
        refreshing={isRefreshing}
        error={lembretes.isError ? describeError(lembretes.error, "Não foi possível carregar os lembretes.") : null}
        responsaveis={profissionais.profissionais
          .filter((p) => p.ativo)
          .map((p) => ({ id: p.id, nome: p.nome }))}
        creating={mut.criar.isPending}
        savingId={savingId}
        onCreate={(body) => mut.criar.mutate(body, { onError: erroToast("Não foi possível criar o lembrete.") })}
        onUpdate={(lembreteId, body) =>
          mut.atualizar.mutate({ lembreteId, body }, { onError: erroToast("Não foi possível atualizar o lembrete.") })
        }
        onDelete={(lembreteId) =>
          mut.remover.mutate(lembreteId, { onError: erroToast("Não foi possível excluir o lembrete.") })
        }
      />
    ),
  };
}
