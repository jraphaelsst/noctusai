/**
 * `<FunnelBoard/>` — the funnel organ's board: `PipelineBoard` (the ONE seed board) + `FunnelCardFace`
 * + `FunnelCardDialog` + `LostReasonDialog`, configured by a `defineFunnel` schema.
 *
 * It COMPOSES `PipelineBoard` — it does not draw columns or handle drags itself. Everything a
 * product used to hand-write per board (card face, "Mover para…", lost flow, gate refusal, detail
 * dialog) is declared in the schema instead.
 *
 * VIEWS: "Abertos" (`status=aberto`) and "Perdidos" (`status=perdido`, cards offer Reabrir). Lost /
 * discarded / archived / won are STATUSES, not columns.
 *
 * REFUSALS: a move refused by the server (409 `gate_refused` …) has already been rolled back by the
 * move mutation (the card is back in its column); this board then says WHAT is missing, in place.
 */
import * as React from 'react';
import { toast } from 'sonner';

import { Button } from '../../../design-system/ui/Button';
import type { PipelineBoardProps } from '../PipelineBoard';
import { PipelineBoard } from '../PipelineBoard';
import type { MoveVariables } from '../createPipelineHooks';
import type { PipelineStage } from '../types';
import type { DefinedFunnel } from './defineFunnel';
import type { FunnelHooks } from './createFunnelHooks';
import { FunnelCardDialog } from './FunnelCardDialog';
import { FunnelCardFace } from './FunnelCardFace';
import { parseFunnelError } from './funnelError';
import { LostReasonDialog } from './LostReasonDialog';
import { formatFunnelValue } from './format';
import { useFunnelActionFlow } from './useFunnelActionFlow';
import type { FunnelCard, FunnelRefusal, FunnelRenderers } from './types';

type PassThrough<TCard extends FunnelCard> = Omit<
  PipelineBoardProps<TCard>,
  'hooks' | 'renderCard' | 'onCardClick' | 'filtros' | 'onMoveError'
>;

export interface FunnelBoardProps<TCard extends FunnelCard> extends PassThrough<TCard> {
  funnel: DefinedFunnel<TCard>;
  hooks: FunnelHooks<TCard>;
  /** Extra server filters (`busca`, `responsavel_id`, `limite_por_etapa`). `status` is owned by the view. */
  filtros?: Record<string, unknown>;
  renderers?: FunnelRenderers<TCard>;
  /** The viewer may move/close/edit cards. Default true. */
  canEdit?: boolean;
  /** Override opening a card (default: the built-in detail dialog). */
  onOpenCard?: (card: TCard) => void;
}

type View = 'aberto' | 'perdido';

const VIEWS: { id: View; label: string }[] = [
  { id: 'aberto', label: 'Abertos' },
  { id: 'perdido', label: 'Perdidos' },
];

export function FunnelBoard<TCard extends FunnelCard>({
  funnel,
  hooks,
  filtros,
  renderers,
  canEdit = true,
  onOpenCard,
  toolbar,
  formatValue,
  ...boardProps
}: FunnelBoardProps<TCard>) {
  const [view, setView] = React.useState<View>('aberto');
  const [openId, setOpenId] = React.useState<string | null>(null);
  const [losingId, setLosingId] = React.useState<string | null>(null);
  const [refusal, setRefusal] = React.useState<(FunnelRefusal & { titulo: string }) | null>(null);

  const boardFiltros = React.useMemo(() => ({ ...filtros, status: view }), [filtros, view]);
  const { data: columns } = hooks.useBoard(boardFiltros);
  const { data: meta } = hooks.useMeta();
  const lose = hooks.useLose();
  const reopen = hooks.useReopen();
  const move = hooks.useMoveCard({
    onError: (error, vars) => reportRefusal(error, vars),
  });
  const actionFlow = useFunnelActionFlow(hooks);

  const stages = React.useMemo(
    () => (columns ?? []).map((c) => c.stage).filter((s): s is PipelineStage => Boolean(s)),
    [columns],
  );
  const cardOf = React.useCallback(
    (id: string) => (columns ?? []).flatMap((c) => c.cards).find((c) => c.id === id) ?? null,
    [columns],
  );

  function reportRefusal(error: Error, vars: MoveVariables) {
    setRefusal({ ...parseFunnelError(error), titulo: cardOf(vars.cardId)?.titulo ?? funnel.schema.entityLabel });
  }

  const losing = losingId ? cardOf(losingId) : null;
  const loseError = lose.error ? parseFunnelError(lose.error).mensagem : null;
  const stageById = (id: string) => stages.find((s) => s.id === id) ?? null;

  return (
    <div data-testid={`funnel-board-${funnel.schema.id}`}>
      {refusal && (
        <div
          role="alert"
          className="mb-4 flex items-start justify-between gap-3 rounded border border-destructive/40 bg-destructive/10 p-3 text-sm"
          data-testid="funnel-board-refusal"
        >
          <div>
            <p className="font-medium text-destructive">
              Não foi possível mover “{refusal.titulo}”: {refusal.mensagem}
            </p>
            {refusal.pendencias.length > 0 && (
              <>
                <p className="mt-1 text-muted-foreground">Falta preencher:</p>
                <ul className="mt-1 list-disc pl-5">
                  {refusal.pendencias.map((p) => (
                    <li key={p.codigo}>{p.label}</li>
                  ))}
                </ul>
              </>
            )}
            <p className="mt-1 text-muted-foreground">O cartão voltou para a etapa anterior.</p>
          </div>
          <Button size="sm" variant="ghost" onClick={() => setRefusal(null)}>
            Dispensar
          </Button>
        </div>
      )}

      {/* No JSX type arguments on <PipelineBoard> — the component-tagger dev plugin breaks on them. */}
      <PipelineBoard
        {...boardProps}
        hooks={hooks.pipeline}
        filtros={boardFiltros}
        formatValue={formatValue ?? ((v) => formatFunnelValue({ valor: v, campos: {} }) ?? '—')}
        onMoveError={(error, vars) => reportRefusal(error, vars)}
        onCardClick={(card) => (onOpenCard ? onOpenCard(card) : setOpenId(card.id))}
        toolbar={
          <>
            <div role="group" aria-label="Visão do funil" className="flex gap-1">
              {VIEWS.map((v) => (
                <Button
                  key={v.id}
                  size="sm"
                  variant={view === v.id ? 'primary' : 'outline'}
                  aria-pressed={view === v.id}
                  onClick={() => setView(v.id)}
                >
                  {v.label}
                </Button>
              ))}
            </div>
            {toolbar}
          </>
        }
        emptyColumnLabel={view === 'perdido' ? 'Nenhum perdido nesta etapa' : boardProps.emptyColumnLabel}
        renderCard={(card) => (
          <FunnelCardFace
            funnel={funnel}
            card={card}
            stage={stageById(card.etapa_id)}
            stages={stages}
            canMove={canEdit}
            onOpen={() => (onOpenCard ? onOpenCard(card) : setOpenId(card.id))}
            onMove={(stageId) => {
              setRefusal(null);
              move.mutate({ cardId: card.id, toStageId: stageId });
            }}
            onLose={() => setLosingId(card.id)}
            onReopen={() => reopen.mutate({ cardId: card.id })}
            onAction={(code) => {
              const def = funnel.action(code);
              if (def) actionFlow.start(card.id, def);
            }}
          />
        )}
      />

      {!onOpenCard && (
        <FunnelCardDialog
          funnel={funnel}
          hooks={hooks}
          cardId={openId}
          stages={stages}
          renderers={renderers}
          canEdit={canEdit}
          onClose={() => setOpenId(null)}
        />
      )}

      <LostReasonDialog
        open={losing !== null}
        reasons={meta?.lost_reasons ?? []}
        cardTitle={losing?.titulo ?? ''}
        busy={lose.isPending}
        error={loseError}
        onCancel={() => {
          lose.reset();
          setLosingId(null);
        }}
        onConfirm={(v) =>
          losingId &&
          lose.mutate(
            { cardId: losingId, ...v },
            {
              onSuccess: () => {
                setLosingId(null);
                toast.success(`${funnel.schema.entityLabel} marcado como perdido`);
              },
            },
          )
        }
      />

      {actionFlow.dialog}
    </div>
  );
}
