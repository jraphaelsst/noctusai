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
import { useState } from 'react';
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

const TABS = [
  { id: 'geral', label: 'Geral' },
  { id: 'secoes', label: 'Seções' },
  { id: 'produtos', label: 'Produtos' },
  { id: 'confianca', label: 'Confiança' },
  { id: 'prova-social', label: 'Prova social' },
  { id: 'faq', label: 'FAQ' },
  { id: 'rastreamento', label: 'Rastreamento' },
  { id: 'historico', label: 'Histórico' },
] as const;

type TabId = (typeof TABS)[number]['id'];

export function Settings() {
  const { isMarketing } = useAuth();
  const { data, isPending, isFetching, error, refetch } = useWebsiteSettings();
  const update = useUpdateWebsiteSettings();
  const [tab, setTab] = useState<TabId>('geral');
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

  return (
    <div className="space-y-6" aria-busy={isRefreshing}>
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Configurações do site</h1>
          <p className="mt-1 text-muted-foreground">noctusai.com — muda sem precisar de um novo deploy</p>
        </div>
        <div className="flex items-center gap-2">
          {dirty && !conflict && (
            <span className="text-xs text-muted-foreground">Alterações não salvas</span>
          )}
          <Button variant="outline" size="sm" disabled={!dirty || update.isPending} onClick={() => setDraft(data.settings)}>
            Descartar
          </Button>
          <Button size="sm" disabled={!dirty || update.isPending} onClick={save}>
            {update.isPending ? 'Salvando…' : 'Salvar alterações'}
          </Button>
        </div>
      </header>

      {conflict && (
        <div role="alert" className="flex items-center justify-between gap-3 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
          <span>Outra pessoa salvou antes — recarregue.</span>
          <Button size="sm" variant="outline" onClick={discardAndReload}>Recarregar</Button>
        </div>
      )}
      {update.error && !conflict && (
        <p role="alert" className="text-sm text-destructive">{update.error.message}</p>
      )}

      <nav role="tablist" aria-label="Seções de configuração" className="flex flex-wrap gap-2 border-b border-border pb-2">
        {TABS.map((t) => (
          <Button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            variant={tab === t.id ? 'primary' : 'ghost'}
            size="sm"
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </Button>
        ))}
      </nav>

      <div role="tabpanel">
        {tab === 'geral' && <GeneralTab draft={effectiveDraft} onChange={updateDraft} isMarketing={isMarketing} />}
        {tab === 'secoes' && <SectionsTab draft={effectiveDraft} onChange={updateDraft} isMarketing={isMarketing} />}
        {tab === 'produtos' && <ProductsTab draft={effectiveDraft} onChange={updateDraft} isMarketing={isMarketing} />}
        {tab === 'confianca' && <TrustTab draft={effectiveDraft} onChange={updateDraft} isMarketing={isMarketing} />}
        {tab === 'prova-social' && <SocialProofTab draft={effectiveDraft} onChange={updateDraft} isMarketing={isMarketing} />}
        {tab === 'faq' && <FaqTab draft={effectiveDraft} onChange={updateDraft} isMarketing={isMarketing} />}
        {tab === 'rastreamento' && <TrackingTab draft={effectiveDraft} onChange={updateDraft} isMarketing={isMarketing} />}
        {tab === 'historico' && <HistoryTab isMarketing={isMarketing} currentVersion={data.version} />}
      </div>
    </div>
  );
}

export default Settings;
