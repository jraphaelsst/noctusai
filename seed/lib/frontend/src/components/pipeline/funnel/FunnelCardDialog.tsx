/**
 * `FunnelCardDialog` — the funnel card detail, built ON `CardHubDialog` (rail + subpage registry +
 * activity pane). The tabs are NOT written here: they come from the schema (`tabsFor(card)`), each
 * section kind rendered by this file or by a product-injected renderer (`renderers`).
 *
 * Header controls (WCAG 2.5.7 — moving never needs a drag): an "Etapa" select, the schema's header
 * actions, and the status verbs (Perder · Reabrir · Arquivar). A refused move (409 gate_refused)
 * snaps the select back (the cache rolled back) and lists what is missing, in place.
 */
import { Archive, LayoutList, RotateCcw, XCircle } from 'lucide-react';
import * as React from 'react';
import { toast } from 'sonner';

import { Button } from '../../../design-system/ui/Button';
import { CardHubDialog, type CardSubpage } from '../../card-hub/CardHubDialog';
import { Timeline } from '../../card-hub/Timeline';
import type { PipelineStage } from '../types';
import type { DefinedFunnel } from './defineFunnel';
import type { FunnelHooks } from './createFunnelHooks';
import { useFunnelActionFlow } from './useFunnelActionFlow';
import { parseFunnelError } from './funnelError';
import { LostReasonDialog } from './LostReasonDialog';
import { FieldsGridSection } from './sections/FieldsGridSection';
import { LinkedEntitiesSection } from './sections/LinkedEntitiesSection';
import type {
  FunnelActionDef,
  FunnelCard,
  FunnelRefusal,
  FunnelRenderers,
  FunnelSectionRenderCtx,
  FunnelTab,
} from './types';

export interface FunnelCardDialogProps<TCard extends FunnelCard> {
  funnel: DefinedFunnel<TCard>;
  hooks: FunnelHooks<TCard>;
  /** The open card, or `null` when closed. */
  cardId: string | null;
  /** Stages for the "Etapa" select (from the board's columns). */
  stages: PipelineStage[];
  onClose: () => void;
  /** Section kinds that need product services (`geral`, `schedule`, `reminders`, `conversation`). */
  renderers?: FunnelRenderers<TCard>;
  /** The viewer may change the card. Default true. */
  canEdit?: boolean;
}

function RefusalAlert({ refusal }: { refusal: FunnelRefusal }) {
  return (
    <div role="alert" className="mb-4 rounded border border-destructive/40 bg-destructive/10 p-3 text-sm" data-testid="funnel-refusal">
      <p className="font-medium text-destructive">{refusal.mensagem}</p>
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
    </div>
  );
}

export function FunnelCardDialog<TCard extends FunnelCard>({
  funnel,
  hooks,
  cardId,
  stages,
  onClose,
  renderers,
  canEdit = true,
}: FunnelCardDialogProps<TCard>) {
  const cardQ = hooks.useCard(cardId);
  const card = cardQ.data ?? null;
  const metaQ = hooks.useMeta();
  const meta = metaQ.data ?? null;
  const hubId = card ? funnel.hubIdOf(card) : null;
  const activity = hooks.useActivity(cardId, hubId);

  const [refusal, setRefusal] = React.useState<FunnelRefusal | null>(null);
  const [losing, setLosing] = React.useState(false);

  const move = hooks.useMoveCard({
    onError: (error) => {
      const r = parseFunnelError(error);
      setRefusal(r);
      // A gate refusal is rendered in place with what is missing; anything else also toasts.
      if (r.code !== 'gate_refused') toast.error('Não foi possível mover', { description: r.mensagem });
    },
  });
  const lose = hooks.useLose();
  const reopen = hooks.useReopen();
  const archive = hooks.useArchive();
  const update = hooks.useUpdateCard();
  const actionFlow = useFunnelActionFlow(hooks);

  // A new card = a clean slate.
  React.useEffect(() => {
    setRefusal(null);
  }, [cardId]);

  const isOpen = card?.status === 'aberto';
  const startAction = (def: FunnelActionDef) => card && actionFlow.start(card.id, def);

  const offered = (def: FunnelActionDef) => {
    if (!meta) return true; // server enforces; the meta only narrows what we OFFER
    const m = meta.acoes.find((a) => a.codigo === def.code);
    if (!m) return false;
    const papel = stages.find((s) => s.id === card?.etapa_id)?.papel;
    return m.papeis.length === 0 || (!!papel && m.papeis.includes(papel));
  };

  function renderTab(tab: FunnelTab<TCard>, ctx: FunnelSectionRenderCtx<TCard>): React.ReactNode {
    const s = tab.section;
    switch (s.kind) {
      case 'fields':
      case 'form':
        return (
          <FieldsGridSection
            card={ctx.card}
            fields={s.fields}
            editable={s.kind === 'form' && canEdit && ctx.card.status === 'aberto'}
            editableKeys={meta?.campos_editaveis ?? []}
            saving={update.isPending}
            onSave={(changes) => update.mutateAsync({ cardId: ctx.card.id, changes })}
          />
        );
      case 'list': {
        const items = s.items(ctx.card);
        if (items.length === 0) return <p className="text-sm text-muted-foreground">{s.empty ?? 'Nada por aqui ainda.'}</p>;
        return (
          <ul className="divide-y text-sm">
            {items.map((i) => (
              <li key={i.id} className="py-2">
                <span className="font-medium">{i.label}</span>
                {i.detail && <span className="ml-2 text-muted-foreground">{i.detail}</span>}
              </li>
            ))}
          </ul>
        );
      }
      case 'linked':
        return (
          <LinkedEntitiesSection
            card={ctx.card}
            api={hooks.api}
            queryKey={hooks.descriptor.queryKey}
            endpoint={s.endpoint(ctx.card)}
            columns={s.columns}
            rowId={s.rowId}
            onOpen={s.onOpen}
            empty={s.empty}
          />
        );
      case 'timeline':
        return (
          <Timeline
            entries={activity.entries}
            loading={activity.loading}
            error={activity.error}
            hasMore={activity.hasMore}
            loadingMore={activity.loadingMore}
            onLoadMore={activity.onLoadMore}
          />
        );
      case 'custom':
        return s.render(ctx);
      case 'geral':
      case 'schedule':
      case 'reminders':
      case 'conversation': {
        const render = renderers?.[s.kind];
        if (render) return render(ctx);
        return (
          <p className="text-sm text-muted-foreground" data-testid={`funnel-missing-renderer-${s.kind}`}>
            Esta aba ({tab.label}) depende de um módulo do produto que ainda não foi conectado.
          </p>
        );
      }
    }
  }

  const subpages: CardSubpage<string>[] = card
    ? funnel.tabsFor(card).map((tab) => ({
        key: tab.id,
        label: tab.label,
        icon: tab.icon ?? LayoutList,
        render: (ctx) => (
          <>
            {card.status !== 'aberto' && (
              <p className="mb-4 rounded bg-muted p-3 text-sm" data-testid="funnel-closed-banner">
                {card.status === 'perdido'
                  ? `Perdido${card.motivo_perda ? ` — ${card.motivo_perda}` : ''}.`
                  : card.status === 'ganho'
                    ? 'Negócio ganho.'
                    : 'Arquivado.'}
              </p>
            )}
            {refusal && <RefusalAlert refusal={refusal} />}
            {renderTab(tab, { card, select: ctx.select, isSheet: ctx.isSheet })}
          </>
        ),
      }))
    : [];
  const headerDefs = funnel.actionsAt('header').filter(offered);
  const busyClosing = lose.isPending || reopen.isPending || archive.isPending;

  const headerActions = card ? (
    <div className="flex flex-wrap items-center justify-end gap-2">
      <label className="flex items-center gap-1 text-xs text-muted-foreground">
        Etapa
        <select
          className="h-8 rounded-md border bg-background px-2 text-sm text-foreground"
          value={card.etapa_id}
          disabled={!isOpen || !canEdit || move.isPending}
          onChange={(e) => {
            setRefusal(null);
            move.mutate({ cardId: card.id, toStageId: e.target.value });
          }}
        >
          {stages.map((s) => (
            <option key={s.id} value={s.id}>
              {s.label}
            </option>
          ))}
        </select>
      </label>
      {isOpen &&
        canEdit &&
        headerDefs.map((def) => (
          <Button key={def.code} size="sm" variant="outline" onClick={() => startAction(def)} disabled={actionFlow.isPending}>
            {def.icon && <def.icon className="mr-1 h-4 w-4" aria-hidden="true" />}
            {def.label}
          </Button>
        ))}
      {isOpen && canEdit && (
        <Button size="sm" variant="ghost" onClick={() => setLosing(true)} disabled={busyClosing}>
          <XCircle className="mr-1 h-4 w-4" aria-hidden="true" />
          Perder
        </Button>
      )}
      {!isOpen && canEdit && card.status !== 'ganho' && (
        <Button size="sm" variant="outline" onClick={() => reopen.mutate({ cardId: card.id })} disabled={busyClosing}>
          <RotateCcw className="mr-1 h-4 w-4" aria-hidden="true" />
          Reabrir
        </Button>
      )}
      {card.status !== 'arquivado' && canEdit && (
        <Button
          size="icon"
          variant="ghost"
          aria-label={`Arquivar ${card.titulo}`}
          title="Arquivar"
          onClick={() => archive.mutate({ cardId: card.id })}
          disabled={busyClosing}
        >
          <Archive className="h-4 w-4" aria-hidden="true" />
        </Button>
      )}
    </div>
  ) : null;

  const loseError = lose.error ? parseFunnelError(lose.error).mensagem : null;

  return (
    <>
      <CardHubDialog
        key={cardId ?? 'closed'}
        open={cardId !== null}
        onClose={onClose}
        isLoading={cardQ.isPending && !card}
        error={cardQ.error ? parseFunnelError(cardQ.error).mensagem : null}
        notFound={!!cardId && !cardQ.isPending && !cardQ.error && !card}
        nome={card?.titulo ?? ''}
        headerActions={headerActions}
        subpages={subpages}
        defaultSubpage={funnel.schema.defaultTab}
        activity={{
          title: activity.composer ? undefined : 'Histórico',
          timeline: {
            entries: activity.entries,
            loading: activity.loading,
            error: activity.error,
            hasMore: activity.hasMore,
            loadingMore: activity.loadingMore,
            onLoadMore: activity.onLoadMore,
          },
          composer: activity.composer ?? undefined,
        }}
        testId={`funnel-dialog-${funnel.schema.id}`}
      />

      {card && (
        <LostReasonDialog
          open={losing}
          reasons={meta?.lost_reasons ?? []}
          cardTitle={card.titulo}
          busy={lose.isPending}
          error={loseError}
          onCancel={() => {
            lose.reset();
            setLosing(false);
          }}
          onConfirm={(v) =>
            lose.mutate(
              { cardId: card.id, ...v },
              {
                onSuccess: () => {
                  setLosing(false);
                  toast.success(`${funnel.schema.entityLabel} marcado como perdido`);
                },
              },
            )
          }
        />
      )}

      {actionFlow.dialog}
    </>
  );
}
