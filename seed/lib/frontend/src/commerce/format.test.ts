import { describe, it, expect } from 'vitest';
import { centsToInput, formatCents, maskCnpj, maskCpf, maskCpfOrCnpj, parseMoneyToCents, slugify } from './format';
import { isValidCnpj, isValidCpf } from './validation';
import { VALID_CNPJ, VALID_CPF } from './testUtils';

const nbsp = (s: string) => s.replace(/ /g, ' ');

describe('money from cents', () => {
  it('formats integer cents as BRL', () => {
    expect(nbsp(formatCents(123456))).toBe('R$ 1.234,56');
    expect(nbsp(formatCents(5))).toBe('R$ 0,05');
    expect(nbsp(formatCents(0))).toBe('R$ 0,00');
    expect(nbsp(formatCents(null))).toBe('R$ 0,00');
  });

  it('formats other currency/locale', () => {
    expect(nbsp(formatCents(1999, 'USD', 'en'))).toBe('$19.99');
  });

  it('parses typed BRL to cents without float error', () => {
    expect(parseMoneyToCents('12,50')).toBe(1250);
    expect(parseMoneyToCents('R$ 1.234,56')).toBe(123456);
    expect(parseMoneyToCents('12.5')).toBe(1250);
    expect(parseMoneyToCents('1.234')).toBe(123400);
    expect(parseMoneyToCents('0,29')).toBe(29);
    expect(parseMoneyToCents('19.99')).toBe(1999);
    expect(parseMoneyToCents('10')).toBe(1000);
  });

  it('rejects invalid amounts', () => {
    for (const bad of ['', 'abc', '-5', '1,234,5', '12,345', '1..2']) expect(parseMoneyToCents(bad)).toBeNull();
  });

  it('round-trips cents ↔ input', () => {
    for (const c of [1, 99, 100, 1250, 123456]) expect(parseMoneyToCents(centsToInput(c))).toBe(c);
  });
});

describe('masks and validation', () => {
  it('masks CNPJ/CPF progressively', () => {
    expect(maskCnpj('11222333000181')).toBe(VALID_CNPJ);
    expect(maskCpf('52998224725')).toBe(VALID_CPF);
    expect(maskCpfOrCnpj('529982247250')).toBe('52.998.224/7250');
    expect(maskCnpj('112')).toBe('11.2');
  });
  it('validates check digits', () => {
    expect(isValidCnpj(VALID_CNPJ)).toBe(true);
    expect(isValidCnpj('11.222.333/0001-82')).toBe(false);
    expect(isValidCnpj('11.111.111/1111-11')).toBe(false);
    expect(isValidCpf(VALID_CPF)).toBe(true);
    expect(isValidCpf('529.982.247-26')).toBe(false);
  });
  it('slugifies', () => {
    expect(slugify('Curso de Programação — 2 ed.')).toBe('curso-de-programacao-2-ed');
  });
});
