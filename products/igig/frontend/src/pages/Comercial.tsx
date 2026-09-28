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
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Archive, Plus } from "lucide-react";
import { PipelineBoard } from "@noctusai/lib/components";
import { Button, Skeleton } from "@noctusai/lib/design-system";
import { toast } from "sonner";

import { FechadoOrcamentoPicker, useFechadoGate } from "@/components/comercial/FechadoOrcamentoPicker";
import { LinkPreQualificacao } from "@/components/comercial/LinkPreQualificacao";
import { NegocioCardDialog } from "@/components/comercial/NegocioCardDialog";
import { NegocioCardFace } from "@/components/comercial/NegocioCardFace";
import { NovoLeadDialog } from "@/components/comercial/NovoLeadDialog";
import { PerdidosView } from "@/components/comercial/PerdidosView";
import { StageRolePanel } from "@/components/common/StageRolePanel";
import { OrcamentoModal } from "@/components/orcamento/OrcamentoModal";
import { useAtribuirPapelEtapaComercial, useNegocioPorId } from "@/hooks/useComercial";
import { describeError } from "@/lib/errors";
import { brl } from "@/lib/format";
import { comercialPipeline } from "@/lib/pipelines";
import { useIsOrgAdmin } from "@/lib/useIsOrgAdmin";
import type { Negocio } from "@/types/crm";

const ROLE_LABELS = { fechado: "Fechado (exige orçamento aceito)" };

export default function Comercial() {
  const isAdmin = useIsOrgAdmin();
  const [params, setParams] = useSearchParams();

  // The board query is shared with `PipelineBoard` (same key: no filtros), so
  // the open card always reads the freshest row after any mutation.
  const { data: colunas } = comercialPipeline.useBoard();
  // `?negocio=<id>` deep-links a card open — automation notifications point
  // here (achado #4/plat#10) but this page never read the param at all.
  const [abertoId, setAbertoId] = useState<string | null>(() => params.get("negocio"));
  useEffect(() => {
    const doParam = params.get("negocio");
    if (doParam && doParam !== abertoId) setAbertoId(doParam);
    // Only react to the URL changing (e.g. a new notification click) —
    // never re-run on every abertoId set from clicking a card, or closing
    // the card would immediately reopen it from a stale param.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);

  function fecharCard() {
    setAbertoId(null);
    if (params.has("negocio")) {
      setParams(
        (atual) => {
          const prox = new URLSearchParams(atual);
          prox.delete("negocio");
          return prox;
        },
        { replace: true },
      );
    }
  }

  const doBoard =
    (abertoId && colunas?.flatMap((c) => c.cards).find((n) => n.id === abertoId)) || null;
  // The board never holds a `perdido` card (`GET /board` is aberto+ganho
  // only) — a deep link / orçamento that names one falls back to fetching it
  // by id, so its archive still opens (roadmap gap G-2).
  const fallback = useNegocioPorId(abertoId && !doBoard ? abertoId : null);
  const aberto: Negocio | null = doBoard || fallback.data || null;

  const [novoLead, setNovoLead] = useState(false);
  const [perdidos, setPerdidos] = useState(false);
  const [orcamento, setOrcamento] = useState<{ id?: string | null; negocioId?: string | null } | null>(null);

  const gate = useFechadoGate();

  // "Papéis das etapas" (comercial achado #14) — the seed's generic stage
  // editor ("Configurar etapas") can tell you a role is blocking a delete,
  // but has no control to actually reassign it. `colunas` already carries
  // each column's `stage`, so no extra fetch.
  const etapasComPapel = useMemo(() => (colunas ?? []).map((c) => c.stage), [colunas]);
  const atribuirPapel = useAtribuirPapelEtapaComercial();

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
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setPerdidos(true)} data-testid="comercial-perdidos">
            <Archive className="mr-1 h-4 w-4" /> Perdidos
          </Button>
          <Button onClick={() => setNovoLead(true)} data-testid="comercial-novo-lead">
            <Plus className="mr-1 h-4 w-4" /> Novo lead
          </Button>
        </div>
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

      {isAdmin && etapasComPapel.length > 0 && (
        <StageRolePanel
          roleLabels={ROLE_LABELS}
          stages={etapasComPapel}
          isPending={atribuirPapel.isPending}
          onAssign={(etapaId, papel) =>
            atribuirPapel.mutate(
              { etapaId, papel },
              { onError: (erro) => toast.error(describeError(erro, "Não foi possível reatribuir o papel.")) },
            )
          }
        />
      )}

      <NovoLeadDialog open={novoLead} onClose={() => setNovoLead(false)} />

      <NegocioCardDialog
        negocio={aberto}
        onClose={fecharCard}
        onGerarOrcamento={gerarOrcamento}
        onAbrirOrcamento={(id) => setOrcamento({ id })}
      />

      <PerdidosView
        open={perdidos}
        onClose={() => setPerdidos(false)}
        onReaberto={(id) => {
          setPerdidos(false);
          setAbertoId(id);
        }}
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
