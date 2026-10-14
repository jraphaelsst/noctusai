import { describe, it, expect } from 'vitest';
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { MESSAGES } from './messages';
import { t } from './i18n';
import { PARTIES_ERROR_CODES, PARTY_KINDS, PARTY_ROLES, ADDRESS_FIELDS } from './types';

describe('parties copy', () => {
  it('every literal t("…") key used by a component exists', () => {
    const keys = new Set<string>();
    for (const f of readdirSync(__dirname).filter((x) => /\.tsx?$/.test(x) && !x.includes('.test.') && x !== 'messages.ts')) {
      for (const m of readFileSync(join(__dirname, f), 'utf8').matchAll(/\bt\('([a-z_]+\.[a-zA-Z_0-9]+)'/g)) keys.add(m[1]);
    }
    expect([...keys].filter((k) => !(k in MESSAGES))).toEqual([]);
  });

  it('every dynamic key family is fully covered', () => {
    const expected = [
      ...PARTY_KINDS.map((k) => `kind.${k}`),
      ...PARTY_KINDS.map((k) => `error.doc_invalid_${k}`),
      ...PARTY_ROLES.map((r) => `role.${r}`),
      ...ADDRESS_FIELDS.map((f) => `address.${f}`),
      // every backend error code the editor can show has a pt-BR message
      ...['documento_invalido', 'documento_duplicado', 'parceiro_em_uso', 'email_invalido', 'telefone_invalido', 'papel_invalido'].map((c) => `error.${c}`),
    ];
    expect(expected.filter((k) => !(k in MESSAGES))).toEqual([]);
    expect(Object.values(PARTIES_ERROR_CODES)).toContain('parceiro_em_uso');
  });

  it('interpolates variables and shows the key for an unknown message', () => {
    expect(t('csv.result_created', { n: 3 })).toBe('3 cadastros criados');
    expect(t('nope.missing')).toBe('nope.missing');
  });
});
