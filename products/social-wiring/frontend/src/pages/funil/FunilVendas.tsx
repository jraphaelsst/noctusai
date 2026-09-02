/**
 * Funil de Vendas — the lead pipeline at `/funil`.
 *
 * Cards are LEADS. They arrive automatically: migration 034 puts an AFTER
 * INSERT trigger on both `social_wiring.leads` and `social_wiring.meta_ads_leads`,
 * so a lead created through the API, the workbook importer, or the Meta
 * Lead-Ads sync lands on the first configured stage.
 *
 * "Novo lead" creates a LEAD, never a card — the card is still spawned by
 * migration 034's trigger, exactly as it is for a campaign lead. That is what
 * keeps the original "no new-card button" rule intact: there is still only ONE
 * way a card comes into existence. A button that inserted a card directly
 * would be the second path that rule forbids, and the two would drift.
 *
 * It reuses `LeadFormDialog` and the same `useLeadMutations().create` the Base
 * de Leads page uses, so a hand-entered lead is byte-identical in shape to one
 * typed there — and the origem selector is what records which portal it came
 * from (ZAP / Imóvel Web / Meta Ads all already exist as `lead_sources` rows).
 *
 * Stages are per-organization DB rows the user edits via "Configurar etapas";
 * renaming one relabels every card and every history row that references it.
 * The defaults are erp-imobiliario's, verbatim since migration 037
 * (Qualificação → Visitas → Proposta → Atendimento → Fechado).
 */
import { useState } from "react";
import { Plus, Search } from "lucide-react";
import { toast } from "sonner";

import { PipelineBoard } from "@noctusai/lib/components";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { LeadDetailModal } from "@/components/LeadDetailModal";
import { ClienteDetailModal } from "@/components/ClienteDetailModal";
import { formatValor } from "./formatValor";
import { funilPipeline } from "@/lib/pipelines";
import { useAceitarProposta } from "@/hooks/usePipelineSeam";
import { useLeadMutations } from "@/hooks/useLeads";
import {
  LeadFormDialog,
  type LeadFormValues,
} from "@/pages/leads/components/LeadFormDialog";
import { describeError } from "@/pages/leads/utils";
import { AtendimentoCard } from "./components/AtendimentoCard";
import { origemDoAtendimento, type CardOrigem } from "@/types/pipeline";

//: Cards per column the board asks for, and the step each "Carregar mais"
//: adds. Mirrors the backend default (`boards.LIMITE_CARDS_PADRAO`); the
//: server caps the request at 1000 either way.
const CARDS_POR_ETAPA = 50;

export default function FunilVendas() {
  const [busca, setBusca] = useState("");
  // How many cards to request per column. Raised by "Carregar mais" — one
  // control for the whole board rather than one per column, because the
  // columns that overflow are the early ones and a user working the board
  // wants depth everywhere, not in one stage at a time.
  const [limite, setLimite] = useState(CARDS_POR_ETAPA);
  // The card that is open in the detail modal. Holds the ORIGIN rather than
  // the card, because that is all the modal needs and it keeps a stale card
  // object from outliving a refetch behind an open modal.
  //
  // Used ONLY as the fallback now: an atendimento whose person layer has not
  // resolved yet (`cliente_id === null`) has no card to open, and showing the
  // old field list beats showing nothing. Everything else opens the real card.
  const [detalhe, setDetalhe] = useState<CardOrigem | null>(null);
  // The atendimento IS the person's card (D1) — clicking it opens the same
  // dialog the Clientes board opens, keyed by `cliente_id`. Before this the
  // funil opened a read-only field list, so the card existed on one board and
  // was unreachable from the one people actually work in.
  const [clienteAberto, setClienteAberto] = useState<string | null>(null);
  const { mutate: aceitarProposta, isPending: aceitando, variables } =
    useAceitarProposta();

  // "Novo lead" — the SAME mutation Base de Leads uses, so a lead entered
  // here is indistinguishable from one entered there or one that arrived from
  // a campaign. The board picks the new card up on the mutation's own
  // invalidation; nothing here inserts a card.
  const [novoLeadAberto, setNovoLeadAberto] = useState(false);
  const { create } = useLeadMutations();

  function criarLead(values: LeadFormValues) {
    create.mutate(values, {
      onSuccess: () => {
        toast.success("Lead criado — o card entra na primeira etapa.");
        setNovoLeadAberto(false);
      },
      onError: (err) => toast.error(describeError(err, "Erro ao criar lead.")),
    });
  }

  return (
    <div className="container mx-auto p-4 sm:p-6">
      <div className="mb-6">
        <h1 className="mb-1 text-2xl font-bold">Funil de Vendas</h1>
        <p className="text-sm text-muted-foreground">
          Cada lead novo entra automaticamente na primeira etapa — inclusive os
          que chegam de campanha.
        </p>
      </div>

      <PipelineBoard
        hooks={funilPipeline}
        filtros={{ busca: busca || undefined, limite_por_etapa: limite }}
        formatValue={formatValor}
        emptyColumnLabel="Nenhum lead nesta etapa"
        onLoadMore={() => setLimite((n) => n + CARDS_POR_ETAPA)}
        loadMoreLabel={`Carregar mais ${CARDS_POR_ETAPA} por etapa`}
        toolbar={
          <>
            <div className="relative min-w-[240px] flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                className="pl-9"
                placeholder="Buscar por nome, contato ou empreendimento..."
                value={busca}
                onChange={(e) => setBusca(e.target.value)}
              />
            </div>
            <Button
              onClick={() => setNovoLeadAberto(true)}
              className="gap-2"
              data-testid="funil-btn-novo-lead"
            >
              <Plus className="h-4 w-4" />
              Novo lead
            </Button>
          </>
        }
        loadingState={
          <div className="flex gap-4 overflow-x-auto pb-4">
            {[1, 2, 3, 4, 5].map((i) => (
              <Skeleton key={i} className="h-96 w-80 flex-shrink-0" />
            ))}
          </div>
        }
        onCardClick={(atendimento) => {
          if (atendimento.cliente_id) {
            setClienteAberto(atendimento.cliente_id);
          } else {
            // No person resolved yet — the backfill runs every 6h and new
            // leads land unattached in between. Never a dead click.
            setDetalhe(origemDoAtendimento(atendimento));
          }
        }}
        renderCard={(atendimento, { isDragging }) => (
          <AtendimentoCard
            atendimento={atendimento}
            isDragging={isDragging}
            onAceitarProposta={aceitarProposta}
            // Scope the pending state to the card actually being accepted —
            // a bare `isPending` would spin every card in the column.
            aceitandoProposta={aceitando && variables === atendimento.id}
          />
        )}
      />

      {/* The card — the atendimento's person. */}
      <ClienteDetailModal
        clienteId={clienteAberto}
        open={!!clienteAberto}
        onClose={() => setClienteAberto(null)}
      />

      {/* Fallback for an atendimento with no cliente yet (see onCardClick). */}
      <LeadDetailModal
        open={!!detalhe}
        onClose={() => setDetalhe(null)}
        leadId={detalhe?.leadId ?? null}
        campanha={detalhe?.campanha ?? null}
      />

      {/* Create — the same dialog Base de Leads uses (no `lead` prop = create
          mode). Its "Origem" select is where the portal is chosen. */}
      <LeadFormDialog
        open={novoLeadAberto}
        onOpenChange={setNovoLeadAberto}
        onSubmit={criarLead}
        isPending={create.isPending}
      />
    </div>
  );
}
