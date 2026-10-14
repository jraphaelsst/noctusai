import { describe, it, expect } from 'vitest';
import { formatDoc, isMaskedDoc, isValidDoc, maskDocInput, onlyAlnum, splitPhones, isValidEmail } from './format';
import { VALID_CNPJ, VALID_CPF } from './testUtils';

describe('document helpers', () => {
  it('masks progressively per kind', () => {
    expect(maskDocInput('PF', '52998224725')).toBe(VALID_CPF);
    expect(maskDocInput('PF', '529')).toBe('529');
    expect(maskDocInput('PF', '5299')).toBe('529.9');
    expect(maskDocInput('PJ', '11222333000181')).toBe(VALID_CNPJ);
    expect(maskDocInput('PJ', '1122')).toBe('11.22');
    expect(maskDocInput('PF', '5299822472599')).toBe(VALID_CPF); // capped at 11
  });

  it('keeps letters for the alphanumeric CNPJ', () => {
    expect(onlyAlnum('12.abc.345/01de-35')).toBe('12ABC34501DE35');
    expect(maskDocInput('PJ', '12abc34501de35')).toBe('12.ABC.345/01DE-35');
  });

  it('validates check digits per kind; blank is valid (doc is optional)', () => {
    expect(isValidDoc('PF', VALID_CPF)).toBe(true);
    expect(isValidDoc('PF', '529.982.247-26')).toBe(false);
    expect(isValidDoc('PF', VALID_CNPJ)).toBe(false); // a CNPJ on a PF
    expect(isValidDoc('PJ', VALID_CNPJ)).toBe(true);
    expect(isValidDoc('PJ', '11.222.333/0001-82')).toBe(false);
    expect(isValidDoc('PJ', VALID_CPF)).toBe(false);
    expect(isValidDoc('PF', '')).toBe(true);
    expect(isValidDoc('PJ', '  ')).toBe(true);
  });

  it('recognises the server-masked document and never re-masks it', () => {
    expect(isMaskedDoc('***.982.247-**')).toBe(true);
    expect(isMaskedDoc('52998224725')).toBe(false);
    expect(isMaskedDoc(null)).toBe(false);
    expect(formatDoc('PF', '***.982.247-**')).toBe('***.982.247-**');
    expect(formatDoc('PF', '52998224725')).toBe(VALID_CPF);
    expect(formatDoc('PF', null)).toBe('');
  });

  it('splits phones and checks e-mail', () => {
    expect(splitPhones('11 99457-3387, 1132165498;\n 21999990000 ,')).toEqual(['11 99457-3387', '1132165498', '21999990000']);
    expect(isValidEmail('a@b.co')).toBe(true);
    expect(isValidEmail('a@b')).toBe(false);
  });
});
