import { describe, it, expect } from 'vitest';
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { MESSAGES } from './messages';
import { createTranslator, resolveLocale } from './i18n';
import { ORDER_STATUSES, PAYMENT_METHODS, PRODUCT_TYPES, FULFILLMENT_TYPES, PRODUCT_STATUSES, TAX_REGIMES, TAX_TREATMENTS, COUPON_KINDS, CONSENT_KINDS, FIELD_SOURCES, ORDER_EVENT_SOURCES } from './types';
import { PRODUCT_TYPE_SLOTS } from './ProductEditor';
import { BRAND_TOKEN_KEYS } from './StoreProfileForm';

describe('commerce i18n', () => {
  it('pt-BR and en carry exactly the same keys', () => {
    expect(Object.keys(MESSAGES.en).sort()).toEqual(Object.keys(MESSAGES['pt-BR']).sort());
  });

  it('every literal t("…") key used by a component exists', () => {
    const dir = __dirname;
    const keys = new Set<string>();
    for (const f of readdirSync(dir).filter((x) => /\.tsx?$/.test(x) && !x.includes('.test.') && x !== 'messages.ts')) {
      for (const m of readFileSync(join(dir, f), 'utf8').matchAll(/\bt\('([a-z_]+\.[a-z_0-9]+)'/g)) keys.add(m[1]);
    }
    const missing = [...keys].filter((k) => !(k in MESSAGES['pt-BR']));
    expect(missing).toEqual([]);
  });

  it('every dynamic key family is fully covered', () => {
    const expected: string[] = [
      ...ORDER_STATUSES.map((s) => `order_status.${s}`),
      ...PAYMENT_METHODS.map((s) => `payment.${s}`),
      ...PRODUCT_TYPES.map((s) => `product_type.${s}`),
      ...FULFILLMENT_TYPES.map((s) => `fulfillment.${s}`),
      ...PRODUCT_STATUSES.map((s) => `product_status.${s}`),
      ...TAX_REGIMES.map((s) => `tax_regime.${s}`),
      ...TAX_TREATMENTS.map((s) => `tax_treatment.${s}`),
      ...COUPON_KINDS.map((s) => `coupon_kind.${s}`),
      ...CONSENT_KINDS.map((s) => `consent.${s}`),
      ...FIELD_SOURCES.map((s) => `field_source.${s}`),
      ...ORDER_EVENT_SOURCES.map((s) => `event_source.${s}`),
      ...BRAND_TOKEN_KEYS.map((s) => `brand.${s}`),
      ...Object.values(PRODUCT_TYPE_SLOTS).flat().map((s) => `slot.${s.key}`),
    ];
    expect(expected.filter((k) => !(k in MESSAGES['pt-BR']))).toEqual([]);
  });

  it('resolves locale, interpolates, falls back to pt-BR then to the key', () => {
    expect(resolveLocale('en-US')).toBe('en');
    expect(resolveLocale('fr')).toBe('pt-BR');
    expect(createTranslator('en')('common.save')).toBe('Save');
    expect(createTranslator('pt-BR')('checkout.pay', { total: 'R$ 10,00' })).toBe('Pagar R$ 10,00');
    expect(createTranslator('en')('no.such.key')).toBe('no.such.key');
  });
});
