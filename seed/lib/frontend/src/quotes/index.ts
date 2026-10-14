/** Quotes organ — public surface (re-exported from the `@noctusai/lib` barrel). Backend: `noctusai_lib.domain.quotes`. */
export { QUOTE_STATUSES, QUOTE_LINE_KINDS, QUOTE_CONVERT_TO, QUOTE_CONVERSION_STATUSES, QUOTE_ERROR_CODES } from './types';
export type {
  QuoteAcceptance,
  QuoteCalculation,
  QuoteConversionStatus,
  QuoteConvertTo,
  QuoteEnvelope,
  QuoteEventRecord,
  QuoteInput,
  QuoteItemOption,
  QuoteLineInput,
  QuoteLineKind,
  QuoteLineRecord,
  QuoteListParams,
  QuotePaginated,
  QuotePartyOption,
  QuotePartyRef,
  QuotePatch,
  QuotePublicView,
  QuoteRecord,
  QuoteSendInput,
  QuoteSendResult,
  QuoteStatus,
} from './types';
export { createQuotesHooks, createQuotesPublicHooks, quotesKeys, quotesErrorMessage, quotesApiErrorCode } from './hooks';
export type { QuotesApi, QuotesHooks, QuotesPublicHooks } from './hooks';
export { QUOTES_MESSAGES } from './messages';
export { createQuotesTranslator, defaultQuotesT } from './i18n';
export type { QuotesTranslate } from './i18n';
export { previewTotals as previewQuoteTotals, lineGrossCents as quoteLineGrossCents } from './format';
export type { QuotesOrganProps } from './shared';
export { QuoteStatusChip, QuoteConversionChip } from './QuoteStatusChip';
export type { QuoteStatusChipProps, QuoteConversionChipProps } from './QuoteStatusChip';
export { QuotesTable } from './QuotesTable';
export type { QuotesTableProps } from './QuotesTable';
export { QuoteEditor } from './QuoteEditor';
export type { QuoteEditorProps } from './QuoteEditor';
export { QuoteSendDialog } from './QuoteSendDialog';
export type { QuoteSendDialogProps } from './QuoteSendDialog';
export { QuoteAcceptPage } from './QuoteAcceptPage';
export type { QuoteAcceptPageProps } from './QuoteAcceptPage';
