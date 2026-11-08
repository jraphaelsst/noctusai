/**
 * `FieldsGridSection` — the `fields` (read) and `form` (edit) section kinds: a labelled grid of the
 * fields a schema declares. A missing value renders "—", never 0 (canon §8).
 *
 * Edit mode only offers fields the SERVER lists in `meta.campos_editaveis` (a field outside it is
 * read-only here — the server would refuse it with 422 `campo_nao_editavel`). Saving sends ONLY the
 * changed keys; the cache write (board + detail) is the hook's job.
 */
import * as React from 'react';

import { Button } from '../../../../design-system/ui/Button';
import { Input } from '../../../../design-system/ui/Input';
import { Textarea } from '../../../../design-system/ui/textarea';
import { formatCurrency } from '../../../../utils';
import { parseFunnelError } from '../funnelError';
import type { FunnelCard, FunnelFieldDef } from '../types';

export interface FieldsGridSectionProps<TCard extends FunnelCard> {
  card: TCard;
  fields: FunnelFieldDef<TCard>[];
  /** Edit mode (`form` kind). */
  editable?: boolean;
  /** `meta.campos_editaveis`. */
  editableKeys?: string[];
  saving?: boolean;
  onSave?: (changes: Record<string, unknown>) => Promise<unknown> | void;
}

const isMissing = (v: unknown) => v === null || v === undefined || v === '' || (typeof v === 'number' && !Number.isFinite(v));

export function displayField<TCard extends FunnelCard>(field: FunnelFieldDef<TCard>, card: TCard): string {
  const raw = field.read ? field.read(card) : card.campos?.[field.key];
  if (isMissing(raw)) return '—';
  if (field.format) return field.format(raw, card);
  if (field.type === 'money' && typeof raw === 'number') return formatCurrency(raw);
  if (field.type === 'date' && typeof raw === 'string') {
    const d = new Date(raw.length === 10 ? `${raw}T00:00:00` : raw);
    return Number.isNaN(d.getTime()) ? raw : d.toLocaleDateString('pt-BR');
  }
  return String(raw);
}

export function FieldsGridSection<TCard extends FunnelCard>({
  card,
  fields,
  editable = false,
  editableKeys = [],
  saving = false,
  onSave,
}: FieldsGridSectionProps<TCard>) {
  const [draft, setDraft] = React.useState<Record<string, string>>({});
  const [error, setError] = React.useState<string | null>(null);
  const dirtyKeys = Object.keys(draft);
  const canEdit = (f: FunnelFieldDef<TCard>) => editable && editableKeys.includes(f.key);

  const current = (f: FunnelFieldDef<TCard>) => {
    const raw = f.read ? f.read(card) : card.campos?.[f.key];
    return isMissing(raw) ? '' : String(raw);
  };

  async function salvar(e: React.FormEvent) {
    e.preventDefault();
    if (!onSave || dirtyKeys.length === 0) return;
    const changes: Record<string, unknown> = {};
    for (const f of fields) {
      if (!(f.key in draft)) continue;
      const v = draft[f.key].trim();
      changes[f.key] = v === '' ? null : f.type === 'number' || f.type === 'money' ? Number(v.replace(',', '.')) : v;
    }
    setError(null);
    try {
      await onSave(changes);
      setDraft({});
    } catch (err) {
      // The server's refusal stays visible next to the form (and the cache rolled back).
      setError(parseFunnelError(err).mensagem);
    }
  }

  return (
    <form onSubmit={salvar} data-testid="funnel-fields">
      <dl className="grid grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-2">
        {fields.map((f) => {
          const id = `funnel-field-${f.key}`;
          const wide = f.type === 'textarea';
          return (
            <div key={f.key} className={wide ? 'sm:col-span-2' : undefined}>
              {canEdit(f) ? (
                <>
                  <label htmlFor={id} className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    {f.label}
                  </label>
                  {f.type === 'textarea' ? (
                    <Textarea
                      id={id}
                      rows={3}
                      value={draft[f.key] ?? current(f)}
                      disabled={saving}
                      onChange={(e) => setDraft((d) => ({ ...d, [f.key]: e.target.value }))}
                    />
                  ) : (
                    <Input
                      id={id}
                      type={f.type === 'date' ? 'date' : 'text'}
                      inputMode={f.type === 'number' || f.type === 'money' ? 'decimal' : undefined}
                      value={draft[f.key] ?? current(f)}
                      disabled={saving}
                      onChange={(e) => setDraft((d) => ({ ...d, [f.key]: e.target.value }))}
                    />
                  )}
                </>
              ) : (
                <>
                  <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{f.label}</dt>
                  <dd className="mt-0.5 whitespace-pre-wrap text-sm">{displayField(f, card)}</dd>
                </>
              )}
            </div>
          );
        })}
      </dl>
      {editable && (
        <div className="mt-4 flex items-center gap-2">
          <Button type="submit" variant="primary" size="sm" disabled={saving || dirtyKeys.length === 0}>
            {saving ? 'Salvando…' : 'Salvar'}
          </Button>
          {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        </div>
      )}
    </form>
  );
}
