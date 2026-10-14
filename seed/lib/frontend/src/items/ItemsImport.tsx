/** `<ItemsImport/>` — CSV import: pick a file, optionally validate-only / update existing SKUs, see every row problem. */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { Field, FormError } from './controls';
import { errorMessage, importRowErrors, type ItemsHooks } from './hooks';
import { itemsT as t } from './messages';
import type { ItemImportResult } from './types';

export interface ItemsImportProps {
  hooks: ItemsHooks;
}

export function ItemsImport({ hooks }: ItemsImportProps) {
  const imp = hooks.useImportItems();
  const [file, setFile] = React.useState<File | null>(null);
  const [updateExisting, setUpdateExisting] = React.useState(false);
  const [dryRun, setDryRun] = React.useState(true);
  const [result, setResult] = React.useState<ItemImportResult | null>(null);

  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    if (!file) return;
    setResult(null);
    try {
      setResult(await imp.mutateAsync({ file, updateExisting, dryRun }));
    } catch {
      // Surfaced below via `imp.error` (row-level problems when the server sent them).
    }
  }

  const rowErrors = importRowErrors(imp.error);
  return (
    <form onSubmit={submit} className="space-y-3 rounded-md border p-3" noValidate>
      <h3 className="text-sm font-semibold">{t('import.title')}</h3>
      <Field label={t('import.file')} required>
        <input type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </Field>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={updateExisting} onChange={(e) => setUpdateExisting(e.target.checked)} />
        {t('import.update_existing')}
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} />
        {t('import.dry_run')}
      </label>
      <Button type="submit" disabled={!file || imp.isPending}>{imp.isPending ? t('import.running') : t('import.submit')}</Button>
      {result ? (
        <p role="status" className="text-sm">
          {t(result.dry_run ? 'import.result_dry' : 'import.result', { created: result.created, updated: result.updated })}
        </p>
      ) : null}
      {rowErrors ? (
        <div role="alert" className="space-y-1 text-sm text-destructive">
          <p>{t('import.errors')}</p>
          <ul className="list-disc pl-5">
            {rowErrors.rows.map((r, i) => (
              <li key={`${r.line}-${r.field}-${i}`}>{`${t('import.line', { line: r.line })} · ${r.field}: ${r.message}`}</li>
            ))}
          </ul>
        </div>
      ) : (
        <FormError message={imp.error ? errorMessage(imp.error) : null} />
      )}
    </form>
  );
}
