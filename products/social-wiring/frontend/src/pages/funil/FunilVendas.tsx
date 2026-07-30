/**
 * Funil de Vendas — the lead pipeline at `/funil`.
 *
 * Cards are LEADS. They arrive automatically: migration 034 puts an AFTER
 * INSERT trigger on both `social_wiring.leads` and `social_wiring.meta_ads_leads`,
 * so a lead created through the API, the workbook importer, or the Meta
 * Lead-Ads sync lands on the first configured stage. There is deliberately no
 * "new card" button — creating one here would be a second way to make a card,
 * and the two would drift.
 *
 * Stages are per-organization DB rows the user edits via "Configurar etapas";
 * renaming one relabels every card and every history row that references it.
 * The defaults are erp-imobiliario's, verbatim since migration 037
 * (Qualificação → Visitas → Proposta → Negociação → Fechado).
 */
import { useState } from "react";
import { Search } from "lucide-react";

import { PipelineBoard } from "@noctusai/lib/components";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { LeadDetailModal } from "@/components/LeadDetailModal";
import { formatValor } from "./formatValor";
import { funilPipeline } from "@/lib/pipelines";
import { useAceitarProposta } from "@/hooks/usePipelineSeam";
import { NegociacaoCard } from "./components/NegociacaoCard";
import { origemDaNegociacao, type CardOrigem } from "@/types/pipeline";

export default function FunilVendas() {
  const [busca, setBusca] = useState("");
  // The card that is open in the detail modal. Holds the ORIGIN rather than
  // the card, because that is all the modal needs and it keeps a stale card
  // object from outliving a refetch behind an open modal.
  const [detalhe, setDetalhe] = useState<CardOrigem | null>(null);
  const { mutate: aceitarProposta, isPending: aceitando, variables } =
    useAceitarProposta();

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
        filtros={{ busca: busca || undefined }}
        formatValue={formatValor}
        emptyColumnLabel="Nenhum lead nesta etapa"
        toolbar={
          <div className="relative min-w-[240px] flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              className="pl-9"
              placeholder="Buscar por nome, contato ou empreendimento..."
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
            />
          </div>
        }
        loadingState={
          <div className="flex gap-4 overflow-x-auto pb-4">
            {[1, 2, 3, 4, 5].map((i) => (
              <Skeleton key={i} className="h-96 w-80 flex-shrink-0" />
            ))}
          </div>
        }
        onCardClick={(negociacao) => setDetalhe(origemDaNegociacao(negociacao))}
        renderCard={(negociacao, { isDragging }) => (
          <NegociacaoCard
            negociacao={negociacao}
            isDragging={isDragging}
            onAceitarProposta={aceitarProposta}
            // Scope the pending state to the card actually being accepted —
            // a bare `isPending` would spin every card in the column.
            aceitandoProposta={aceitando && variables === negociacao.id}
          />
        )}
      />

      {/* The same modal the Leads table and the Processos board open. */}
      <LeadDetailModal
        open={!!detalhe}
        onClose={() => setDetalhe(null)}
        leadId={detalhe?.leadId ?? null}
        campanha={detalhe?.campanha ?? null}
      />
    </div>
  );
}
