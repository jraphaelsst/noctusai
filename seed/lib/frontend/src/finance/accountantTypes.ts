/** Wire types for the accountant additions (E16/E21): budget vs actual, Livro Caixa, MEI monthly report, Domínio export. */
import { ApiError } from '../api';
import type { ActivityKind, CategoryDirection } from './types';
import type { DreWarning, FinanceTaxRegime } from './dreTypes';

// ---- budgets -------------------------------------------------------------------------------------------------

export interface Budget {
  id: string;
  category_id: string;
  /** First of the month (`YYYY-MM-01`). */
  month: string;
  amount_cents: number;
}
export interface BudgetItemInput {
  category_id: string;
  /** Any day of the month; the server stores the first. */
  month: string;
  amount_cents: number;
}
/** `ok` within plan · `over` an expense above plan · `under` income below plan · `no_budget` nothing planned. */
export type BudgetStatus = 'ok' | 'over' | 'under' | 'no_budget';
export interface BudgetCell {
  budget_cents: number;
  actual_cents: number;
  /** actual − budget. */
  variance_cents: number;
  status: BudgetStatus;
}
export interface BudgetRow {
  category_id: string;
  name: string;
  /** `Group / Category`. */
  path: string;
  direction: CategoryDirection;
  months: Record<string, BudgetCell>;
  total: BudgetCell;
}
export interface BudgetSide {
  by_month: Record<string, { budget_cents: number; actual_cents: number; variance_cents: number }>;
  budget_cents: number;
  actual_cents: number;
  variance_cents: number;
}
/** `GET /api/finance/reports/budget`. */
export interface BudgetReportData {
  from: string;
  to: string;
  months: string[];
  rows: BudgetRow[];
  income: BudgetSide;
  expense: BudgetSide;
  result: { budget_cents: number; actual_cents: number };
  warnings: DreWarning[];
  notes: string[];
  source: string;
}

// ---- Livro Caixa ---------------------------------------------------------------------------------------------

export interface LivroCaixaRow {
  on: string;
  kind: string;
  history: string;
  in: number;
  out: number;
  balance_cents: number;
  counterparty: string | null;
  category: string | null;
  account: string | null;
  ledger_id: string | null;
}
/** `GET /api/finance/reports/livro-caixa` (totals cover the whole period; `rows` is one page). */
export interface LivroCaixaData {
  from: string;
  to: string;
  opening_balance_cents: number;
  total_in_cents: number;
  total_out_cents: number;
  closing_balance_cents: number;
  row_count: number;
  rows: LivroCaixaRow[];
  page: number;
  page_size: number;
  legal_basis: string;
  notes: string[];
  disclaimer: string;
}

// ---- MEI Relatório Mensal ------------------------------------------------------------------------------------

export interface MeiGroup {
  without_invoice_cents: number;
  with_invoice_cents: number;
  total_cents: number;
}
export interface MeiFieldLabels {
  title: string;
  without: string;
  without_roman: string;
  with: string;
  with_roman: string;
  total: string;
  total_roman: string;
}
/** `GET /api/finance/reports/mei-monthly`. */
export interface MeiMonthlyData {
  /** `YYYY-MM`. */
  month: string;
  tax_regime: FinanceTaxRegime;
  /** False outside `tax_regime = mei`. */
  applicable: boolean;
  basis: 'cash';
  deadline: string;
  groups: Record<ActivityKind, MeiGroup>;
  fields: Record<ActivityKind, MeiFieldLabels>;
  grand_total: { label: string; roman: string };
  total_cents: number;
  /** Receipts in categories with no activity group: NOT in the totals. */
  unassigned_cents: number;
  /** Receipts whose nota fiscal is unknown: counted as "sem documento fiscal". */
  unknown_invoice_cents: number;
  warnings: DreWarning[];
  notes: string[];
  legal_basis: string;
  disclaimer: string;
}

// ---- Domínio export ------------------------------------------------------------------------------------------

export interface DominioMissing {
  categories: { id: string; name: string }[];
  accounts: { id: string; name: string }[];
  issues: { code: string; count: number }[];
}

/** The 422 `dominio_codigos_ausentes` details, or null when `err` is some other error. */
export function dominioMissingOf(err: unknown): DominioMissing | null {
  if (!(err instanceof ApiError) || err.code !== 'dominio_codigos_ausentes') return null;
  const d = (err.body as { error?: { details?: Partial<DominioMissing> } } | undefined)?.error?.details ?? {};
  return { categories: d.categories ?? [], accounts: d.accounts ?? [], issues: d.issues ?? [] };
}
