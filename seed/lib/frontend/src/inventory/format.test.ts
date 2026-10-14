import { describe, expect, it } from 'vitest';
import { formatQty, parseQty } from './format';
import { createInventoryTranslator } from './i18n';
import { INVENTORY_MESSAGES } from './messages';

describe('quantities', () => {
  it('formats up to 3 decimals without trailing zeros (pt-BR)', () => {
    expect(formatQty(2.5)).toBe('2,5');
    expect(formatQty(1234)).toBe('1.234');
    expect(formatQty(0.125)).toBe('0,125');
    expect(formatQty(null)).toBe('0');
  });
  it('parses what a person types into the canonical wire string', () => {
    expect(parseQty('2,5')).toBe('2.5');
    expect(parseQty('1.234,5')).toBe('1234.5');
    expect(parseQty('12')).toBe('12');
    expect(parseQty('0,125')).toBe('0.125');
    expect(parseQty('1.234.567')).toBe('1234567');
  });
  it('rejects negatives, junk and more than 3 decimals', () => {
    for (const bad of ['', '-1', 'abc', '1,2345', '1,2,3']) expect(parseQty(bad)).toBeNull();
  });
});

describe('i18n', () => {
  const t = createInventoryTranslator();
  it('interpolates and falls back to the key', () => {
    expect(t('common.page', { page: 2, pages: 5 })).toBe('Página 2 de 5');
    expect(t('nope.key')).toBe('nope.key');
  });
  it('every move kind and every backend error code has copy', () => {
    for (const k of ['in', 'out', 'adjust', 'transfer_in', 'transfer_out', 'reserve', 'release', 'commit']) {
      expect(INVENTORY_MESSAGES).toHaveProperty(`kind.${k}`);
    }
    for (const c of ['estoque_insuficiente', 'abaixo_reservado', 'deposito_invalido', 'deposito_duplicado', 'deposito_com_estoque', 'item_invalido']) {
      expect(INVENTORY_MESSAGES).toHaveProperty(`error.${c}`);
    }
  });
});
