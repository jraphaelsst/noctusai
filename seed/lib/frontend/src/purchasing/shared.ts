/** Props every purchasing organ takes: the hooks factory output + optional copy seams. */
import type { PurchasingHooks } from './hooks';
import type { PurchasingTranslate } from './i18n';

export interface PurchasingOrganProps {
  hooks: PurchasingHooks;
  /** Translator override (defaults to the shipped pt-BR table). */
  t?: PurchasingTranslate;
  locale?: string;
}
