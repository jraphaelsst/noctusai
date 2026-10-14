/**
 * `<PartiesCsvActions/>` — export the (filtered) list as CSV and import a CSV with a row-level report.
 *
 * Export is open to every reader (the server masks `doc` for non-admins); import is admin-only
 * (`canWrite` hides it — UX only, the server enforces). A "validate only" import writes nothing.
 */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { FormError } from './controls';
import { errorMessage, type PartiesHooks } from './hooks';
import { t } from './i18n';
import type { PartiesImportResult, PartiesListParams } from './types';

export interface PartiesCsvActionsProps {
  hooks: PartiesHooks;
  /** The list filters the export should honour. */
  filters?: PartiesListParams;
  canWrite?: boolean;
}

function download(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function PartiesCsvActions({ hooks, filters = {}, canWrite = false }: PartiesCsvActionsProps) {
  const exporter = hooks.useExportParties();
  const importer = hooks.useImportParties();
  const [dryRun, setDryRun] = React.useState(false);
  const [result, setResult] = React.useState<PartiesImportResult | null>(null);
  const fileRef = React.useRef<HTMLInputElement>(null);

  async function onExport() {
    try {
      download(await exporter.mutateAsync(filters), 'cadastros.csv');
    } catch {
      // Rendered below from `exporter.error`.
    }
  }

  async function onFile(ev: React.ChangeEvent<HTMLInputElement>) {
    const file = ev.target.files?.[0];
    ev.target.value = ''; // the same file can be picked again after a fix
    if (!file) return;
    setResult(null);
    try {
      setResult(await importer.mutateAsync({ file, dryRun }));
    } catch {
      // Rendered below from `importer.error`.
    }
  }

  const error = exporter.error ?? importer.error;
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="outline" disabled={exporter.isPending} onClick={onExport}>
          {exporter.isPending ? t('csv.exporting') : t('csv.export')}
        </Button>
        {canWrite ? (
          <>
            <Button size="sm" variant="outline" disabled={importer.isPending} onClick={() => fileRef.current?.click()}>
              {importer.isPending ? t('csv.importing') : t('csv.import')}
            </Button>
            <input ref={fileRef} type="file" accept=".csv,text/csv" className="hidden" aria-label={t('csv.import')} onChange={onFile} />
            <label className="flex items-center gap-1 text-xs">
              <input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} />
              {t('csv.dry_run')}
            </label>
          </>
        ) : null}
      </div>
      <FormError message={error ? `${t('error.generic')}: ${errorMessage(error)}` : null} />
      {result ? (
        <div role="status" className="space-y-1 rounded-md border p-3 text-sm">
          <p>{t(result.dry_run ? 'csv.result_dry' : 'csv.result_created', { n: result.created })}</p>
          {result.skipped.length > 0 ? <p>{t('csv.result_skipped', { n: result.skipped.length })}</p> : null}
          {result.errors.length > 0 ? (
            <>
              <p className="text-destructive">{t('csv.result_errors', { n: result.errors.length })}</p>
              <ul className="max-h-40 list-disc space-y-0.5 overflow-y-auto pl-5 text-xs text-destructive">
                {result.errors.map((e) => (
                  <li key={`${e.line}-${e.field ?? ''}`}>
                    {t('csv.line', { line: e.line })}: {e.message ?? e.code}
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
