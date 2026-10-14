/**
 * Enum parity — the exact CONTRACT §3.1 value lists (the backend `types.py` mirror test fails if either
 * side changes a value), and i18n coverage: every literal key a component passes to `t()` exists, every enum
 * value has a label (so a new member can never render as a raw key).
 */
import { describe, it, expect } from 'vitest';
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import {
  ACCOUNT_KINDS, CATEGORY_BEHAVIORS, CATEGORY_DIRECTIONS, ENTRY_DIRECTIONS, ENTRY_SOURCES, ENTRY_STATUSES, FREQUENCIES,
  LEDGER_ORIGINS, MATCH_STATUSES, SETTLEMENT_KINDS, STATEMENT_FORMATS, AGING_BUCKET_KEYS,
} from './types';
import { DRE_ASSIGNABLE_LINES, DRE_LINE_SETTING_KEYS, DRE_LINES, DRE_SUBTOTAL_KEYS, FINANCE_TAX_REGIMES } from './dreTypes';
import { MESSAGES } from './messages';
import { t } from './i18n';
import { FINANCE_SECTIONS, REGISTER_TABS, ACCOUNTANT_TABS } from './FinanceShell';

describe('finance enums (CONTRACT §3.1)', () => {
  it('matches the contract value lists exactly', () => {
    expect({
      AccountKind: ACCOUNT_KINDS,
      EntryDirection: ENTRY_DIRECTIONS,
      EntryStatus: ENTRY_STATUSES,
      CategoryDirection: CATEGORY_DIRECTIONS,
      Frequency: FREQUENCIES,
      EntrySource: ENTRY_SOURCES,
      SettlementKind: SETTLEMENT_KINDS,
      LedgerOrigin: LEDGER_ORIGINS,
      StatementFormat: STATEMENT_FORMATS,
      MatchStatus: MATCH_STATUSES,
    }).toEqual({
      AccountKind: ['checking', 'savings', 'cash', 'gateway', 'credit_card', 'investment'],
      EntryDirection: ['payable', 'receivable'],
      EntryStatus: ['open', 'partial', 'paid', 'cancelled'],
      CategoryDirection: ['income', 'expense', 'transfer'],
      Frequency: ['daily', 'weekly', 'biweekly', 'monthly', 'bimonthly', 'quarterly', 'semiannual', 'annual'],
      EntrySource: ['manual', 'recurrence', 'installment', 'commerce_order', 'import', 'external', 'purchasing'],
      SettlementKind: ['payment', 'refund'],
      LedgerOrigin: ['settlement', 'fee', 'transfer', 'adjustment', 'opening'],
      StatementFormat: ['ofx', 'csv'],
      MatchStatus: ['unmatched', 'suggested', 'matched', 'ignored'],
    });
  });

  it('DRE lines mirror the backend DreLine enum (types.py); subtotals are computed keys, not members', () => {
    expect(DRE_LINES).toEqual([
      'gross_revenue', 'deductions', 'cost_of_sales', 'selling_expenses', 'administrative_expenses', 'other_operating',
      'financial_revenue', 'financial_expenses', 'income_taxes', 'unclassified',
    ]);
    expect(DRE_ASSIGNABLE_LINES).toEqual(DRE_LINES.filter((l) => l !== 'unclassified'));
    expect(DRE_SUBTOTAL_KEYS).toEqual(['net_revenue', 'gross_result', 'result_before_financial', 'result_before_income_taxes', 'net_result']);
    expect(DRE_LINE_SETTING_KEYS).toEqual(['gateway_fee_line', 'anticipation_fee_line', 'chargeback_line', 'chargeback_fee_line', 'installment_interest_line']);
    expect(FINANCE_TAX_REGIMES).toEqual(['mei', 'simples', 'presumido', 'unknown']);
  });
});

describe('finance messages', () => {
  const dir = __dirname;
  const sources = readdirSync(dir)
    .filter((f) => /\.tsx?$/.test(f) && !/\.test\.|testUtils|messages\.ts$/.test(f))
    .map((f) => readFileSync(join(dir, f), 'utf8'));

  it('every literal t("…") key used by a component exists', () => {
    const missing: string[] = [];
    for (const src of sources) {
      for (const m of src.matchAll(/\bt\('([a-z_0-9.]+)'/g)) if (!(m[1] in MESSAGES)) missing.push(m[1]);
      for (const m of src.matchAll(/labelKey: '([a-z_0-9.]+)'/g)) if (!(m[1] in MESSAGES)) missing.push(m[1]);
    }
    expect([...new Set(missing)]).toEqual([]);
  });

  it('every enum value has a label', () => {
    const keys: string[] = [
      ...ENTRY_STATUSES.map((s) => `entry_status.${s}`),
      'entry_status.overdue',
      ...ENTRY_DIRECTIONS.map((d) => `entry.direction_${d}`),
      ...ACCOUNT_KINDS.map((k) => `account_kind.${k}`),
      ...CATEGORY_DIRECTIONS.map((d) => `category_direction.${d}`),
      ...FREQUENCIES.map((f) => `frequency.${f}`),
      ...MATCH_STATUSES.map((s) => `match_status.${s}`),
      ...CATEGORY_BEHAVIORS.map((b) => `behavior.${b}`),
      ...AGING_BUCKET_KEYS.map((k) => `aging.bucket_${k}`),
      ...[...DRE_LINES, ...DRE_SUBTOTAL_KEYS].map((l) => `dre_line.${l}`),
      ...['revenue', 'variable_costs', 'contribution_margin', 'fixed_costs', 'other_income', 'net_result'].flatMap((k) => [`dre_managerial.${k}`, `dre_managerial_help.${k}`]),
      ...['dre_csv', 'entries_csv'].map((k) => `accountant.export_${k}`),
      ...[...DRE_LINES, ...DRE_SUBTOTAL_KEYS].flatMap((l) => [`dre_help.${l}.what`, `dre_help.${l}.example`, `dre_help.${l}.source`]),
      ...FINANCE_TAX_REGIMES.flatMap((r) => [`finance_regime.${r}`, `dre_settings.regime_help_${r}`]),
      ...DRE_LINE_SETTING_KEYS.flatMap((k) => [`dre_settings.${k}`, `dre_settings.${k}_help`]),
      ...['provisional', 'confirmed'].map((s) => `accountant.status_${s}`),
      ...FINANCE_SECTIONS.map((s) => s.labelKey),
      ...REGISTER_TABS.map((k) => `registers.${k}`),
      ...ACCOUNTANT_TABS.map((k) => `accountant_tabs.${k}`),
    ];
    expect(keys.filter((k) => !(k in MESSAGES))).toEqual([]);
  });

  it('translator interpolates and falls back to the key', () => {
    expect(t('entry.installments_invalid', { max: 120 })).toContain('120');
    expect(t('nao.existe')).toBe('nao.existe');
  });
});
