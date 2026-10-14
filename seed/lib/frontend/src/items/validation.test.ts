import { describe, it, expect } from 'vitest';
import { gtinCheckDigit, normalizeCest, normalizeCfop, normalizeGtin, normalizeNcm, normalizeOrigem, normalizeSku } from './validation';
import { EAN13 } from './testUtils';

describe('fiscal validators (mirror of backend validators.py)', () => {
  it('NCM: 8 digits, printed form accepted, chapter 01..97', () => {
    expect(normalizeNcm('8471.30.19')).toBe('84713019');
    expect(normalizeNcm('')).toBeNull();
    for (const bad of ['8471301', '00012100', '98123456', 'abc']) expect(normalizeNcm(bad)).toBeUndefined();
  });
  it('CEST: 7 digits', () => {
    expect(normalizeCest('01.001.00')).toBe('0100100');
    expect(normalizeCest('010010')).toBeUndefined();
  });
  it('CFOP: 4 digits, first digit 1/2/3/5/6/7', () => {
    expect(normalizeCfop('5.102')).toBe('5102');
    for (const bad of ['4102', '0102', '8102', '510']) expect(normalizeCfop(bad)).toBeUndefined();
  });
  it('origem: 0..8', () => {
    expect(normalizeOrigem('0')).toBe(0);
    expect(normalizeOrigem(8)).toBe(8);
    expect(normalizeOrigem('')).toBeNull();
    for (const bad of ['9', '-1', 'x', '1.5']) expect(normalizeOrigem(bad)).toBeUndefined();
  });
  it('GTIN: GS1 mod-10 check digit and lengths 8/12/13/14', () => {
    expect(gtinCheckDigit('789100010010')).toBe(3);
    expect(gtinCheckDigit('03600029145')).toBe(2);
    expect(normalizeGtin(EAN13)).toBe(EAN13);
    expect(normalizeGtin('036000291452')).toBe('036000291452');
    expect(normalizeGtin('40170725')).toBe('40170725');
    for (const bad of ['7891000100104', '123456789', 'abc']) expect(normalizeGtin(bad)).toBeUndefined();
  });
  it('SKU is upper-cased; bad shapes refused', () => {
    expect(normalizeSku('ab-1')).toBe('AB-1');
    for (const bad of ['', 'a b', '-A', 'A'.repeat(65)]) expect(normalizeSku(bad)).toBeUndefined();
  });
});
