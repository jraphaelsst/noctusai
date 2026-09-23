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
import { useMemo, useState } from "react";
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

import { esteiraPipeline, type TarefaCard } from "@/hooks/useEsteira";
import { useIsOrgAdmin } from "@/lib/useIsOrgAdmin";
import { decidirMovimento } from "./moveRules";
import { NovaTarefaDialog } from "./NovaTarefaDialog";
import { TarefaCardFace } from "./TarefaCardFace";
import { TarefaDetalhe } from "./TarefaDetalhe";

export interface EsteiraBoardProps {
  /** Show only this cliente's tarefas (the Clientes card's Esteira tab). */
  clienteId?: string;
  className?: string;
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

export function EsteiraBoard({ clienteId, className }: EsteiraBoardProps) {
  const { user } = useAuthStore();
  const usuarioId = user?.id ?? null;
  const podeEditarEtapas = useIsOrgAdmin();

  const filtros = useMemo(() => (clienteId ? { cliente_id: clienteId } : undefined), [clienteId]);
  // Same key as the board's own query — a cache read, not a second request.
  // The open card is looked up here by id so the sheet always shows the
  // CURRENT row (after a move, a timer or a link), never a stale snapshot.
  const { data: colunas } = esteiraPipeline.useBoard(filtros);

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
        onBeforeMove={onBeforeMove}
        onMoveError={(erro) =>
          // The server's pt-BR `detail` (409 `etapa_invalida`, 422
          // `motivo_obrigatorio`) is the message; the card already rolled back.
          toast.error(erro.message || "Não foi possível mover a tarefa.")
        }
        toolbar={
          <Button size="sm" className="min-h-10" onClick={() => setNovaAberta(true)}>
            <Plus className="mr-1 h-4 w-4" />
            Nova tarefa
          </Button>
        }
      />

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
        onClose={() => setAbertaId(null)}
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
