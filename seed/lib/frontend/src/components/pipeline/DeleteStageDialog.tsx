/**
 * `<DeleteStageDialog/>` — confirm a stage delete, asking where its cards go.
 *
 * Extracted from `PipelineStagesManager` so the board's column-header menu
 * (`StageHeaderMenu`) and the stage list share ONE delete flow. Two copies of
 * "which guards apply before a delete" is exactly how the list and the header
 * would drift into disagreeing about what may be deleted.
 *
 * The guards mirror the API (`delete_stage` in the seed backend), so the user
 * never meets a 400 they could not have avoided:
 *  - a stage carrying a `papel` cannot be deleted at all — other features
 *    resolve it by role. The dialog says so and offers no confirm.
 *  - a stage holding cards needs a TARGET stage; confirm stays disabled until
 *    one is chosen. The alternative (cascade) silently destroys deals.
 *
 * Presentation-only: the caller runs the mutation in `onConfirm`.
 */
import * as React from 'react';

import { Button } from '../../design-system/ui/Button';
import { STAGE_ROLE_LABELS } from './stageTokens';
import type { PipelineStage, StageRoleLabels } from './types';

export interface DeleteStageDialogProps {
  /** The stage being deleted. */
  stage: PipelineStage;
  /** Every stage of the pipeline, in display order (the target candidates). */
  stages: PipelineStage[];
  /** Cards currently in `stage`. */
  cardCount: number;
  /** Disable the controls while a mutation is in flight. */
  busy?: boolean;
  /** Runs the delete. `reassignTo` is set whenever the stage holds cards. */
  onConfirm: (reassignTo: string | undefined) => void;
  onCancel: () => void;
  roleLabels?: StageRoleLabels;
  className?: string;
}

export function DeleteStageDialog({
  stage,
  stages,
  cardCount,
  busy = false,
  onConfirm,
  onCancel,
  roleLabels = STAGE_ROLE_LABELS,
  className = 'rounded-md border border-destructive p-3 space-y-2',
}: DeleteStageDialogProps) {
  const candidates = React.useMemo(
    () => stages.filter((s) => s.id !== stage.id),
    [stages, stage.id],
  );
  const [destino, setDestino] = React.useState<string>(() => candidates[0]?.id ?? '');

  // Reset the target when the dialog is re-pointed at another stage.
  React.useEffect(() => {
    setDestino(candidates[0]?.id ?? '');
    // Only the stage identity re-seeds the choice; a candidates refresh must
    // not clobber what the user already picked.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stage.id]);

  if (stage.papel) {
    return (
      <div className={className} role="alertdialog" aria-label={`Excluir ${stage.label}`}>
        <p className="text-sm">
          <strong>{stage.label}</strong> não pode ser excluída: ela tem o papel{' '}
          <em>{roleLabels[stage.papel] ?? stage.papel}</em>, do qual outras funcionalidades
          dependem. Atribua o papel a outra etapa primeiro.
        </p>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" onClick={onCancel}>
            Fechar
          </Button>
        </div>
      </div>
    );
  }

  const needsTarget = cardCount > 0;
  const semDestino = needsTarget && !destino;

  return (
    <div className={className} role="alertdialog">
      <p className="text-sm">
        Excluir <strong>{stage.label}</strong>?
        {needsTarget && (
          <>
            {' '}Esta etapa tem {cardCount} carta
            {cardCount === 1 ? '' : 's'}. Escolha para onde movê-las:
          </>
        )}
      </p>
      {needsTarget && (
        <select
          className="w-full rounded-md border bg-background p-2 text-sm"
          aria-label="Mover cartas para"
          value={destino}
          onChange={(e) => setDestino(e.target.value)}
        >
          {candidates.map((s) => (
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
          disabled={busy || semDestino}
          onClick={() => onConfirm(destino || undefined)}
        >
          Confirmar exclusão
        </Button>
        <Button variant="ghost" size="sm" onClick={onCancel}>
          Cancelar
        </Button>
      </div>
    </div>
  );
}
