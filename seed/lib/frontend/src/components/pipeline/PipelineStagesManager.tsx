/**
 * `<PipelineStagesManager/>` — add / rename / recolour / reorder / delete stages.
 *
 * Deliberately a plain list with explicit up/down buttons rather than a
 * drag-to-reorder list. Reordering here is a rare, deliberate act on a short
 * list, and buttons are keyboard-operable, screen-reader-legible and
 * touch-reliable for free — whereas a second dnd-kit context nested inside the
 * board's would be a genuine source of pointer-capture bugs for no gain.
 *
 * DELETION asks where the cards should go. The API refuses to delete a
 * non-empty stage without a target, and this dialog is how the user supplies
 * one — the alternative (cascade) silently destroys deals.
 */
import * as React from 'react';

import { Badge } from '../../design-system/ui/Badge';
import { Button } from '../../design-system/ui/Button';
import { Input } from '../../design-system/ui/Input';
import {
  STAGE_COLOR_OPTIONS,
  STAGE_ROLE_LABELS,
  stageColorClasses,
} from './stageTokens';
import type { PipelineHooks } from './createPipelineHooks';
import type { PipelineStage, StageColor } from './types';

export interface PipelineStagesManagerProps<TCard> {
  hooks: PipelineHooks<TCard>;
  /** Cards per stage id, to warn before a destructive delete. */
  cardCounts?: Record<string, number>;
  onClose?: () => void;
  title?: string;
}

export function PipelineStagesManager<TCard>({
  hooks,
  cardCounts = {},
  onClose,
  title = 'Configurar etapas',
}: PipelineStagesManagerProps<TCard>) {
  const { data: stages, isPending, isFetching, error } = hooks.useStages();
  const createStage = hooks.useCreateStage();
  const updateStage = hooks.useUpdateStage();
  const deleteStage = hooks.useDeleteStage();
  const reorderStages = hooks.useReorderStages();

  const [novoLabel, setNovoLabel] = React.useState('');
  const [editandoId, setEditandoId] = React.useState<string | null>(null);
  const [editLabel, setEditLabel] = React.useState('');
  const [excluindo, setExcluindo] = React.useState<PipelineStage | null>(null);
  const [destino, setDestino] = React.useState<string>('');

  const ordered = React.useMemo(
    () => [...(stages ?? [])].sort((a, b) => a.posicao - b.posicao),
    [stages],
  );

  // `isPending || isFetching` gated to the EMPTY case, never bare `isLoading`:
  // during a background refetch `isLoading` is false, so an unguarded empty
  // branch renders "no stages" over stages that exist.
  if (isPending || (isFetching && ordered.length === 0)) {
    return (
      <div className="p-4 text-sm text-muted-foreground" role="status">
        Carregando etapas...
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 text-sm text-destructive" role="alert">
        {(error as Error).message || 'Não foi possível carregar as etapas.'}
      </div>
    );
  }

  function mover(index: number, delta: number) {
    const alvo = index + delta;
    if (alvo < 0 || alvo >= ordered.length) return;
    const ids = ordered.map((s) => s.id);
    [ids[index], ids[alvo]] = [ids[alvo], ids[index]];
    reorderStages.mutate(ids);
  }

  function salvarLabel(stage: PipelineStage) {
    const label = editLabel.trim();
    setEditandoId(null);
    if (!label || label === stage.label) return;
    updateStage.mutate({ id: stage.id, input: { label } });
  }

  const busy =
    createStage.isPending ||
    updateStage.isPending ||
    deleteStage.isPending ||
    reorderStages.isPending;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-semibold">{title}</h3>
        {onClose && (
          <Button variant="ghost" size="sm" onClick={onClose}>
            Fechar
          </Button>
        )}
      </div>

      <p className="text-sm text-muted-foreground">
        Renomear uma etapa atualiza todos os registros que já passaram por ela —
        as cartas apontam para a etapa, não para o nome.
      </p>

      <ul className="space-y-2">
        {ordered.map((stage, index) => {
          const classes = stageColorClasses(stage.cor);
          const count = cardCounts[stage.id] ?? 0;
          return (
            <li
              key={stage.id}
              className={`flex flex-wrap items-center gap-2 rounded-md border p-2 ${classes.bgColor} ${classes.borderColor}`}
              data-stage-id={stage.id}
            >
              <div className="flex flex-col gap-0.5">
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={`Mover ${stage.label} para cima`}
                  disabled={index === 0 || busy}
                  onClick={() => mover(index, -1)}
                >
                  ↑
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={`Mover ${stage.label} para baixo`}
                  disabled={index === ordered.length - 1 || busy}
                  onClick={() => mover(index, 1)}
                >
                  ↓
                </Button>
              </div>

              <div className="flex-1 min-w-[160px]">
                {editandoId === stage.id ? (
                  <Input
                    autoFocus
                    value={editLabel}
                    aria-label={`Novo nome para ${stage.label}`}
                    onChange={(e) => setEditLabel(e.target.value)}
                    onBlur={() => salvarLabel(stage)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') salvarLabel(stage);
                      if (e.key === 'Escape') setEditandoId(null);
                    }}
                  />
                ) : (
                  <button
                    type="button"
                    className={`text-left font-medium ${classes.color}`}
                    onClick={() => {
                      setEditandoId(stage.id);
                      setEditLabel(stage.label);
                    }}
                  >
                    {stage.label}
                  </button>
                )}
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-xs text-muted-foreground">{count} carta{count === 1 ? '' : 's'}</span>
                  {stage.papel && (
                    <Badge variant="muted" title="Outras funcionalidades dependem deste papel">
                      {STAGE_ROLE_LABELS[stage.papel] ?? stage.papel}
                    </Badge>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-1">
                {STAGE_COLOR_OPTIONS.map((cor) => (
                  <button
                    key={cor}
                    type="button"
                    aria-label={`Cor ${cor} para ${stage.label}`}
                    aria-pressed={stage.cor === cor}
                    disabled={busy}
                    className={`h-4 w-4 rounded-full border ${stageColorClasses(cor).swatch} ${
                      stage.cor === cor ? 'ring-2 ring-offset-1 ring-foreground' : ''
                    }`}
                    onClick={() =>
                      updateStage.mutate({ id: stage.id, input: { cor: cor as StageColor } })
                    }
                  />
                ))}
              </div>

              <Button
                variant="ghost"
                size="sm"
                disabled={busy || !!stage.papel}
                title={
                  stage.papel
                    ? 'Esta etapa tem um papel do qual outras funcionalidades dependem'
                    : 'Excluir etapa'
                }
                onClick={() => {
                  setExcluindo(stage);
                  setDestino(ordered.find((s) => s.id !== stage.id)?.id ?? '');
                }}
              >
                Excluir
              </Button>
            </li>
          );
        })}
      </ul>

      <form
        className="flex items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          const label = novoLabel.trim();
          if (!label) return;
          createStage.mutate({ label }, { onSuccess: () => setNovoLabel('') });
        }}
      >
        <Input
          placeholder="Nome da nova etapa"
          aria-label="Nome da nova etapa"
          value={novoLabel}
          onChange={(e) => setNovoLabel(e.target.value)}
        />
        <Button type="submit" disabled={busy || !novoLabel.trim()}>
          Adicionar
        </Button>
      </form>

      {excluindo && (
        <div className="rounded-md border border-destructive p-3 space-y-2" role="alertdialog">
          <p className="text-sm">
            Excluir <strong>{excluindo.label}</strong>?
            {(cardCounts[excluindo.id] ?? 0) > 0 && (
              <>
                {' '}Esta etapa tem {cardCounts[excluindo.id]} carta
                {cardCounts[excluindo.id] === 1 ? '' : 's'}. Escolha para onde movê-las:
              </>
            )}
          </p>
          {(cardCounts[excluindo.id] ?? 0) > 0 && (
            <select
              className="w-full rounded-md border bg-background p-2 text-sm"
              aria-label="Mover cartas para"
              value={destino}
              onChange={(e) => setDestino(e.target.value)}
            >
              {ordered
                .filter((s) => s.id !== excluindo.id)
                .map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.label}
                  </option>
                ))}
            </select>
          )}
          <div className="flex gap-2">
            <Button
              variant="primary"
              size="sm"
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={busy}
              onClick={() =>
                deleteStage.mutate(
                  { id: excluindo.id, reassignTo: destino || undefined },
                  { onSuccess: () => setExcluindo(null) },
                )
              }
            >
              Confirmar exclusão
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setExcluindo(null)}>
              Cancelar
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
