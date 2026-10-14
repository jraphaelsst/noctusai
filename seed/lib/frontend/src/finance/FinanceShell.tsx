/**
 * `<FinanceShell/>` — navigation + page switch for the whole finance module. Product-agnostic: the host
 * mounts it under its own route (e.g. `/admin/financeiro/*`), builds `hooks = createFinanceHooks(api)` once,
 * passes `isAdmin` (`useIsOrgAdmin()` — UX only, the server enforces every write again) and, if it routes,
 * maps the URL segment ⇄ section with `financeSectionFromPath` / `financeSectionPath`.
 *
 * Sections: Visão geral · Contas a receber · Contas a pagar · Fluxo de caixa · DRE · Conciliação ·
 * Cadastros (contas, categorias, centros de custo, recorrências) · Contador (checklist, como o DRE é montado,
 * base do Simples, exportações). Uncontrolled by default; pass `section` + `onSectionChange` to control it.
 */
import * as React from 'react';
import { AccountantChecklist } from './AccountantChecklist';
import { AccountsManager } from './AccountsManager';
import { AgingReport } from './AgingReport';
import { CashflowReport } from './CashflowReport';
import { FinanceCategoryManager } from './CategoryManager';
import { CostCentersManager } from './CostCentersManager';
import { DreReport } from './DreReport';
import { DreSettingsForm } from './DreSettingsForm';
import { EntriesTable } from './EntriesTable';
import { ExportsPanel } from './ExportsPanel';
import { FinanceOverview } from './FinanceOverview';
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
  { key: 'reconciliation', path: 'conciliacao', labelKey: 'nav.reconciliation' },
  { key: 'registers', path: 'cadastros', labelKey: 'nav.registers' },
  { key: 'accountant', path: 'contador', labelKey: 'nav.accountant' },
] as const;
export type FinanceSectionKey = (typeof FINANCE_SECTIONS)[number]['key'];

export const REGISTER_TABS = ['accounts', 'categories', 'cost_centers', 'recurrences'] as const;
export type RegisterTab = (typeof REGISTER_TABS)[number];
export const ACCOUNTANT_TABS = ['checklist', 'dre_settings', 'simples', 'exports'] as const;
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

export function FinanceShell({ hooks, isAdmin = false, section: controlled, onSectionChange, now }: FinanceShellProps) {
  const [inner, setInner] = React.useState<FinanceSectionKey>('overview');
  const section = controlled ?? inner;
  const [registerTab, setRegisterTab] = React.useState<RegisterTab>('accounts');
  const [accountantTab, setAccountantTab] = React.useState<AccountantTab>('checklist');

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
        <div className="space-y-4">
          <SubTabs<AccountantTab> tabs={ACCOUNTANT_TABS} active={accountantTab} onChange={(k) => setAccountantTab(k)} labelPrefix="accountant_tabs" label={t('nav.accountant')} />
          {accountantTab === 'checklist' ? <AccountantChecklist hooks={hooks} isAdmin={isAdmin} /> : null}
          {accountantTab === 'dre_settings' ? <DreSettingsForm hooks={hooks} isAdmin={isAdmin} /> : null}
          {accountantTab === 'simples' ? <SimplesBaseReport hooks={hooks} now={now} /> : null}
          {accountantTab === 'exports' ? <ExportsPanel hooks={hooks} isAdmin={isAdmin} now={now} /> : null}
        </div>
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
