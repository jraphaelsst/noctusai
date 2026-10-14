import { describe, it, expect } from 'vitest';
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { MESSAGES } from './messages';
import { t } from './i18n';
import {
  CONTRACT_BILLING_MODELS, CONTRACT_FREQUENCIES, CONTRACT_READJUSTMENT_INDEXES, CONTRACT_SIGNATURE_STATUSES, CONTRACT_STATUSES,
  CONTRACT_VERSION_KINDS, CONTRACTS_ERROR_CODES,
} from './types';

describe('contracts copy', () => {
  it('every literal t("…") key used by a component exists', () => {
    const keys = new Set<string>();
    for (const f of readdirSync(__dirname).filter((x) => /\.tsx?$/.test(x) && !x.includes('.test.') && x !== 'messages.ts')) {
      for (const m of readFileSync(join(__dirname, f), 'utf8').matchAll(/\bt\('([a-z_]+\.[a-zA-Z_0-9]+)'/g)) keys.add(m[1]);
    }
    expect([...keys].filter((k) => !(k in MESSAGES))).toEqual([]);
  });

  it('every dynamic key family is fully covered (enums mirror the backend; every error code has pt-BR copy)', () => {
    const expected = [
      ...CONTRACT_STATUSES.map((s) => `status.${s}`),
      ...CONTRACT_BILLING_MODELS.map((m) => `model.${m}`),
      ...CONTRACT_FREQUENCIES.map((f) => `frequency.${f}`),
      ...CONTRACT_READJUSTMENT_INDEXES.map((i) => `index.${i}`),
      ...CONTRACT_SIGNATURE_STATUSES.map((s) => `signature.${s}`),
      ...CONTRACT_VERSION_KINDS.map((k) => `kind.${k}`),
      ...CONTRACTS_ERROR_CODES.map((c) => `error.${c}`),
      ...['amount_cents', 'end_date', 'notice_days', 'percent_bp', 'lines', 'penalty_applied_cents'].map((f) => `field.${f}`),
    ];
    expect(expected.filter((k) => !(k in MESSAGES))).toEqual([]);
  });

  it('enums mirror the backend wire values', () => {
    expect(CONTRACT_STATUSES).toEqual(['draft', 'active', 'suspended', 'terminated', 'expired']);
    expect(CONTRACT_BILLING_MODELS).toEqual(['one_time', 'installments', 'recurring', 'retainer']);
    expect(CONTRACT_READJUSTMENT_INDEXES).toEqual(['none', 'IPCA', 'IGPM', 'INPC', 'fixed']);
  });

  it('interpolates variables and shows the key for an unknown message', () => {
    expect(t('timeline.version', { n: 3 })).toBe('Versão 3');
    expect(t('nope.missing')).toBe('nope.missing');
  });
});
