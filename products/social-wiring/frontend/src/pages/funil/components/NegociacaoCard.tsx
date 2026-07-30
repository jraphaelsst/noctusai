/**
 * A Funil card — one lead in the pipeline.
 *
 * The card is a SUMMARY. Clicking it opens the lead's full record in the
 * shared `LeadDetailModal` — the same modal the Leads table opens, so the
 * two surfaces cannot drift.
 *
 * It used to end in a "Ver no Leads" link that navigated to
 * `/leads?q=<contato>` and left the user to find the row themselves. That
 * went with the modal: deep-linking into a filtered table is what you do
 * when you have no detail view, not a feature.
 *
 * The click is wired by the board (`PipelineBoard onCardClick` →
 * `KanbanCard onActivate`), which owns the drag-vs-click discrimination.
 * Anything interactive in here must `stopPropagation` — a button click is
 * not a card click.
 */
import { Megaphone, CheckCircle2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatPhone } from "@noctusai/lib/phone";
import {
  contatoDaNegociacao,
  nomeDaNegociacao,
  type NegociacaoVenda,
} from "@/types/pipeline";

export interface NegociacaoCardProps {
  negociacao: NegociacaoVenda;
  isDragging?: boolean;
  onAceitarProposta?: (negociacaoId: string) => void;
  aceitandoProposta?: boolean;
}

export function NegociacaoCard({
  negociacao,
  isDragging,
  onAceitarProposta,
  aceitandoProposta,
}: NegociacaoCardProps) {
  const nome = nomeDaNegociacao(negociacao);
  const contatoRaw = contatoDaNegociacao(negociacao);
  // Through the platform's one phone seam, so the card shows the same string
  // as the modal, the Leads table and a WhatsApp lookup. An e-mail passes
  // through untouched — `formatPhone` returns what it cannot canonicalize.
  const contato = contatoRaw?.includes("@") ? contatoRaw : formatPhone(contatoRaw);
  const deCampanha = !!negociacao.meta_ads_lead_id;

  // The accept seam is keyed on the stage's ROLE, never its name — stages are
  // user-editable, so renaming "Proposta" must not remove this button.
  const podeAceitar =
    negociacao.etapa_rel?.papel === "proposta_aceite" &&
    negociacao.status === "aberta" &&
    !!onAceitarProposta;

  return (
    <div
      className={`cursor-pointer rounded-lg border bg-card p-3 shadow-sm transition-colors hover:border-primary/40 ${
        isDragging ? "opacity-60" : ""
      }`}
      data-testid="negociacao-card"
    >
      <div className="flex items-start gap-3">
        <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-primary/10 text-sm font-semibold text-primary">
          {nome.slice(0, 2).toUpperCase()}
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate font-medium">{nome}</p>
          {contato && (
            <p className="truncate text-xs text-muted-foreground">{contato}</p>
          )}
          <div className="mt-1 flex flex-wrap items-center gap-1">
            {deCampanha ? (
              <Badge variant="secondary" className="gap-1">
                <Megaphone className="h-3 w-3" />
                Campanha
              </Badge>
            ) : (
              negociacao.lead?.origem_raw && (
                <Badge variant="outline">{negociacao.lead.origem_raw}</Badge>
              )
            )}
            {negociacao.lead?.empreendimento && (
              <Badge variant="outline" className="truncate max-w-[140px]">
                {negociacao.lead.empreendimento}
              </Badge>
            )}
          </div>
        </div>
      </div>

      {podeAceitar && (
        <Button
          size="sm"
          className="mt-3 w-full"
          disabled={aceitandoProposta}
          onClick={(e) => {
            // MUST stopPropagation, now twice over: the card body carries the
            // organ's dnd-kit drag listeners AND its click-to-open handler, so
            // an un-stopped click would start a drag and open the detail modal
            // on top of accepting the proposal.
            e.stopPropagation();
            onAceitarProposta?.(negociacao.id);
          }}
        >
          <CheckCircle2 className="mr-1 h-4 w-4" />
          {aceitandoProposta ? "Aceitando..." : "Aceitar Proposta"}
        </Button>
      )}
    </div>
  );
}
