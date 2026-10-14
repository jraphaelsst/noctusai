import { describe, expect, it } from 'vitest';
import { formatDate, lineGrossCents, previewTotals } from './format';
import { createQuotesTranslator, defaultQuotesT } from './i18n';
import { QUOTES_MESSAGES } from './messages';
import { QUOTE_CONVERSION_STATUSES, QUOTE_STATUSES } from './types';

describe('lineGrossCents — the server rounding (half-up on exact decimals)', () => {
  it.each([
    ['0.5', 1, 1],
    ['2.5', 3, 8],
    ['1.333', 100, 133],
    ['2', 10000, 20000],
    ['2,5', 1999, 4998],
    ['1.234,5', 100, 123450],
  ])('%s x %i = %i', (qty, price, want) => {
    expect(lineGrossCents(qty, price)).toBe(want);
  });
  it('is null for a quantity the server would refuse', () => {
    expect(lineGrossCents('abc', 1)).toBeNull();
    expect(lineGrossCents('1.2345', 1)).toBeNull();
    expect(lineGrossCents('1', -5)).toBeNull();
  });
  it('is exact where floats are not (0.1 + 0.2 class)', () => {
    expect(lineGrossCents('0.3', 100)).toBe(30);
    expect(lineGrossCents('1.1', 100)).toBe(110);
  });
});

describe('previewTotals', () => {
  it('adds rounded lines and subtracts the general discount', () => {
    const t = previewTotals([{ qty: '1.333', unitPriceCents: 100, discountCents: 0 }, { qty: '3', unitPriceCents: 999, discountCents: 100 }], 50);
    expect(t).toMatchObject({ subtotal: 133 + 2897, discount: 50, total: 133 + 2897 - 50, invalid: false });
    expect(t.lineTotals).toEqual([133, 2897]);
  });
  it('flags a discount above its base instead of showing a negative total', () => {
    expect(previewTotals([{ qty: '1', unitPriceCents: 100, discountCents: 101 }], 0)).toMatchObject({ invalid: true, lineTotals: [null] });
    expect(previewTotals([{ qty: '1', unitPriceCents: 100, discountCents: 0 }], 101).invalid).toBe(true);
    expect(previewTotals([{ qty: 'x', unitPriceCents: NaN, discountCents: 0 }], 0).invalid).toBe(true);
  });
  it('an empty quote is zero', () => {
    expect(previewTotals([], 0)).toMatchObject({ subtotal: 0, total: 0, invalid: false });
  });
});

describe('dates and copy', () => {
  it('date-only values do not shift with the timezone', () => {
    expect(formatDate('2026-10-14')).toBe('14/10/2026');
    expect(formatDate(null)).toBe('—');
  });
  it('every status and conversion state has copy; unknown keys are visible, never blank', () => {
    for (const s of QUOTE_STATUSES) expect(defaultQuotesT(`status.${s}`)).not.toBe(`status.${s}`);
    for (const s of QUOTE_CONVERSION_STATUSES) expect(defaultQuotesT(`conversion.${s}`)).not.toBe(`conversion.${s}`);
    expect(defaultQuotesT('nope.key')).toBe('nope.key');
  });
  it('interpolates and accepts overrides', () => {
    expect(defaultQuotesT('table.version', { n: 3 })).toBe('v3');
    expect(createQuotesTranslator({ 'table.title': 'Propostas' })('table.title')).toBe('Propostas');
    expect(defaultQuotesT('table.version')).toBe('v{n}');
  });
  it('every backend error code the organ can raise has pt-BR copy', () => {
    const codes = ['orcamento_vazio', 'orcamento_bloqueado', 'orcamento_expirado', 'orcamento_encerrado', 'orcamento_substituido', 'transicao_invalida',
      'desconto_invalido', 'cliente_invalido', 'item_invalido', 'linha_invalida', 'validade_invalida', 'consentimento_obrigatorio', 'nome_obrigatorio',
      'motivo_obrigatorio', 'link_invalido', 'link_indisponivel', 'email_indisponivel', 'envio_falhou', 'conversao_indisponivel'];
    for (const c of codes) expect(QUOTES_MESSAGES).toHaveProperty(`error.${c}`);
  });
});
