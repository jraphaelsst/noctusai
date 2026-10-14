/** Props every quotes organ takes: the hooks factory output + optional copy seams. */
import type { QuotesHooks } from './hooks';
import type { QuotesTranslate } from './i18n';

export interface QuotesOrganProps {
  hooks: QuotesHooks;
  /** Translator override (defaults to the shipped pt-BR table). */
  t?: QuotesTranslate;
  locale?: string;
}
