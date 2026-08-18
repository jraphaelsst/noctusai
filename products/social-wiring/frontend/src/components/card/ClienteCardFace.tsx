/**
 * ClienteCardFace — the board card face (screenshot 11, the densest single
 * spec in the reference set): colour strip · title · badge row (due pill
 * with state colouring, description glyph, `📎 n`, `☑ done/total`,
 * temperature). PROJECT.md §4.
 *
 * Presentational only (S3, §0): props in, a single `onClick` out, zero data
 * fetching, zero imports outside `components/card/**` and its own types.
 *
 * "Badges render only when non-zero" — Trello shows nothing rather than a
 * zero, and so do we (§4). Every badge below is independently omitted when
 * its underlying count/flag is falsy.
 */
import { AlignLeft, CheckSquare, Clock, Paperclip, Thermometer } from "lucide-react";

import { cn } from "@/lib/utils";
import type { CardBadges, CardDatas } from "@/types/cardHub";

export interface ClienteCardFaceProps {
  nome: string;
  /** First tag's colour (hex) — `undefined` renders no strip, matching a card with no Etiquetas. */
  corFaixa?: string | null;
  datas?: Pick<CardDatas, "data_entrega" | "entrega_concluida"> | null;
  badges?: CardBadges | null;
  onClick?: () => void;
  className?: string;
  testId?: string;
}

type DueState = "done" | "overdue" | "soon" | "upcoming";

const DUE_SOON_WINDOW_MS = 24 * 60 * 60 * 1000;

/**
 * Trello's own due-pill rule (no formula is pinned in the contract for
 * this): done ⇒ green, past due ⇒ red, within 24h ⇒ yellow, otherwise
 * neutral. Colocated here — it is purely a rendering concern of this one
 * face, not a shared domain calculation.
 */
export function resolveDueState(dataEntrega: string, entregaConcluida: boolean, now = new Date()): DueState {
  if (entregaConcluida) return "done";
  const due = new Date(dataEntrega).getTime();
  const diff = due - now.getTime();
  if (diff < 0) return "overdue";
  if (diff <= DUE_SOON_WINDOW_MS) return "soon";
  return "upcoming";
}

const DUE_STATE_CLASSES: Record<DueState, string> = {
  done: "bg-emerald-500/20 text-emerald-400",
  overdue: "bg-red-500/20 text-red-400",
  soon: "bg-amber-500/20 text-amber-400",
  upcoming: "bg-secondary text-secondary-foreground",
};

function formatDuePill(dataEntrega: string): string {
  const date = new Date(dataEntrega);
  if (Number.isNaN(date.getTime())) return "—";
  const day = date.getDate();
  const month = date.toLocaleDateString("pt-BR", { month: "short" }).replace(".", "");
  return `${day} de ${month}.`;
}

export function ClienteCardFace({
  nome,
  corFaixa,
  datas,
  badges,
  onClick,
  className,
  testId = "cliente-card-face",
}: ClienteCardFaceProps) {
  const dueState =
    datas?.data_entrega != null
      ? resolveDueState(datas.data_entrega, datas.entrega_concluida ?? false)
      : null;

  const hasBadgeRow =
    !!dueState ||
    !!badges?.tem_descricao ||
    !!(badges?.documentos && badges.documentos > 0) ||
    !!(badges?.checklist_total && badges.checklist_total > 0) ||
    !!badges?.temperatura;

  return (
    <div
      data-testid={testId}
      className={cn(
        "cursor-pointer overflow-hidden rounded-md border bg-card text-left transition-colors hover:border-primary/50",
        className,
      )}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onClick={onClick}
      onKeyDown={(e) => {
        if (onClick && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault();
          onClick();
        }
      }}
    >
      {corFaixa && (
        <div
          className="h-2 w-full"
          style={{ backgroundColor: corFaixa }}
          data-testid="cliente-card-face-strip"
        />
      )}

      <div className="space-y-2 p-3">
        <p className="line-clamp-2 text-sm font-medium leading-snug">{nome}</p>

        {hasBadgeRow && (
          <div className="flex flex-wrap items-center gap-2 text-xs" data-testid="cliente-card-face-badges">
            {dueState && datas?.data_entrega && (
              <span
                className={cn(
                  "inline-flex items-center gap-1 rounded px-1.5 py-0.5 font-medium",
                  DUE_STATE_CLASSES[dueState],
                )}
                data-testid="cliente-card-face-due"
              >
                <Clock className="h-3 w-3" />
                {formatDuePill(datas.data_entrega)}
              </span>
            )}

            {badges?.tem_descricao && (
              <AlignLeft
                className="h-3.5 w-3.5 text-muted-foreground"
                data-testid="cliente-card-face-descricao"
              />
            )}

            {!!badges?.documentos && badges.documentos > 0 && (
              <span
                className="inline-flex items-center gap-1 text-muted-foreground"
                data-testid="cliente-card-face-anexos"
              >
                <Paperclip className="h-3.5 w-3.5" />
                {badges.documentos}
              </span>
            )}

            {!!badges?.checklist_total && badges.checklist_total > 0 && (
              <span
                className="inline-flex items-center gap-1 text-muted-foreground"
                data-testid="cliente-card-face-checklist"
              >
                <CheckSquare className="h-3.5 w-3.5" />
                {badges.checklist_concluidos}/{badges.checklist_total}
              </span>
            )}

            {badges?.temperatura && (
              <span
                className="inline-flex items-center gap-1 text-muted-foreground"
                data-testid="cliente-card-face-temperatura"
                title="Temperatura provisória — a fórmula ainda não foi ratificada (D8)"
              >
                <Thermometer className="h-3.5 w-3.5" />
                {badges.temperatura.rotulo}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
