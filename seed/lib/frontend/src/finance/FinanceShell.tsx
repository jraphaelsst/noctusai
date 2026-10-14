/**
 * `<FinanceShell/>` — navigation + page switch for the whole finance module. Product-agnostic: the host
 * mounts it under its own route (e.g. `/admin/financeiro/*`), builds `hooks = createFinanceHooks(api)` once,
 * passes `isAdmin` (`useIsOrgAdmin()` — UX only, the server enforces every write again) and, if it routes,
 * maps the URL segment ⇄ section with `financeSectionFromPath` / `financeSectionPath`.
 *
 * Sections: Visão geral · Contas a receber · Contas a pagar · Fluxo de caixa · DRE · Orçamento · Conciliação ·
 * Cadastros (contas, categorias, centros de custo, recorrências) · Contador (checklist, como o DRE é montado,
 * base do Simples, Livro Caixa, Relatório Mensal do MEI [só no regime MEI], arquivo do Domínio, exportações).
 * Uncontrolled by default; pass `section` + `onSectionChange` to control it.
 *
 * `isAccountant` (UX only) = the caller holds the accountant READ grant: reports and downloads are offered, writes stay
 * hidden. The server enforces both again (`finance.accountant_read:<org_id>`).
 */
import * as React from 'react';
import { AccountantChecklist } from './AccountantChecklist';
import { AccountsManager } from './AccountsManager';
import { AgingReport } from './AgingReport';
import { BudgetPage } from './BudgetPage';
import { CashflowReport } from './CashflowReport';
import { FinanceCategoryManager } from './CategoryManager';
import { CostCentersManager } from './CostCentersManager';
import { DreReport } from './DreReport';
import { DominioExport } from './DominioExport';
import { DreSettingsForm } from './DreSettingsForm';
import { EntriesTable } from './EntriesTable';
import { ExportsPanel } from './ExportsPanel';
import { FinanceOverview } from './FinanceOverview';
import { LivroCaixaReport } from './LivroCaixaReport';
import { MeiMonthlyReport } from './MeiMonthlyReport';
import { ReconciliationPage } from './ReconciliationPage';
import { RecurrencesManager } from './RecurrencesManager';
import { SimplesBaseReport } from './SimplesBaseReport';
import type { FinanceHooks } from './hooks';
import { t } from './i18n';

export const FINANCE_SECTIONS = [
  { key: 'overview', path: '', labelKey: 'nav.overview' },
  { key: 'receivable', path: 'receber', labelKey: 'nav.receivable' },
  { key: 'payable', path: 'pagar', labelKey: 'nav.payable' },
  { key: 'cashflow', path: 'fluxo-de-caixa', labelKey: 'nav.cashflow' },
  { key: 'dre', path: 'dre', labelKey: 'nav.dre' },
  { key: 'budget', path: 'orcamento', labelKey: 'nav.budget' },
  { key: 'reconciliation', path: 'conciliacao', labelKey: 'nav.reconciliation' },
  { key: 'registers', path: 'cadastros', labelKey: 'nav.registers' },
  { key: 'accountant', path: 'contador', labelKey: 'nav.accountant' },
] as const;
export type FinanceSectionKey = (typeof FINANCE_SECTIONS)[number]['key'];

export const REGISTER_TABS = ['accounts', 'categories', 'cost_centers', 'recurrences'] as const;
export type RegisterTab = (typeof REGISTER_TABS)[number];
/** `mei` is only shown when the store's tax regime is MEI. */
export const ACCOUNTANT_TABS = ['checklist', 'dre_settings', 'simples', 'livro_caixa', 'mei', 'dominio', 'exports'] as const;
export type AccountantTab = (typeof ACCOUNTANT_TABS)[number];

/** URL segment (`receber`, `''`...) → section; unknown → overview. */
export function financeSectionFromPath(segment: string | null | undefined): FinanceSectionKey {
  const s = (segment ?? '').replace(/^\/+|\/+$/g, '').split('/')[0] ?? '';
  return FINANCE_SECTIONS.find((x) => x.path === s)?.key ?? 'overview';
}
export function financeSectionPath(key: FinanceSectionKey): string {
  return FINANCE_SECTIONS.find((x) => x.key === key)?.path ?? '';
}

export interface FinanceShellProps {
  hooks: FinanceHooks;
  isAdmin?: boolean;
  /** The caller holds the accountant read grant (UX only; the server enforces it). */
  isAccountant?: boolean;
  section?: FinanceSectionKey;
  onSectionChange?: (key: FinanceSectionKey) => void;
  now?: Date;
}

function SubTabs<T extends string>({ tabs, active, onChange, labelPrefix, label }: { tabs: readonly T[]; active: T; onChange: (t: T) => void; labelPrefix: string; label: string }) {
  return (
    <div role="tablist" aria-label={label} className="flex flex-wrap gap-1 border-b">
      {tabs.map((k) => (
        <button
          key={k}
          type="button"
          role="tab"
          aria-selected={active === k}
          onClick={() => onChange(k)}
          className={`px-3 py-1.5 text-sm ${active === k ? 'border-b-2 border-primary font-medium' : 'text-muted-foreground hover:text-foreground'}`}
        >
          {t(`${labelPrefix}.${k}`)}
        </button>
      ))}
    </div>
  );
}

function AccountantSection({
  hooks, isAdmin, canRead, now, onGoToRegisters,
}: { hooks: FinanceHooks; isAdmin: boolean; canRead: boolean; now?: Date; onGoToRegisters: () => void }) {
  const [tab, setTab] = React.useState<AccountantTab>('checklist');
  const settings = hooks.useDreSettings();
  const isMei = settings.data?.tax_regime === 'mei';
  const tabs = ACCOUNTANT_TABS.filter((k) => k !== 'mei' || isMei);
  const active = tabs.includes(tab) ? tab : 'checklist';
  return (
    <div className="space-y-4">
      <SubTabs<AccountantTab> tabs={tabs} active={active} onChange={(k) => setTab(k)} labelPrefix="accountant_tabs" label={t('nav.accountant')} />
      {active === 'checklist' ? <AccountantChecklist hooks={hooks} isAdmin={isAdmin} canExport={canRead} onOpenTab={(k) => setTab(k)} /> : null}
      {active === 'dre_settings' ? <DreSettingsForm hooks={hooks} isAdmin={isAdmin} /> : null}
      {active === 'simples' ? <SimplesBaseReport hooks={hooks} now={now} /> : null}
      {active === 'livro_caixa' ? <LivroCaixaReport hooks={hooks} canExport={canRead} now={now} /> : null}
      {active === 'mei' ? <MeiMonthlyReport hooks={hooks} canExport={canRead} now={now} /> : null}
      {active === 'dominio' ? <DominioExport hooks={hooks} canExport={canRead} onGoToRegisters={onGoToRegisters} now={now} /> : null}
      {active === 'exports' ? <ExportsPanel hooks={hooks} isAdmin={isAdmin} canExport={canRead} now={now} /> : null}
    </div>
  );
}

export function FinanceShell({ hooks, isAdmin = false, isAccountant = false, section: controlled, onSectionChange, now }: FinanceShellProps) {
  const canRead = isAdmin || isAccountant;
  const [inner, setInner] = React.useState<FinanceSectionKey>('overview');
  const section = controlled ?? inner;
  const [registerTab, setRegisterTab] = React.useState<RegisterTab>('accounts');

  const go = React.useCallback(
    (key: FinanceSectionKey) => {
      setInner(key);
      onSectionChange?.(key);
    },
    [onSectionChange],
  );

  let page: React.ReactNode;
  switch (section) {
    case 'overview':
      page = (
        <FinanceOverview
          hooks={hooks}
          now={now}
          onNavigate={(to) => {
            if (to === 'accounts') {
              setRegisterTab('accounts');
              go('registers');
            } else go(to);
          }}
        />
      );
      break;
    case 'receivable':
      page = <EntriesTable hooks={hooks} direction="receivable" isAdmin={isAdmin} />;
      break;
    case 'payable':
      page = <EntriesTable hooks={hooks} direction="payable" isAdmin={isAdmin} />;
      break;
    case 'cashflow':
      page = (
        <div className="space-y-8">
          <CashflowReport hooks={hooks} now={now} />
          <AgingReport hooks={hooks} />
        </div>
      );
      break;
    case 'dre':
      page = <DreReport hooks={hooks} now={now} />;
      break;
    case 'budget':
      page = <BudgetPage hooks={hooks} isAdmin={isAdmin} now={now} />;
      break;
    case 'reconciliation':
      page = <ReconciliationPage hooks={hooks} isAdmin={isAdmin} />;
      break;
    case 'registers':
      page = (
        <div className="space-y-4">
          <SubTabs<RegisterTab> tabs={REGISTER_TABS} active={registerTab} onChange={(k) => setRegisterTab(k)} labelPrefix="registers" label={t('nav.registers')} />
          {registerTab === 'accounts' ? <AccountsManager hooks={hooks} isAdmin={isAdmin} /> : null}
          {registerTab === 'categories' ? <FinanceCategoryManager hooks={hooks} isAdmin={isAdmin} /> : null}
          {registerTab === 'cost_centers' ? <CostCentersManager hooks={hooks} isAdmin={isAdmin} /> : null}
          {registerTab === 'recurrences' ? <RecurrencesManager hooks={hooks} isAdmin={isAdmin} /> : null}
        </div>
      );
      break;
    case 'accountant':
      page = (
        <AccountantSection
          hooks={hooks}
          isAdmin={isAdmin}
          canRead={canRead}
          now={now}
          onGoToRegisters={() => {
            setRegisterTab('categories');
            go('registers');
          }}
        />
      );
      break;
  }

  return (
    <div className="space-y-4">
      <nav aria-label={t('nav.label')}>
        <ul className="flex flex-wrap gap-1 border-b">
          {FINANCE_SECTIONS.map((s) => (
            <li key={s.key}>
              <button
                type="button"
                aria-current={section === s.key ? 'page' : undefined}
                onClick={() => go(s.key)}
                className={`px-3 py-2 text-sm ${section === s.key ? 'border-b-2 border-primary font-semibold' : 'text-muted-foreground hover:text-foreground'}`}
              >
                {t(s.labelKey)}
              </button>
            </li>
          ))}
        </ul>
      </nav>
      <div>{page}</div>
    </div>
  );
}
