/**
 * Frontend half of the canonical identifier contract: asserts the SAME case
 * table as `seed/lib/backend/tests/test_identificador.py` and the plpgsql
 * parity block (`seed/lib/shared/identificador.cases.json`).
 */
// Node types for `node:fs` / `__dirname`: every product's `tsc` includes this file
// through the `@noctusai/lib` path and its tsconfig carries only `vite/client`.
/// <reference types="node" />
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

import {
  canonicoIdentificador,
  chaveBuscaIdentificador,
  detectarTipoIdentificador,
  equivalentesIdentificador,
  extrairCns,
  formatIdentificador,
  lerIdentificador,
} from './identificador';

interface Opts { municipio?: string; ibge?: string; uf?: string }
const CASES = JSON.parse(
  readFileSync(resolve(__dirname, '../../shared/identificador.cases.json'), 'utf-8'),
) as {
  ler: Array<{ tipo: string; entrada: string; canonico: string | null; cabe: boolean; dv_ok: boolean | null; dv_completado: boolean; motivo: string; tipo_detectado: string | null; opts?: Opts }>;
  equivalentes: Array<{ tipo: string; a: string; b: string; esperado: boolean | null; opts?: Opts }>;
  chave_busca: Array<{ tipo: string; entrada: string; esperado: string | null; opts?: Opts }>;
  extrair_cns: Array<{ texto: string; esperado: string | null }>;
  detectar_tipo: Array<{ entrada: string; esperado: string[] }>;
};

describe('lerIdentificador — shared case table', () => {
  it.each(CASES.ler.map((c) => [`${c.tipo}:${JSON.stringify(c.entrada)}:${JSON.stringify(c.opts ?? {})}`, c] as const))(
    '%s',
    (_n, c) => {
      const r = lerIdentificador(c.tipo, c.entrada, c.opts);
      expect([r.canonico, r.cabe, r.dvOk, r.dvCompletado, r.motivo, r.tipoDetectado]).toEqual([
        c.canonico, c.cabe, c.dv_ok, c.dv_completado, c.motivo, c.tipo_detectado,
      ]);
      expect(canonicoIdentificador(c.tipo, c.entrada, c.opts)).toBe(c.canonico);
    },
  );
});

describe('equivalentesIdentificador — shared case table (symmetric)', () => {
  it.each(CASES.equivalentes.map((c) => [`${c.tipo}:${c.a}~${c.b}`, c] as const))('%s', (_n, c) => {
    expect(equivalentesIdentificador(c.tipo, c.a, c.b, c.opts)).toBe(c.esperado);
    expect(equivalentesIdentificador(c.tipo, c.b, c.a, c.opts)).toBe(c.esperado);
  });
});

describe('chaveBuscaIdentificador — shared case table', () => {
  it.each(CASES.chave_busca.map((c) => [`${c.tipo}:${c.entrada}`, c] as const))('%s', (_n, c) => {
    expect(chaveBuscaIdentificador(c.tipo, c.entrada, c.opts)).toBe(c.esperado);
  });
});

describe('extrairCns / detectarTipoIdentificador — shared case table', () => {
  it.each(CASES.extrair_cns.map((c) => [c.texto.slice(0, 30), c] as const))('cns %s', (_n, c) => {
    expect(extrairCns(c.texto)).toBe(c.esperado);
  });
  it.each(CASES.detectar_tipo.map((c) => [JSON.stringify(c.entrada), c] as const))('detect %s', (_n, c) => {
    expect(detectarTipoIdentificador(c.entrada)).toEqual(c.esperado);
  });
});

describe('formatIdentificador — the display seam', () => {
  it('canonical when it fits, raw (visible) when it does not', () => {
    expect(formatIdentificador('rg', '30128742')).toBe('30.128.742-9');
    expect(formatIdentificador('rg', ' 15.668.564-3 ')).toBe('15.668.564-3');
    expect(formatIdentificador('rg', null)).toBe('');
  });
  it('unknown tipo is loud', () => {
    expect(() => lerIdentificador('passaporte', 'x')).toThrow();
  });
});
