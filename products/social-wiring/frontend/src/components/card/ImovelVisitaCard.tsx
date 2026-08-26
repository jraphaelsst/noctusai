/**
 * ImovelVisitaCard — one property on a roteiro, as a draggable card.
 *
 * NOT a canonical organ (`noc-organ-consume-check`, run before building).
 * `@noctusai/lib` ships `EntityDetailDialog`/`DetailSections` (a label/value
 * field grid) and this product's `MultiSelectPopover` (a fixed-option
 * multi-select). Neither is this: a media card with a photo, a sort handle and
 * a reorder affordance, whose whole job is to be picked up and moved. Building
 * it out of a field grid would mean fighting the grid.
 *
 * Flagged as the extraction target: if a second product needs a sortable
 * media-card list, THIS shape is what goes to the seed rather than a third
 * bespoke one.
 *
 * Presentational only (S3, same contract as the rest of `card/**`): props in,
 * callbacks out, zero data fetching and zero `@/pages/**` imports.
 */
import { GripVertical, ImageOff, X } from "lucide-react";
import { CSS } from "@dnd-kit/utilities";
import { useSortable } from "@dnd-kit/sortable";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ImovelVisita } from "@/types/cardHub";

export interface ImovelVisitaCardProps {
  /** The dnd-kit sortable id — the visita id on a saved roteiro, the código
   *  while the roteiro is still being composed in the dialog. */
  id: string;
  imovel: ImovelVisita;
  /** 1-based, for display. The visiting order IS this number. */
  posicao: number;
  onRemove?: () => void;
  /** Off while the list is read-only (a saved roteiro's summary). */
  sortable?: boolean;
}

export function enderecoDoImovel(imovel: ImovelVisita): string | null {
  const rua = [imovel.logradouro, imovel.numero].filter(Boolean).join(" ").trim();
  const comComplemento = imovel.complemento ? `${rua} — ${imovel.complemento}`.trim() : rua;
  const cidadeUf = [imovel.cidade, imovel.uf].filter(Boolean).join("/");
  const partes = [comComplemento, imovel.bairro, cidadeUf].filter(Boolean);
  return partes.length ? partes.join(" · ") : null;
}

export function captacaoDoImovel(imovel: ImovelVisita): string | null {
  // `imovel_dados.captador_user_id` (migration 075) is the canonical answer —
  // a USER, because the commission slice is attributed to it. The Vista
  // corretor list is the fallback, and ALL of them: 13% of the catalog carries
  // two or three, and showing only the first discards the rest.
  if (imovel.captacao?.nome) return imovel.captacao.nome;
  const nomes = imovel.corretores.map((c) => c.nome).filter(Boolean);
  return nomes.length ? nomes.join(" · ") : null;
}

export function ImovelVisitaCard({
  id,
  imovel,
  posicao,
  onRemove,
  sortable = true,
}: ImovelVisitaCardProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id,
    disabled: !sortable,
  });

  const endereco = enderecoDoImovel(imovel);
  const captacao = captacaoDoImovel(imovel);

  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={cn(
        "flex gap-3 rounded-lg border bg-background p-3",
        isDragging && "z-10 opacity-80 shadow-lg",
      )}
      data-testid={`imovel-visita-${imovel.codigo}`}
    >
      {sortable && (
        <button
          type="button"
          // Keyboard-reachable on purpose: dnd-kit's keyboard sensor drives
          // the sort from this handle, so hiding it behind a mouse-only
          // affordance would make the whole feature unusable without a mouse.
          className="flex cursor-grab touch-none items-center text-muted-foreground hover:text-foreground"
          aria-label={`Reordenar ${imovel.codigo}`}
          data-testid={`imovel-visita-handle-${imovel.codigo}`}
          {...attributes}
          {...listeners}
        >
          <GripVertical className="h-5 w-5" />
        </button>
      )}

      <div className="flex h-16 w-20 shrink-0 items-center justify-center overflow-hidden rounded bg-muted">
        {imovel.foto_destaque ? (
          <img
            src={imovel.foto_destaque}
            alt=""
            className="h-full w-full object-cover"
            loading="lazy"
          />
        ) : (
          <ImageOff className="h-5 w-5 text-muted-foreground" aria-hidden />
        )}
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="rounded bg-muted px-1.5 py-0.5 text-xs font-semibold tabular-nums">
            {posicao}
          </span>
          <span className="truncate text-sm font-semibold">{imovel.codigo}</span>
          {!imovel.ativo_no_vista && (
            // A corretor about to drive there needs to know the listing is
            // gone. `fonte: "registry"` rows also legitimately carry no
            // street, so this explains the blanks below rather than leaving
            // them looking like a loading state.
            <span
              className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-900 dark:bg-amber-950 dark:text-amber-200"
              data-testid="imovel-fora-do-catalogo"
            >
              fora do catálogo
            </span>
          )}
        </div>

        <p className="mt-1 truncate text-sm">{imovel.empreendimento ?? "—"}</p>
        <p className="truncate text-xs text-muted-foreground">{endereco ?? "—"}</p>
        <p className="mt-1 truncate text-xs text-muted-foreground">
          Captação: {captacao ?? "—"}
        </p>
        {/*
          NOC-REMEDIATE[imovel-owner-data]: Vista exposes no proprietário field
          (neither CANDIDATE_IMOVEL_LIST_FIELDS nor
          CANDIDATE_IMOVEL_DETAIL_FIELDS in the seed's vista/calibration.py
          carries one), so there is nothing to read yet. User-ratified
          2026-08-25 to ship the slot empty rather than invent a source.
          DESTINATION: `social_wiring.imovel_dados` (migration 075) — the table
          that already holds what WE author about a property. Add
          `proprietario_nome` / `proprietario_celular` there, surface them via
          `roteiros_service._imovel_out`, then render them here and delete this
          marker. The LABELS stay visible meanwhile: a corretor must see that
          the field exists and is unknown, not wonder whether it was dropped.
        */}
        <p className="truncate text-xs text-muted-foreground" data-testid="imovel-proprietario">
          Proprietário: — · Celular: —
        </p>
      </div>

      {onRemove && (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-7 w-7 shrink-0"
          onClick={onRemove}
          aria-label={`Remover ${imovel.codigo} do roteiro`}
          data-testid={`imovel-visita-remover-${imovel.codigo}`}
        >
          <X className="h-4 w-4" />
        </Button>
      )}
    </div>
  );
}
