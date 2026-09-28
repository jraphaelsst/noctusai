/**
 * `<EsteiraBoard clienteId?/>` — the Esteira de Produção board, reusable.
 *
 * Mounted by the Esteira page (all clientes, `?cliente=` filter) and by the
 * Clientes card's Esteira tab (slice F, one cliente — roadmap R9). Everything
 * a board needs lives here so both mounts behave identically: the seed
 * `PipelineBoard`, the move rules, the reason dialog, the card detail sheet
 * and the "nova tarefa" sheet.
 *
 * Rules (R3), enforced client-side BEFORE the request (`moveRules.ts`) and
 * again server-side (authoritative):
 *   - forward exactly one stage — a skip is cancelled with a toast;
 *   - backward any distance, only with a reason (seed `MotivoMoveDialog`);
 *     leaving the approval stage backwards is labelled "Refação".
 * Stage headers are editable in place (rename / recolour / delete / add /
 * drag-reorder) for org admins only; the server enforces the same gate
 * (`exigir_admin_da_org`) — this only hides what it would refuse.
 *
 * MOBILE (R0): the board scrolls horizontally INSIDE its own container
 * (`min-w-0` chain + the seed board's `overflow-x-auto`), never the page — the
 * old page overflowed to scrollWidth 2049. Columns are ~82vw on a phone so the
 * next column peeks in, and each column scrolls vertically on its own.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { useAuthStore } from "@noctusai/seed/infra";
import {
  MotivoMoveDialog,
  PipelineBoard,
  type MoveDecision,
  type MoveIntentContext,
} from "@noctusai/lib/components";
import { Button } from "@noctusai/lib/design-system";
import { Plus } from "lucide-react";

import { StageRolePanel } from "@/components/common/StageRolePanel";
import {
  ESTEIRA_ROLE_LABELS,
  esteiraPipeline,
  useAtribuirPapelEtapa,
  type TarefaCard,
} from "@/hooks/useEsteira";
import { describeError } from "@/lib/errors";
import { useIsOrgAdmin } from "@/lib/useIsOrgAdmin";
import { decidirMovimento } from "./moveRules";
import { NovaTarefaDialog } from "./NovaTarefaDialog";
import { TarefaCardFace } from "./TarefaCardFace";
import { TarefaDetalhe } from "./TarefaDetalhe";

export interface EsteiraBoardProps {
  /** Show only this cliente's tarefas (the Clientes card's Esteira tab). */
  clienteId?: string;
  className?: string;
  /**
   * `?tarefa=<id>` deep link (automation/card-hub reminder notifications
   * point at `/esteira?tarefa=<id>` — Esteira.tsx only; the Clientes card's
   * embedded mount never passes this). Opens it ONCE it is found on the
   * CURRENTLY loaded board — a client filter active on the page can hide a
   * tarefa belonging to another cliente, same honest limit `onDeepLinkResolved`
   * reports (there is no single-tarefa-by-id endpoint to fall back to, unlike
   * Comercial's `?negocio=` + `useNegocioPorId`).
   */
  deepLinkTarefaId?: string | null;
  /** Fires exactly once per `deepLinkTarefaId` value, once the board has
   * loaded — `found` tells the caller whether the sheet actually opened. */
  onDeepLinkResolved?: (found: boolean) => void;
  /** Fires whenever the open tarefa's sheet closes — lets the page clear its
   * own `?tarefa=` param, mirroring Comercial's `fecharCard`. */
  onCardClose?: () => void;
}

/** The seed default column, re-sized for a phone first. */
const COLUNA =
  "flex-shrink-0 w-[82vw] max-w-80 sm:w-80 rounded-lg border bg-card text-card-foreground shadow-sm " +
  "flex flex-col overflow-hidden max-h-[calc(100dvh-13rem)] " +
  "[&>[data-kanban-column-id]]:flex-1 [&>[data-kanban-column-id]]:p-3 [&>[data-kanban-column-id]]:overflow-y-auto";

interface MotivoPendente {
  resolve: (decisao: MoveDecision) => void;
  titulo: string;
  refacao: boolean;
}

export function EsteiraBoard({
  clienteId, className, deepLinkTarefaId, onDeepLinkResolved, onCardClose,
}: EsteiraBoardProps) {
  const { user } = useAuthStore();
  const usuarioId = user?.id ?? null;
  const podeEditarEtapas = useIsOrgAdmin();

  const filtros = useMemo(() => (clienteId ? { cliente_id: clienteId } : undefined), [clienteId]);
  // Same key as the board's own query — a cache read, not a second request.
  // The open card is looked up here by id so the sheet always shows the
  // CURRENT row (after a move, a timer or a link), never a stale snapshot.
  const { data: colunas, isPending: carregandoBoard } = esteiraPipeline.useBoard(filtros);

  // Stages-only, not the board: the "Papéis das etapas" picker (below) only
  // needs id/label/papel. `enabled: podeEditarEtapas` matches BOTH the old
  // behaviour (only an admin ever fetched anything for this picker — it
  // wasn't even mounted for anyone else) and `PipelineBoard`'s own
  // `reorderableColumns`+`canEditStages` gate below, which fetches this SAME
  // query (`useStages`, admin-only) for the "Configurar etapas" panel —
  // TanStack dedupes the identical key+enabled pair, so this is a cache read,
  // never a second request. The seed's stage-list endpoint returns EVERY
  // stage (`incluir_inativas=True`, so the editor can reactivate one) while
  // the board only ever carries active stages' columns — `.filter((e) =>
  // e.ativo)` keeps the picker's options exactly what `useBoard()`-sourced
  // `etapas` used to offer.
  const { data: todasEtapas } = esteiraPipeline.useStages({ enabled: podeEditarEtapas });
  const etapasComPapel = useMemo(
    () => (todasEtapas ?? []).filter((e) => e.ativo),
    [todasEtapas],
  );
  const atribuirPapel = useAtribuirPapelEtapa();

  const [motivoPendente, setMotivoPendente] = useState<MotivoPendente | null>(null);
  const [abertaId, setAbertaId] = useState<string | null>(null);
  const [novaAberta, setNovaAberta] = useState(false);

  const aberta = useMemo(() => {
    if (!abertaId) return null;
    for (const coluna of colunas ?? []) {
      const card = coluna.cards.find((c) => c.id === abertaId);
      if (card) return { card, etapa: coluna.stage?.label ?? null };
    }
    return null;
  }, [abertaId, colunas]);

  // `?tarefa=<id>` deep link — resolved exactly once per id, only once the
  // board has actually loaded (an empty `colunas` mid-fetch must never read
  // as "not found"). A client filter active on the page can hide a tarefa
  // that genuinely exists, same honest limit `onDeepLinkResolved`'s caller
  // (Esteira.tsx) names in its not-found message.
  const deepLinkResolvidoRef = useRef<string | null>(null);
  useEffect(() => {
    if (!deepLinkTarefaId || carregandoBoard) return;
    if (deepLinkResolvidoRef.current === deepLinkTarefaId) return;
    deepLinkResolvidoRef.current = deepLinkTarefaId;
    const encontrada = (colunas ?? []).some((c) => c.cards.some((t) => t.id === deepLinkTarefaId));
    if (encontrada) setAbertaId(deepLinkTarefaId);
    onDeepLinkResolved?.(encontrada);
  }, [deepLinkTarefaId, carregandoBoard, colunas, onDeepLinkResolved]);

  function onBeforeMove(ctx: MoveIntentContext<TarefaCard>): MoveDecision | Promise<MoveDecision> {
    const decisao = decidirMovimento(ctx);
    if (decisao.tipo === "cancelar") {
      toast.error(decisao.mensagem);
      return false;
    }
    if (decisao.tipo === "seguir") return true;
    return new Promise<MoveDecision>((resolve) =>
      setMotivoPendente({ resolve, titulo: decisao.titulo, refacao: decisao.refacao }),
    );
  }

  function fecharMotivo(decisao: MoveDecision) {
    motivoPendente?.resolve(decisao);
    setMotivoPendente(null);
  }

  return (
    <div className={`min-w-0 max-w-full ${className ?? ""}`} data-testid="esteira-board">
      <PipelineBoard
        hooks={esteiraPipeline}
        filtros={filtros}
        className="min-w-0 max-w-full"
        columnClassName={COLUNA}
        renderCard={(tarefa, { isDragging }) => (
          <TarefaCardFace tarefa={tarefa} isDragging={isDragging} />
        )}
        onCardClick={(tarefa) => setAbertaId(tarefa.id)}
        formatValue={() => ""}
        emptyColumnLabel="Nenhuma tarefa"
        editableHeaders
        reorderableColumns
        canEditStages={podeEditarEtapas}
        roleLabels={ESTEIRA_ROLE_LABELS}
        onBeforeMove={onBeforeMove}
        onMoveError={(erro) =>
          // The server's pt-BR `detail` (409 `etapa_invalida`, 422
          // `motivo_obrigatorio`) is the message; the card already rolled
          // back. `describeError` strips the `[status]` prefix `err.message`
          // otherwise carries (achado 10).
          toast.error(describeError(erro, "Não foi possível mover a tarefa."))
        }
        toolbar={
          <Button size="sm" className="min-h-10" onClick={() => setNovaAberta(true)}>
            <Plus className="mr-1 h-4 w-4" />
            Nova tarefa
          </Button>
        }
      />

      {podeEditarEtapas && (
        <div className="mt-3">
          <StageRolePanel
            roleLabels={ESTEIRA_ROLE_LABELS}
            stages={etapasComPapel}
            isPending={atribuirPapel.isPending}
            onAssign={(etapaId, papel) =>
              atribuirPapel.mutate(
                { etapaId, papel },
                {
                  onError: (erro) =>
                    toast.error(describeError(erro, "Não foi possível reatribuir o papel.")),
                },
              )
            }
          />
        </div>
      )}

      {motivoPendente && (
        <MotivoMoveDialog
          open
          required
          title={motivoPendente.titulo}
          description={
            motivoPendente.refacao
              ? "Sair da aprovação do cliente conta uma refação para esta tarefa."
              : "Voltar uma tarefa exige um motivo — ele fica no histórico."
          }
          placeholder={motivoPendente.refacao ? "O que precisa ser refeito?" : "Por que voltar?"}
          confirmLabel={motivoPendente.refacao ? "Registrar refação" : "Devolver"}
          onCancel={() => fecharMotivo(false)}
          onConfirm={(motivo) => fecharMotivo({ motivo })}
        />
      )}

      <TarefaDetalhe
        tarefa={aberta?.card ?? null}
        etapaLabel={aberta?.etapa ?? null}
        usuarioId={usuarioId}
        onClose={() => {
          setAbertaId(null);
          onCardClose?.();
        }}
      />

      <NovaTarefaDialog
        open={novaAberta}
        onClose={() => setNovaAberta(false)}
        clienteId={clienteId}
      />
    </div>
  );
}

export default EsteiraBoard;
