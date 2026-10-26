/**
 * `<Settings/>` — Website > Configurações (`/admin/website/settings`).
 *
 * Contract: `src/website/docs/15-api-contract.md` §2 (`WebsiteSettings`
 * shape) / §6 (this page's spec). ONE shared draft backs every tab — every
 * tab mutates its own slice of the same `WebsiteSettings` object, and a
 * single sticky save bar sends the WHOLE object via `PUT
 * /api/admin/website/settings` with `expected_version` (the endpoint takes
 * the complete settings object every time; there is no per-field PATCH).
 *
 * `site_enabled`/`signup_enabled` are the two exceptions worth naming: they
 * are staged into the SAME shared draft (via a confirm dialog inside
 * `GeneralTab`), not saved as an immediate side-channel PUT — one save path,
 * one 409/conflict story, everywhere.
 *
 * 409 (someone else saved first) shows the contract-mandated message and
 * offers a one-click reload that discards the local draft in favor of the
 * fresh server version — never a silent overwrite.
 *
 * The draft is seeded SYNCHRONOUSLY from `data.settings` on every render
 * where no local edit exists yet (`draft ?? data.settings`), not via a
 * `useEffect` — an effect-seeded draft has one render where `data` is
 * truthy but `draft` is still `null` (e.g. right after `discardAndReload`
 * clears it), which would render "Nenhuma configuração encontrada." over
 * settings that are, in fact, loaded (the lying-empty-state shape this
 * platform's loading-state rule exists to prevent).
 */
import { useState, type ReactNode } from 'react';
import { SectionTabsPage, type SectionTab } from '@noctusai/lib/components';
import { Button, EmptyState, ErrorState, Skeleton } from '@noctusai/lib/design-system';
import { useAuth } from '../../../lib/auth-context';
import {
  isConflictError,
  useUpdateWebsiteSettings,
  useWebsiteSettings,
  type WebsiteSettings,
} from '../../../lib/website';
import { GeneralTab } from './settings/GeneralTab';
import { SectionsTab } from './settings/SectionsTab';
import { ProductsTab } from './settings/ProductsTab';
import { TrustTab } from './settings/TrustTab';
import { SocialProofTab } from './settings/SocialProofTab';
import { FaqTab } from './settings/FaqTab';
import { TrackingTab } from './settings/TrackingTab';
import { HistoryTab } from './settings/HistoryTab';

export function Settings() {
  const { isMarketing } = useAuth();
  const { data, isPending, isFetching, error, refetch } = useWebsiteSettings();
  const update = useUpdateWebsiteSettings();
  const [draft, setDraft] = useState<WebsiteSettings | null>(null);

  const showSkeleton = isPending && !data;
  const isRefreshing = isFetching && !!data;
  // No local edit yet (fresh load, or just after `discardAndReload`) ⇒ the
  // effective draft IS the server settings — computed every render, never
  // a `null` gap a `useEffect` would otherwise leave for one tick.
  const effectiveDraft = draft ?? data?.settings ?? null;

  function updateDraft(updater: (prev: WebsiteSettings) => WebsiteSettings) {
    setDraft((prev) => updater(prev ?? (data as { settings: WebsiteSettings }).settings));
  }

  function discardAndReload() {
    update.reset();
    setDraft(null);
    refetch();
  }

  function save() {
    if (!effectiveDraft || !data) return;
    update.mutate({ settings: effectiveDraft, expectedVersion: data.version });
  }

  if (showSkeleton) {
    return (
      <div className="space-y-4">
        <Skeleton height={40} announce label="Carregando configurações do site" />
        <Skeleton height={320} announce={false} />
      </div>
    );
  }
  if (error && !data) {
    return <ErrorState message={`Não foi possível carregar as configurações: ${error.message}`} />;
  }
  if (!data || !effectiveDraft) {
    return <EmptyState message="Nenhuma configuração encontrada." />;
  }

  const dirty = JSON.stringify(effectiveDraft) !== JSON.stringify(data.settings);
  const conflict = isConflictError(update.error);

  // The save bar + conflict/error alerts sit above EVERY section (one shared draft, one save path), so they are
  // rendered by each section's frame; the draft lives here, so it survives switching tabs.
  const frame = (body: ReactNode) => (
    <div className="space-y-6" aria-busy={isRefreshing}>
      <div className="flex flex-wrap items-center justify-end gap-2">
        {dirty && !conflict && <span className="text-xs text-muted-foreground">Alterações não salvas</span>}
        <Button variant="outline" size="sm" disabled={!dirty || update.isPending} onClick={() => setDraft(data.settings)}>
          Descartar
        </Button>
        <Button size="sm" disabled={!dirty || update.isPending} onClick={save}>
          {update.isPending ? 'Salvando…' : 'Salvar alterações'}
        </Button>
      </div>

      {conflict && (
        <div role="alert" className="flex items-center justify-between gap-3 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
          <span>Outra pessoa salvou antes — recarregue.</span>
          <Button size="sm" variant="outline" onClick={discardAndReload}>Recarregar</Button>
        </div>
      )}
      {update.error && !conflict && (
        <p role="alert" className="text-sm text-destructive">{update.error.message}</p>
      )}

      {body}
    </div>
  );

  const tabProps = { draft: effectiveDraft, onChange: updateDraft, isMarketing };
  const sections: SectionTab[] = [
    { key: 'geral', label: 'Geral', render: () => frame(<GeneralTab {...tabProps} />) },
    { key: 'secoes', label: 'Seções', render: () => frame(<SectionsTab {...tabProps} />) },
    { key: 'produtos', label: 'Produtos', render: () => frame(<ProductsTab {...tabProps} />) },
    { key: 'confianca', label: 'Confiança', render: () => frame(<TrustTab {...tabProps} />) },
    { key: 'prova-social', label: 'Prova social', render: () => frame(<SocialProofTab {...tabProps} />) },
    { key: 'faq', label: 'FAQ', render: () => frame(<FaqTab {...tabProps} />) },
    { key: 'rastreamento', label: 'Rastreamento', render: () => frame(<TrackingTab {...tabProps} />) },
    { key: 'historico', label: 'Histórico', render: () => frame(<HistoryTab isMarketing={isMarketing} currentVersion={data.version} />) },
  ];

  return (
    <SectionTabsPage
      basePath="/admin/website/settings"
      title="Configurações do site"
      description="noctusai.com — muda sem precisar de um novo deploy"
      sections={sections}
    />
  );
}

export default Settings;
