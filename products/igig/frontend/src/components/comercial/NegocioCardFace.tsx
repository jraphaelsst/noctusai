/**
 * The funnel card face: lead nome/empresa, origem badge, valor, responsável,
 * and the "Gerar orçamento" icon (roadmap R5 — "lead cards have a Gerar
 * orçamento icon opening the same modal").
 *
 * igig's own face rather than the seed `CardHubFace`: the board DTO carries
 * the lead + responsável projection this face shows, not the card-hub badges
 * `CardHubFace` renders (those need a per-card `/card` read). Buttons inside
 * stop propagation — a button click is not a card click (`PipelineBoard`).
 */
import { FilePlus2, Trophy, UserRound } from "lucide-react";
import { Badge } from "@noctusai/lib/design-system";
import { cn } from "@noctusai/lib";

import { brl } from "@/lib/format";
import { ORIGEM_LABEL, type Negocio } from "@/types/crm";

export interface NegocioCardFaceProps {
  negocio: Negocio;
  isDragging?: boolean;
  onGerarOrcamento?: (negocio: Negocio) => void;
}

export function NegocioCardFace({ negocio, isDragging, onGerarOrcamento }: NegocioCardFaceProps) {
  const lead = negocio.lead;
  const titulo = lead?.empresa || lead?.nome || negocio.titulo;
  const subtitulo = lead?.empresa && lead?.nome !== lead?.empresa ? lead?.nome : null;
  const origem = lead?.origem ? ORIGEM_LABEL[lead.origem] ?? lead.origem : null;

  return (
    <div
      data-testid="negocio-card"
      className={cn(
        "rounded-lg border border-border bg-background p-3 text-sm shadow-sm transition-shadow",
        isDragging && "shadow-lg ring-2 ring-primary/40",
      )}
    >
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <p className="truncate font-medium text-foreground">{titulo}</p>
          {subtitulo ? <p className="truncate text-xs text-muted-foreground">{subtitulo}</p> : null}
        </div>
        {negocio.status === "aberto" && onGerarOrcamento ? (
          <button
            type="button"
            aria-label={`Gerar orçamento — ${titulo}`}
            title="Gerar orçamento"
            onPointerDown={(e) => e.stopPropagation()}
            onClick={(e) => {
              e.stopPropagation();
              onGerarOrcamento(negocio);
            }}
            className="-m-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-primary"
          >
            <FilePlus2 className="h-4 w-4" />
          </button>
        ) : null}
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {origem ? <Badge variant="outline">{origem}</Badge> : null}
        {negocio.status === "ganho" ? (
          <Badge variant="default">
            <Trophy className="mr-1 h-3 w-3" /> Ganho
          </Badge>
        ) : null}
        {negocio.valor_estimado ? (
          <span className="ml-auto text-xs font-medium tabular-nums text-foreground">
            {brl(negocio.valor_estimado)}
          </span>
        ) : null}
      </div>

      {negocio.responsavel?.nome ? (
        <p className="mt-2 flex items-center gap-1 truncate text-xs text-muted-foreground">
          <UserRound className="h-3 w-3 shrink-0" /> {negocio.responsavel.nome}
        </p>
      ) : null}
    </div>
  );
}
