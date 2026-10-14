/** Finance organ — public surface (re-exported from the `@noctusai/lib` barrel). */
export * from './types';
export * from './dreTypes';
export { createFinanceHooks, createFinanceTransport, financeKeys, FINANCE_EXPORT_PATHS, FINANCE_BASE } from './hooks';
export type {
  FinanceApi,
  FinanceHooks,
  EntryListParams,
  PeriodParams,
  CashflowParams,
  StatementLineParams,
  StatementImportInput,
  DownloadInput,
} from './hooks';
export { formatDate, formatMonth, remainingCents, toCompetenceMonth, monthStartIso, monthEndIso } from './format';
export { t as financeT, useFinanceT } from './i18n';

export { FinanceShell, FINANCE_SECTIONS, REGISTER_TABS, ACCOUNTANT_TABS, financeSectionFromPath, financeSectionPath } from './FinanceShell';
export type { FinanceShellProps, FinanceSectionKey, RegisterTab, AccountantTab } from './FinanceShell';
export { FinanceOverview } from './FinanceOverview';
export type { FinanceOverviewProps } from './FinanceOverview';
export { EntriesTable } from './EntriesTable';
export type { EntriesTableProps } from './EntriesTable';
export { EntryDialog } from './EntryDialog';
export type { EntryDialogProps } from './EntryDialog';
export { EntryDetailDialog } from './EntryDetailDialog';
export type { EntryDetailDialogProps } from './EntryDetailDialog';
export { SettleDialog } from './SettleDialog';
export type { SettleDialogProps } from './SettleDialog';
export { AttachmentsPanel } from './AttachmentsPanel';
export type { AttachmentsPanelProps } from './AttachmentsPanel';
export { AccountsManager } from './AccountsManager';
export type { AccountsManagerProps } from './AccountsManager';
export { TransferDialog } from './TransferDialog';
export type { TransferDialogProps } from './TransferDialog';
// `CategoryManager` is the commerce catalog organ — the finance one carries the prefix.
export { FinanceCategoryManager, DRE_LINES_BY_DIRECTION, flattenCategories as flattenFinanceCategories } from './CategoryManager';
export type { FinanceCategoryManagerProps } from './CategoryManager';
export { CostCentersManager } from './CostCentersManager';
export type { CostCentersManagerProps } from './CostCentersManager';
export { RecurrencesManager } from './RecurrencesManager';
export type { RecurrencesManagerProps } from './RecurrencesManager';
export { CashflowReport } from './CashflowReport';
export type { CashflowReportProps } from './CashflowReport';
export { AgingReport } from './AgingReport';
export type { AgingReportProps } from './AgingReport';
export { ReconciliationPage } from './ReconciliationPage';
export type { ReconciliationPageProps } from './ReconciliationPage';
export { ExportsPanel } from './ExportsPanel';
export type { ExportsPanelProps } from './ExportsPanel';
export { DreReport } from './DreReport';
export type { DreReportProps } from './DreReport';
export { DreSettingsForm } from './DreSettingsForm';
export type { DreSettingsFormProps } from './DreSettingsForm';
export { AccountantChecklist } from './AccountantChecklist';
export type { AccountantChecklistProps } from './AccountantChecklist';
export { SimplesBaseReport } from './SimplesBaseReport';
export type { SimplesBaseReportProps } from './SimplesBaseReport';
