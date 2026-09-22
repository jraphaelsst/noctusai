/**
 * `<StageHeaderMenu/>` — the stage title of a board column, editable in place.
 *
 * Rendered by `PipelineBoard` in place of the plain column title when the
 * board is opted into `editableHeaders`. It gives the column header the three
 * edits users otherwise have to open "Configurar etapas" for:
 *
 *  - RENAME inline (double-click the title, or the menu's "Renomear"): Enter
 *    saves, Escape cancels, blur saves. Renaming is one PATCH of `label` —
 *    cards reference the stage by id, so every card follows.
 *  - RECOLOUR from the menu's swatches (the same closed token set as the
 *    stage list — `STAGE_COLOR_OPTIONS`).
 *  - DELETE via the shared `DeleteStageDialog`: a stage with a `papel` cannot
 *    be deleted, a stage holding cards needs a target.
 *
 * DRAG-SAFETY: when columns are drag-reorderable the whole header is the
 * column's drag handle. Every interactive control here stops mouse / touch /
 * key propagation, so pressing the menu button or selecting text in the
 * rename input never starts a column drag. The title TEXT itself does not stop
 * propagation — it stays a grab surface.
 *
 * Presentation + local state only; the caller wires the mutations.
 */
import * as React from 'react';

import { Button } from '../../design-system/ui/Button';
import { Dialog } from '../../design-system/ui/Dialog';
import { Input } from '../../design-system/ui/Input';
import { DeleteStageDialog } from './DeleteStageDialog';
import { STAGE_COLOR_OPTIONS, STAGE_ROLE_LABELS, stageColorClasses } from './stageTokens';
import type { PipelineStage, StageColor, StageRoleLabels } from './types';

export interface StageHeaderMenuProps {
  stage: PipelineStage;
  /** Every stage of the pipeline, in display order (delete targets). */
  stages: PipelineStage[];
  /** Cards in this stage (the true total, not just the rendered page). */
  cardCount: number;
  onRename: (label: string) => void;
  onRecolor: (cor: StageColor) => void;
  onDelete: (reassignTo: string | undefined) => void;
  /** Disable the controls while a stage mutation is in flight. */
  busy?: boolean;
  roleLabels?: StageRoleLabels;
  /** Classes for the title text (the column's colour token). */
  titleClassName?: string;
}

/** Stop an interaction from reaching the column's drag handle. */
const isolate = {
  onMouseDown: (e: React.SyntheticEvent) => e.stopPropagation(),
  onTouchStart: (e: React.SyntheticEvent) => e.stopPropagation(),
  onPointerDown: (e: React.SyntheticEvent) => e.stopPropagation(),
  onKeyDown: (e: React.SyntheticEvent) => e.stopPropagation(),
};

export function StageHeaderMenu({
  stage,
  stages,
  cardCount,
  onRename,
  onRecolor,
  onDelete,
  busy = false,
  roleLabels = STAGE_ROLE_LABELS,
  titleClassName = '',
}: StageHeaderMenuProps) {
  const [renaming, setRenaming] = React.useState(false);
  const [draft, setDraft] = React.useState(stage.label);
  const [menuOpen, setMenuOpen] = React.useState(false);
  const [deleting, setDeleting] = React.useState(false);
  const rootRef = React.useRef<HTMLDivElement>(null);
  const menuId = React.useId();

  // Close the menu on an outside press. `mousedown`/`touchstart`, not
  // `click`: a click fires after the press already moved focus elsewhere.
  React.useEffect(() => {
    if (!menuOpen) return;
    const onOutside = (event: Event) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', onOutside);
    document.addEventListener('touchstart', onOutside);
    return () => {
      document.removeEventListener('mousedown', onOutside);
      document.removeEventListener('touchstart', onOutside);
    };
  }, [menuOpen]);

  function startRename() {
    setMenuOpen(false);
    setDraft(stage.label);
    setRenaming(true);
  }

  function commitRename() {
    const label = draft.trim();
    setRenaming(false);
    if (!label || label === stage.label) return;
    onRename(label);
  }

  return (
    <div ref={rootRef} className="relative flex min-w-0 items-center gap-1" data-stage-header={stage.id}>
      {renaming ? (
        <span className="min-w-0 flex-1" {...isolate}>
          <Input
            autoFocus
            value={draft}
            maxLength={60}
            aria-label={`Novo nome para ${stage.label}`}
            className="h-7 text-sm"
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commitRename}
            onKeyDown={(e) => {
              if (e.key === 'Enter') commitRename();
              if (e.key === 'Escape') setRenaming(false);
            }}
          />
        </span>
      ) : (
        <h3
          className={`font-semibold text-sm min-w-0 truncate ${titleClassName}`}
          title="Clique duas vezes para renomear"
          onDoubleClick={busy ? undefined : startRename}
        >
          {stage.label}
        </h3>
      )}

      <span {...isolate}>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 shrink-0"
          aria-label={`Opções da etapa ${stage.label}`}
          aria-haspopup="menu"
          aria-expanded={menuOpen}
          aria-controls={menuOpen ? menuId : undefined}
          disabled={busy}
          onClick={() => setMenuOpen((v) => !v)}
        >
          ⋯
        </Button>
      </span>

      {menuOpen && (
        <div
          id={menuId}
          role="menu"
          aria-label={`Opções da etapa ${stage.label}`}
          className="absolute right-0 top-full z-20 mt-1 w-56 rounded-md border bg-popover text-popover-foreground p-1 shadow-md"
          {...isolate}
          onKeyDown={(e) => {
            e.stopPropagation();
            if (e.key === 'Escape') setMenuOpen(false);
          }}
        >
          <button
            type="button"
            role="menuitem"
            className="w-full rounded-sm px-2 py-1.5 text-left text-sm hover:bg-muted"
            onClick={startRename}
          >
            Renomear
          </button>

          <div role="group" aria-label="Cor da etapa" className="flex flex-wrap gap-1.5 px-2 py-1.5">
            {STAGE_COLOR_OPTIONS.map((cor) => (
              <button
                key={cor}
                type="button"
                role="menuitemradio"
                aria-checked={stage.cor === cor}
                aria-label={`Cor ${cor} para ${stage.label}`}
                className={`h-5 w-5 rounded-full border ${stageColorClasses(cor).swatch} ${
                  stage.cor === cor ? 'ring-2 ring-offset-1 ring-foreground' : ''
                }`}
                onClick={() => {
                  setMenuOpen(false);
                  if (cor !== stage.cor) onRecolor(cor);
                }}
              />
            ))}
          </div>

          <button
            type="button"
            role="menuitem"
            className="w-full rounded-sm px-2 py-1.5 text-left text-sm text-destructive hover:bg-muted disabled:opacity-50"
            aria-disabled={Boolean(stage.papel)}
            title={
              stage.papel
                ? 'Esta etapa tem um papel do qual outras funcionalidades dependem'
                : 'Excluir etapa'
            }
            onClick={() => {
              setMenuOpen(false);
              setDeleting(true);
            }}
          >
            Excluir etapa
          </button>
        </div>
      )}

      {deleting && (
        // React events bubble through the component tree even out of a fixed
        // overlay, so the dialog is isolated from the drag handle too.
        <span {...isolate}>
          <Dialog open onClose={() => setDeleting(false)} title={`Excluir ${stage.label}`}>
            <DeleteStageDialog
              stage={stage}
              stages={stages}
              cardCount={cardCount}
              busy={busy}
              roleLabels={roleLabels}
              className="space-y-3 p-4"
              onCancel={() => setDeleting(false)}
              onConfirm={(reassignTo) => {
                setDeleting(false);
                onDelete(reassignTo);
              }}
            />
          </Dialog>
        </span>
      )}
    </div>
  );
}
