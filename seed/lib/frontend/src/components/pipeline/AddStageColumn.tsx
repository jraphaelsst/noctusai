/**
 * `<AddStageColumn/>` — the trailing "+ coluna" slot of an editable board.
 *
 * Rendered through `KanbanBoard.renderTrailingColumn`, so it sits after the
 * last column inside the same horizontal scroll container and is never a drag
 * target. A button until pressed, then a one-field form: Enter creates,
 * Escape (or an empty blur) cancels. The new stage is appended at the end —
 * the API's own default — so it lands exactly where the user clicked.
 */
import * as React from 'react';

import { Button } from '../../design-system/ui/Button';
import { Input } from '../../design-system/ui/Input';

export interface AddStageColumnProps {
  onCreate: (label: string) => void;
  busy?: boolean;
  label?: string;
  className?: string;
}

export function AddStageColumn({
  onCreate,
  busy = false,
  label = '+ coluna',
  className = 'flex-shrink-0 w-64 sm:w-72',
}: AddStageColumnProps) {
  const [adding, setAdding] = React.useState(false);
  const [draft, setDraft] = React.useState('');

  function submit() {
    const value = draft.trim();
    if (!value) {
      setAdding(false);
      return;
    }
    onCreate(value);
    setDraft('');
    setAdding(false);
  }

  return (
    <div className={className} data-testid="pipeline-add-stage">
      {adding ? (
        <form
          className="rounded-lg border bg-card p-3 space-y-2"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <Input
            autoFocus
            maxLength={60}
            placeholder="Nome da nova etapa"
            aria-label="Nome da nova etapa"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Escape') {
                setDraft('');
                setAdding(false);
              }
            }}
          />
          <div className="flex gap-2">
            <Button type="submit" size="sm" disabled={busy || !draft.trim()}>
              Adicionar
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => {
                setDraft('');
                setAdding(false);
              }}
            >
              Cancelar
            </Button>
          </div>
        </form>
      ) : (
        <Button
          variant="outline"
          className="w-full border-dashed"
          disabled={busy}
          onClick={() => setAdding(true)}
        >
          {label}
        </Button>
      )}
    </div>
  );
}
