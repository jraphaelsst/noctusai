/**
 * A Funil card — one lead in the pipeline.
 *
 * Renders whichever origin the card has (a `leads` row or a `meta_ads_leads`
 * row) and deep-links back into the Leads page, which is where the lead is
 * actually managed. The card deliberately does NOT duplicate lead editing:
 * this board moves deals, the Leads module owns the lead.
 */
import { ExternalLink, Megaphone, CheckCircle2 } from "lucide-react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  contatoDaNegociacao,
  linkParaLeads,
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
  const contato = contatoDaNegociacao(negociacao);
  const deCampanha = !!negociacao.meta_ads_lead_id;

  // The accept seam is keyed on the stage's ROLE, never its name — stages are
  // user-editable, so renaming "Proposta" must not remove this button.
  const podeAceitar =
    negociacao.etapa_rel?.papel === "proposta_aceite" &&
    negociacao.status === "aberta" &&
    !!onAceitarProposta;

  return (
    <div
      className={`rounded-lg border bg-card p-3 shadow-sm ${isDragging ? "opacity-60" : ""}`}
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
            // MUST stopPropagation: the card body carries the organ's dnd-kit
            // drag listeners, and a click that reaches them starts a drag
            // instead of firing this handler.
            e.stopPropagation();
            onAceitarProposta?.(negociacao.id);
          }}
        >
          <CheckCircle2 className="mr-1 h-4 w-4" />
          {aceitandoProposta ? "Aceitando..." : "Aceitar Proposta"}
        </Button>
      )}

      <div className="mt-3 flex items-center justify-between border-t pt-2">
        <Link
          to={linkParaLeads(negociacao)}
          className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          onClick={(e) => e.stopPropagation()}
        >
          <ExternalLink className="h-3 w-3" />
          Ver no Leads
        </Link>
      </div>
    </div>
  );
}
