/**
 * Comercial — the sales funnel page (roadmap R2–R5; wave-2 contract Slice C).
 *
 * Contains exactly: the pré-qualificação link, the funnel board and the
 * "Novo lead" button. The board is the seed `PipelineBoard` over
 * `@/lib/pipelines#comercialPipeline`:
 *   • drag-and-drop changes stage (touch: press-and-hold) — no stage dropdown,
 *   • columns editable in-header (add / rename / recolour / delete / reorder)
 *     for org admins only — the server enforces the same (`require_stage_admin`),
 *   • `onBeforeMove`: into the `fechado`-role stage ⇒ "Qual orçamento foi
 *     aceito?" picker; the chosen id rides as `extra.orcamento_id`, none ⇒
 *     "Gerar orçamento" instead (no close without an orçamento, R4),
 *   • a refused move (409/422) is rolled back by the seed and its server
 *     message toasted verbatim.
 *
 * A card opens the negócio `CardHubDialog`; its "Gerar orçamento" icon (and
 * the dialog's) open the shared `OrcamentoModal`.
 */
import { useState } from "react";
import { Plus } from "lucide-react";
import { PipelineBoard } from "@noctusai/lib/components";
import { Button, Skeleton } from "@noctusai/lib/design-system";
import { toast } from "sonner";

import { FechadoOrcamentoPicker, useFechadoGate } from "@/components/comercial/FechadoOrcamentoPicker";
import { LinkPreQualificacao } from "@/components/comercial/LinkPreQualificacao";
import { NegocioCardDialog } from "@/components/comercial/NegocioCardDialog";
import { NegocioCardFace } from "@/components/comercial/NegocioCardFace";
import { NovoLeadDialog } from "@/components/comercial/NovoLeadDialog";
import { OrcamentoModal } from "@/components/orcamento/OrcamentoModal";
import { describeError } from "@/lib/errors";
import { brl } from "@/lib/format";
import { comercialPipeline } from "@/lib/pipelines";
import { useIsOrgAdmin } from "@/lib/useIsOrgAdmin";
import type { Negocio } from "@/types/crm";

const ROLE_LABELS = { fechado: "Fechado (exige orçamento aceito)" };

export default function Comercial() {
  const isAdmin = useIsOrgAdmin();

  // The board query is shared with `PipelineBoard` (same key: no filtros), so
  // the open card always reads the freshest row after any mutation.
  const { data: colunas } = comercialPipeline.useBoard();
  const [abertoId, setAbertoId] = useState<string | null>(null);
  const aberto: Negocio | null =
    (abertoId && colunas?.flatMap((c) => c.cards).find((n) => n.id === abertoId)) || null;

  const [novoLead, setNovoLead] = useState(false);
  const [orcamento, setOrcamento] = useState<{ id?: string | null; negocioId?: string | null } | null>(null);

  const gate = useFechadoGate();

  function gerarOrcamento(negocio: Negocio) {
    setOrcamento({ negocioId: negocio.id });
  }

  return (
    <div className="mx-auto w-full max-w-full space-y-4 overflow-x-hidden p-4 sm:p-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold text-foreground">Comercial</h1>
          <p className="text-sm text-muted-foreground">Cada lead novo entra na primeira etapa do funil.</p>
        </div>
        <Button onClick={() => setNovoLead(true)} data-testid="comercial-novo-lead">
          <Plus className="mr-1 h-4 w-4" /> Novo lead
        </Button>
      </header>

      <LinkPreQualificacao />

      {/* The board scrolls sideways INSIDE its own frame — the page never does. */}
      <div className="-mx-4 min-w-0 sm:mx-0">
        <PipelineBoard<Negocio>
          hooks={comercialPipeline}
          formatValue={brl}
          emptyColumnLabel="Nenhum negócio nesta etapa"
          editableHeaders
          reorderableColumns
          canEditStages={isAdmin}
          roleLabels={ROLE_LABELS}
          onBeforeMove={gate.onBeforeMove}
          onMoveError={(err) => toast.error(describeError(err, "Não foi possível mover o negócio."))}
          columnClassName="flex-shrink-0 w-[85vw] max-w-80 sm:w-80 rounded-lg border bg-card text-card-foreground shadow-sm h-full flex flex-col overflow-hidden [&>[data-kanban-column-id]]:flex-1 [&>[data-kanban-column-id]]:p-3 [&>[data-kanban-column-id]]:overflow-y-auto"
          className="px-4 sm:px-0"
          loadingState={
            <div className="flex gap-3 overflow-hidden px-4 sm:px-0">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-80 w-[85vw] max-w-80 shrink-0 sm:w-80" />
              ))}
            </div>
          }
          onCardClick={(n) => setAbertoId(n.id)}
          renderCard={(n, { isDragging }) => (
            <NegocioCardFace negocio={n} isDragging={isDragging} onGerarOrcamento={gerarOrcamento} />
          )}
        />
      </div>

      <NovoLeadDialog open={novoLead} onClose={() => setNovoLead(false)} />

      <NegocioCardDialog
        negocio={aberto}
        onClose={() => setAbertoId(null)}
        onGerarOrcamento={gerarOrcamento}
        onAbrirOrcamento={(id) => setOrcamento({ id })}
      />

      <FechadoOrcamentoPicker
        negocio={gate.pendente}
        onEscolher={(orcamentoId) => gate.decidir({ extra: { orcamento_id: orcamentoId } })}
        onCancelar={() => gate.decidir(false)}
        onGerarOrcamento={(n) => {
          gate.decidir(false);
          gerarOrcamento(n);
        }}
      />

      <OrcamentoModal
        open={!!orcamento}
        onClose={() => setOrcamento(null)}
        orcamentoId={orcamento?.id ?? null}
        negocioId={orcamento?.negocioId ?? null}
        onOrcamentoChange={(o) => setOrcamento({ id: o.id, negocioId: o.negocio_id })}
      />
    </div>
  );
}
