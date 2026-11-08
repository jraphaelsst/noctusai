/**
 * `FunnelCardFace` — the board card, drawn from a schema's face slots. EXTENDS `CardHubFace`
 * through its declared seam (`leading` / `subtitle` / `chips` / `footer` / `onOpen`) — it does not
 * copy the markup.
 *
 * Accessibility fixed HERE, once, for every product (WCAG 2.1.1, 2.5.7, 4.1.2):
 *  - the title is a real `<button>`: a card opens from the keyboard;
 *  - "Mover para…" is a menu on the card — moving never requires a drag;
 *  - every icon-only button carries an accessible name.
 */
import { ArrowRightLeft, Flame, UserRound } from 'lucide-react';
import * as React from 'react';

import { Button } from '../../../design-system/ui/Button';
import { Popover, PopoverContent, PopoverTrigger } from '../../../design-system/ui/popover';
import { CardHubFace } from '../../card-hub/CardHubFace';
import type { PipelineStage } from '../types';
import type { DefinedFunnel } from './defineFunnel';
import { formatFunnelValue, initialsOf } from './format';
import type { FunnelCard } from './types';

export interface FunnelCardFaceProps<TCard extends FunnelCard> {
  funnel: DefinedFunnel<TCard>;
  card: TCard;
  /** The stage the card sits in (for role actions). */
  stage: PipelineStage | null;
  /** Every stage a card may go to (the "Mover para…" menu). */
  stages: PipelineStage[];
  onOpen: () => void;
  onMove: (stageId: string) => void;
  onLose: () => void;
  onReopen: () => void;
  onAction: (code: string) => void;
  /** The viewer may move/close cards. Default true. */
  canMove?: boolean;
}

const STATUS_LABEL: Record<string, string> = {
  ganho: 'Ganho',
  perdido: 'Perdido',
  arquivado: 'Arquivado',
};

export function FunnelCardFace<TCard extends FunnelCard>({
  funnel,
  card,
  stage,
  stages,
  onOpen,
  onMove,
  onLose,
  onReopen,
  onAction,
  canMove = true,
}: FunnelCardFaceProps<TCard>) {
  const slots = funnel.schema.face ?? {};
  const testId = `funnel-card-${card.id}`;
  const title = slots.title?.(card) ?? card.titulo;
  const subtitle = slots.subtitle ? slots.subtitle(card) : card.subtitulo;
  const avatar = slots.avatar?.(card) ?? null;
  const chips = slots.chips ? slots.chips(card) : card.badges;
  const value = slots.value ? slots.value(card) : formatFunnelValue(card);
  const owner = slots.owner ? slots.owner(card) : card.responsavel;
  const due = slots.due?.(card) ?? null;
  const score = slots.score?.(card) ?? null;
  const roleAction = slots.roleAction?.(card, { stage }) ?? null;
  const iconAction = slots.iconAction?.(card, { stage }) ?? null;
  const aberto = card.status === 'aberto';
  const [menuOpen, setMenuOpen] = React.useState(false);

  const closedChip = !aberto ? STATUS_LABEL[card.status] : null;
  const hasChips = chips.length > 0 || closedChip || score;

  return (
    <CardHubFace
      testId={testId}
      nome={title}
      onOpen={onOpen}
      datas={due ? { data_entrega: due.data_entrega, entrega_concluida: due.concluida ?? false } : null}
      leading={
        avatar ? (
          <span
            aria-hidden="true"
            className="flex h-8 w-8 shrink-0 items-center justify-center overflow-hidden rounded-full bg-secondary text-xs font-semibold text-secondary-foreground"
          >
            {avatar.src ? <img src={avatar.src} alt="" className="h-full w-full object-cover" /> : initialsOf(avatar.label)}
          </span>
        ) : undefined
      }
      subtitle={subtitle || undefined}
      chips={
        hasChips ? (
          <ul className="flex flex-wrap items-center gap-1.5 text-xs" aria-label="Marcadores">
            {closedChip && (
              <li className="rounded bg-muted px-1.5 py-0.5 font-medium text-foreground">{closedChip}</li>
            )}
            {chips.map((b, i) => (
              <li
                key={`${b.label}-${i}`}
                data-variant={b.variant}
                className="rounded border px-1.5 py-0.5 text-muted-foreground"
              >
                {b.label}
              </li>
            ))}
            {score && (
              <li className="inline-flex items-center gap-1 text-muted-foreground">
                <Flame className="h-3.5 w-3.5" aria-hidden="true" />
                {score.label}
              </li>
            )}
          </ul>
        ) : undefined
      }
      footer={
        // A click on any control here is NOT a card click (KanbanCard activates on every click that
        // bubbles — including React-portal bubbling from the "Mover para…" menu).
        // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-static-element-interactions
        <div className="space-y-2" onClick={(e) => e.stopPropagation()}>
          {(value || owner) && (
            <div className="flex items-center justify-between gap-2 text-xs">
              <span className="font-medium" data-testid={`${testId}-valor`}>{value ?? ''}</span>
              {owner && (
                <span className="inline-flex min-w-0 items-center gap-1 text-muted-foreground" data-testid={`${testId}-owner`}>
                  <UserRound className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                  <span className="truncate">{owner.nome}</span>
                </span>
              )}
            </div>
          )}

          <div className="flex items-center gap-1.5">
            {aberto && roleAction && canMove && (
              <Button size="sm" variant="primary" onClick={() => onAction(roleAction.code)}>
                {roleAction.label}
              </Button>
            )}
            {aberto && iconAction && (
              <Button
                size="icon"
                variant="ghost"
                aria-label={iconAction.label}
                title={iconAction.label}
                onClick={() => onAction(iconAction.code)}
              >
                <iconAction.icon className="h-4 w-4" aria-hidden="true" />
              </Button>
            )}
            {!aberto && canMove && card.status !== 'ganho' && (
              <Button size="sm" variant="outline" onClick={onReopen}>
                Reabrir
              </Button>
            )}

            {aberto && canMove && (
              <Popover open={menuOpen} onOpenChange={setMenuOpen}>
                <PopoverTrigger asChild>
                  <Button
                    size="icon"
                    variant="ghost"
                    className="ml-auto"
                    aria-label={`Mover ${title} para…`}
                    title="Mover para…"
                    data-testid={`${testId}-mover`}
                  >
                    <ArrowRightLeft className="h-4 w-4" aria-hidden="true" />
                  </Button>
                </PopoverTrigger>
                <PopoverContent align="end" className="w-56 p-1">
                  <p className="px-2 py-1 text-xs font-semibold text-muted-foreground">Mover para…</p>
                  <ul>
                    {stages.map((s) => (
                      <li key={s.id}>
                        <button
                          type="button"
                          disabled={s.id === card.etapa_id}
                          aria-current={s.id === card.etapa_id ? 'true' : undefined}
                          className="w-full rounded px-2 py-1.5 text-left text-sm hover:bg-accent focus-visible:bg-accent disabled:opacity-60"
                          onClick={() => {
                            setMenuOpen(false);
                            onMove(s.id);
                          }}
                        >
                          {s.label}
                          {s.id === card.etapa_id ? ' (atual)' : ''}
                        </button>
                      </li>
                    ))}
                  </ul>
                  <div className="mt-1 border-t pt-1">
                    <button
                      type="button"
                      className="w-full rounded px-2 py-1.5 text-left text-sm text-destructive hover:bg-accent focus-visible:bg-accent"
                      onClick={() => {
                        setMenuOpen(false);
                        onLose();
                      }}
                    >
                      Marcar como perdido…
                    </button>
                  </div>
                </PopoverContent>
              </Popover>
            )}
          </div>
        </div>
      }
    />
  );
}
