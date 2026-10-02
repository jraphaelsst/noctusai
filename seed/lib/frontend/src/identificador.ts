/**
 * Canonical identifier formats (CPF, CNPJ, RG, CEP, matrícula, ...) — the
 * frontend half.
 *
 * Mirrors `noctusai_lib.primitives.identificador` case for case. OWNER RULE
 * (2026-10-01): the canonical form of every document number / id / protocol
 * is its PUNCTUATED form; an unpunctuated value is CHECKED against the
 * punctuated shape of its type (and, where the type has a check digit, the
 * digit decides). Python, this file and the plpgsql twin all assert the SAME
 * case table: `seed/lib/shared/identificador.cases.json`.
 *
 * NEVER invents data: a SP RG read without its check digit is COMPLETED
 * (arithmetic), everything else unparseable is `canonico: null` and the value
 * stays VISIBLE (`formatIdentificador` returns it as stored).
 *
 * `formatIdentificador` is THE display seam (replaces ad-hoc `maskCpf` /
 * `documentoBr` helpers); `chaveBuscaIdentificador` is the search key —
 * normalize the NEEDLE too (and floor it at `CHAVE_BUSCA_MIN`), or the UI
 * shows what search cannot find.
 */

export const CHAVE_BUSCA_MIN = 4;

export interface Leitura {
  canonico: string | null;
  cabe: boolean;
  dvOk: boolean | null;
  dvCompletado: boolean;
  /** stable code: ok · dv_completado · dv_invalido · tamanho · ... */
  motivo: string;
  /** another type this value is a VALID instance of (CPF sitting in an RG field) */
  tipoDetectado: string | null;
}

export interface IdentificadorOpts {
  municipio?: string | null;
  ibge?: string | null;
  uf?: string | null;
}

const SEP = /[.\-/\s]/g;
const UFS = new Set(
  'AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO'.split(' '),
);

const ok = (canon: string, motivo = 'ok', dvOk: boolean | null = null, completado = false): Leitura => ({
  canonico: canon, cabe: true, dvOk, dvCompletado: completado, motivo, tipoDetectado: null,
});
const no = (motivo: string, dvOk: boolean | null = null): Leitura => ({
  canonico: null, cabe: false, dvOk, dvCompletado: false, motivo, tipoDetectado: null,
});

function texto(valor: unknown): string {
  if (valor === null || valor === undefined) return '';
  return String(valor).trim();
}

function deaccentUpper(s: string): string {
  return s.normalize('NFKD').replace(/[̀-ͯ]/g, '').toUpperCase();
}
const alnum = (s: string): string => deaccentUpper(s).replace(/[^0-9A-Z]/g, '');
function numerico(s: string): string | null {
  const d = s.replace(SEP, '');
  return /^[0-9]+$/.test(d) ? d : null;
}

// ─── check-digit algorithms ─────────────────────────────────────────────────

export function cpfDvValido(d: string): boolean {
  if (!/^[0-9]{11}$/.test(d) || d === d[0].repeat(11)) return false;
  for (const t of [9, 10]) {
    let soma = 0;
    for (let i = 0; i < t; i++) soma += Number(d[i]) * (t + 1 - i);
    const resto = (soma * 10) % 11;
    if ((resto === 10 ? 0 : resto) !== Number(d[t])) return false;
  }
  return true;
}

const P1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
const P2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
function cnpjDigito(base: string, pesos: number[]): number {
  let soma = 0;
  for (let i = 0; i < base.length; i++) soma += (base.charCodeAt(i) - 48) * pesos[i];
  const r = soma % 11;
  return r < 2 ? 0 : 11 - r;
}
export function cnpjDvValido(a: string): boolean {
  if (!/^[0-9A-Z]{12}[0-9]{2}$/.test(a)) return false;
  if (/^[0-9]+$/.test(a) && a === a[0].repeat(14)) return false;
  const dv1 = cnpjDigito(a.slice(0, 12), P1);
  const dv2 = cnpjDigito(a.slice(0, 12) + String(dv1), P2);
  return a.slice(12) === `${dv1}${dv2}`;
}

export function rgSpDv(d8: string): string {
  let soma = 0;
  for (let i = 0; i < 8; i++) soma += Number(d8[i]) * (i + 2);
  const dv = 11 - (soma % 11);
  return dv === 10 ? 'X' : dv === 11 ? '0' : String(dv);
}

function cnhDvOk(d: string): boolean {
  if (d === d[0].repeat(11)) return false;
  let v = 0;
  for (let i = 0; i < 9; i++) v += Number(d[i]) * (9 - i);
  let dsc = 0;
  let dv1 = v % 11;
  if (dv1 >= 10) { dv1 = 0; dsc = 2; }
  v = 0;
  for (let i = 0; i < 9; i++) v += Number(d[i]) * (1 + i);
  let dv2 = (v % 11) - dsc;
  if (dv2 < 0) dv2 += 11;
  if (dv2 >= 10) dv2 = 0;
  return d.slice(9) === `${dv1}${dv2}`;
}

function tituloDv(seq: string, uf: number, pesos: number[]): number {
  let soma = 0;
  for (let i = 0; i < pesos.length; i++) soma += Number(seq[i]) * pesos[i];
  const r = soma % 11;
  if (r === 10) return 0;
  if (r === 0 && (uf === 1 || uf === 2)) return 1;
  return r;
}
function tituloDvOk(d: string): boolean {
  const uf = Number(d.slice(8, 10));
  if (uf < 1 || uf > 28) return false;
  const dv1 = tituloDv(d.slice(0, 8), uf, [2, 3, 4, 5, 6, 7, 8, 9]);
  const dv2 = tituloDv(d.slice(8, 10) + String(dv1), uf, [7, 8, 9]);
  return d.slice(10) === `${dv1}${dv2}`;
}

function nisDvOk(d: string): boolean {
  if (d === d[0].repeat(11)) return false;
  const pesos = [3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
  let soma = 0;
  for (let i = 0; i < 10; i++) soma += Number(d[i]) * pesos[i];
  const dv = 11 - (soma % 11);
  return d[10] === String(dv >= 10 ? 0 : dv);
}

// ─── per-type readers ───────────────────────────────────────────────────────

type Reader = (s: string, o: IdentificadorOpts) => Leitura;

const lerCpf: Reader = (s) => {
  const d = numerico(s);
  if (d === null) return no('caracteres_invalidos');
  if (d.length !== 11) return no('tamanho');
  if (!cpfDvValido(d)) return no('dv_invalido', false);
  return ok(`${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6, 9)}-${d.slice(9, 11)}`, 'ok', true);
};

const lerCnpj: Reader = (s) => {
  const a = deaccentUpper(s).replace(SEP, '');
  if (!/^[0-9A-Z]+$/.test(a)) return no('caracteres_invalidos');
  if (!/^[0-9A-Z]{12}[0-9]{2}$/.test(a)) return no('tamanho');
  if (!cnpjDvValido(a)) return no('dv_invalido', false);
  return ok(`${a.slice(0, 2)}.${a.slice(2, 5)}.${a.slice(5, 8)}/${a.slice(8, 12)}-${a.slice(12)}`, 'ok', true);
};

const RG_UFS_CONHECIDAS = new Set(['SP']);
const lerRg: Reader = (s, o) => {
  const a = deaccentUpper(s).replace(SEP, '');
  if (o.uf && !RG_UFS_CONHECIDAS.has(o.uf.toUpperCase())) return no('rg_uf_sem_mascara');
  if (/^[0-9]{8}$/.test(a)) {
    return ok(`${a.slice(0, 2)}.${a.slice(2, 5)}.${a.slice(5, 8)}-${rgSpDv(a)}`, 'dv_completado', null, true);
  }
  if (/^[0-9]{8}[0-9X]$/.test(a)) {
    if (rgSpDv(a.slice(0, 8)) !== a[8]) return no('dv_invalido', false);
    return ok(`${a.slice(0, 2)}.${a.slice(2, 5)}.${a.slice(5, 8)}-${a[8]}`, 'ok', true);
  }
  return no('rg_formato_desconhecido');
};

const lerCnh: Reader = (s) => {
  const d = numerico(s);
  if (d === null) return no('caracteres_invalidos');
  if (d.length !== 11) return no('tamanho');
  return cnhDvOk(d) ? ok(d, 'ok', true) : no('dv_invalido', false);
};

const lerTitulo: Reader = (s) => {
  const d = numerico(s);
  if (d === null) return no('caracteres_invalidos');
  if (d.length !== 12) return no('tamanho');
  if (!tituloDvOk(d)) return no('dv_invalido', false);
  return ok(`${d.slice(0, 4)} ${d.slice(4, 8)} ${d.slice(8)}`, 'ok', true);
};

const lerNis: Reader = (s) => {
  const d = numerico(s);
  if (d === null) return no('caracteres_invalidos');
  if (d.length !== 11) return no('tamanho');
  if (!nisDvOk(d)) return no('dv_invalido', false);
  return ok(`${d.slice(0, 3)}.${d.slice(3, 8)}.${d.slice(8, 10)}-${d[10]}`, 'ok', true);
};

const lerCep: Reader = (s) => {
  const d = numerico(s);
  if (d === null) return no('caracteres_invalidos');
  if (d.length !== 8) return no('tamanho'); // 7 digits lost a leading zero: never guessed
  return ok(`${d.slice(0, 5)}-${d.slice(5)}`);
};

const lerCns: Reader = (s) => {
  const d = numerico(s);
  if (d === null) return no('caracteres_invalidos');
  if (d.length !== 6) return no('tamanho');
  return ok(`${d.slice(0, 5)}-${d[5]}`); // DV algorithm not published: dvOk stays null
};

const lerMatricula: Reader = (s) => {
  const d = s.replace(/[.\s]/g, '');
  if (!/^[0-9]+$/.test(d)) return no('caracteres_invalidos');
  if (d.length > 9) return no('tamanho');
  const n = Number(d);
  if (n === 0) return no('zero');
  return ok(String(n).replace(/\B(?=(\d{3})+$)/g, '.'));
};

const IBGE_POR_MUNICIPIO: Record<string, string> = { COTIA: '3513009' };
const PERFIS_IM: Record<string, number[]> = { '3513009': [5, 2, 2, 4, 2, 3] };

function perfilIm(o: IdentificadorOpts): number[] | null {
  let ibge = o.ibge || null;
  if (!ibge && o.municipio) {
    const nome = deaccentUpper(o.municipio).trim().replace(/\s*[-/,]\s*[A-Z]{2}$/, '').trim();
    ibge = IBGE_POR_MUNICIPIO[nome] ?? null;
  }
  return (ibge && PERFIS_IM[ibge]) || null;
}

function mascaraIm(d: string, grupos: number[]): string {
  const partes: string[] = [];
  let i = 0;
  for (const g of grupos) { partes.push(d.slice(i, i + g)); i += g; }
  const out = partes.join('.');
  return d.length > i ? `${out}-${d.slice(i)}` : out;
}

const lerIm: Reader = (s, o) => {
  const d = numerico(s);
  if (d === null) return no('caracteres_invalidos');
  const grupos = perfilIm(o);
  if (!grupos) return no('municipio_sem_perfil');
  const base = grupos.reduce((a, b) => a + b, 0);
  if (d.length !== base && d.length !== base + 1) return no('digitos_incompativeis');
  return ok(mascaraIm(d, grupos));
};

const ORGAOS_COM_UF = new Set('SSP DETRAN IFP SJS SDS SESP SEJUSP PC PM CBM DIC'.split(' '));
const ORGAOS_SEM_UF = new Set('DPF DPMAF MD MAER MEX MAR'.split(' '));

function parseOrgao(s: string, o: IdentificadorOpts): [string, string | null, string] {
  const up = deaccentUpper(s).replace(/\s+/g, ' ').trim();
  const tok = up.split(/[\s./\-,]+/).filter(Boolean);
  if (tok.length === 0) return [up, null, 'vazio'];
  if (tok[0] === 'IIRGD' && tok.length <= 2) return ['SSP', 'SP', 'ok'];
  const hint = o.uf && UFS.has(o.uf.toUpperCase()) ? o.uf.toUpperCase() : null;
  if (ORGAOS_COM_UF.has(tok[0]) && tok.length <= 2) {
    if (tok.length === 2 && UFS.has(tok[1])) return [tok[0], tok[1], 'ok'];
    if (tok.length === 1) return hint ? [tok[0], hint, 'ok'] : [tok[0], null, 'sem_uf'];
  }
  if (ORGAOS_SEM_UF.has(tok[0]) && tok.length === 1) return [tok[0], null, 'ok'];
  return [up, null, 'desconhecido_mantido'];
}

const lerOrgao: Reader = (s, o) => {
  const [org, uf, motivo] = parseOrgao(s, o);
  if (motivo === 'vazio') return no('vazio');
  return ok(uf ? `${org}/${uf}` : org, motivo);
};

const lerCertidaoReceita: Reader = (s) => {
  const a = deaccentUpper(s).replace(SEP, '');
  if (!/^[0-9A-F]{16}$/.test(a)) return no(/^[0-9A-Z]+$/.test(a) ? 'tamanho' : 'caracteres_invalidos');
  return ok(a.match(/.{4}/g)!.join('.'));
};

// Protocol numbers have no punctuated shape: canonical IS the digit run.
const lerCenprot: Reader = (s) => {
  const d = numerico(s);
  return d === null ? no('caracteres_invalidos') : ok(d);
};

const REGISTRO: Record<string, Reader> = {
  cpf: lerCpf,
  cin: lerCpf, // the CIN number IS the CPF number
  cnpj: lerCnpj,
  rg: lerRg,
  cnh: lerCnh,
  titulo_eleitor: lerTitulo,
  nis_pis: lerNis,
  cep: lerCep,
  cns_cartorio: lerCns,
  matricula_imovel: lerMatricula,
  inscricao_municipal: lerIm,
  orgao_expedidor: lerOrgao,
  certidao_controle_receita: lerCertidaoReceita,
  protocolo_cenprot: lerCenprot,
};
const ALIASES: Record<string, string[]> = { cin: ['cpf'], cpf: ['cin'] };
const DETECTAVEIS_DV = ['cpf', 'cnpj', 'cnh', 'nis_pis', 'titulo_eleitor'];

export const tiposIdentificador = (): string[] => Object.keys(REGISTRO);

function detectar(s: string): string[] {
  const achados: string[] = [];
  for (const t of DETECTAVEIS_DV) {
    const r = REGISTRO[t](s, {});
    if (r.cabe && r.dvOk) achados.push(t);
  }
  if (/^[0-9]{5}-[0-9]{3}$/.test(s)) achados.push('cep');
  if (/^[0-9]{1,2}\.[0-9]{3}\.[0-9]{3}-[0-9X]$/.test(s.toUpperCase())) {
    const r = lerRg(s, {});
    if (r.cabe && r.dvOk) achados.push('rg');
  }
  return achados;
}

/** Types this value is a VALID instance of. `297.556.088-50` -> `['cpf', ...]`. */
export function detectarTipoIdentificador(valor: unknown): string[] {
  const s = texto(valor);
  return s ? detectar(s) : [];
}

function leitor(tipo: string): Reader {
  const r = REGISTRO[tipo];
  if (!r) throw new Error(`tipo de identificador desconhecido: ${tipo}`);
  return r;
}

export function lerIdentificador(tipo: string, valor: unknown, opts: IdentificadorOpts = {}): Leitura {
  const rd = leitor(tipo);
  const s = texto(valor);
  if (!s) return no('vazio');
  let r = rd(s, opts);
  if (!r.cabe && r.dvOk === null) {
    const excl = new Set([tipo, ...(ALIASES[tipo] ?? [])]);
    const det = detectar(s).filter((t) => !excl.has(t));
    if (det.length) r = { ...r, tipoDetectado: det[0] };
  }
  return r;
}

export const canonicoIdentificador = (tipo: string, valor: unknown, opts: IdentificadorOpts = {}): string | null =>
  lerIdentificador(tipo, valor, opts).canonico;

/** THE display seam: canonical form when it fits, else the value as stored. */
export function formatIdentificador(tipo: string, valor: unknown, opts: IdentificadorOpts = {}): string {
  return canonicoIdentificador(tipo, valor, opts) ?? texto(valor);
}

/** Search key: canonical alnum when the value parses, RAW alnum otherwise. */
export function chaveBuscaIdentificador(tipo: string, valor: unknown, opts: IdentificadorOpts = {}): string | null {
  const c = canonicoIdentificador(tipo, valor, opts);
  return alnum(c ?? texto(valor)) || null;
}

function imPartes(r: Leitura): [string, string | null] {
  const c = r.canonico ?? '';
  return c.length > 23 ? [c.slice(0, 23), c.slice(24) || null] : [c, null];
}

/** true: same identifier · false: different · null: undecidable. */
export function equivalentesIdentificador(
  tipo: string, a: unknown, b: unknown, opts: IdentificadorOpts = {},
): boolean | null {
  const la = lerIdentificador(tipo, a, opts);
  const lb = lerIdentificador(tipo, b, opts);
  const ra = alnum(texto(a));
  const rb = alnum(texto(b));
  if (!ra || !rb) return null;
  if (tipo === 'orgao_expedidor') {
    const [oa, ua] = parseOrgao(texto(a), { uf: opts.uf });
    const [ob, ub] = parseOrgao(texto(b), { uf: opts.uf });
    if (oa !== ob) return false;
    if (ua === null || ub === null) return ORGAOS_COM_UF.has(oa) ? null : true;
    return ua === ub;
  }
  if (tipo === 'inscricao_municipal') {
    if (la.canonico && lb.canonico) {
      const [ba, da] = imPartes(la);
      const [bb, db] = imPartes(lb);
      if (ba !== bb) return false;
      return da && db && da !== db ? false : true;
    }
    if (la.motivo === 'municipio_sem_perfil' && lb.motivo === 'municipio_sem_perfil') {
      const da = numerico(texto(a)) ?? '';
      const db = numerico(texto(b)) ?? '';
      if (da && da === db) return true;
      if (da && db && (da.startsWith(db) || db.startsWith(da))) return null;
      return da && db ? false : null;
    }
  }
  if (la.canonico && lb.canonico) return la.canonico === lb.canonico;
  if (ra === rb) return true;
  if ((la.canonico && lb.dvOk === false) || (lb.canonico && la.dvOk === false)) return false;
  return null;
}

const CNS_RE = /\bC\.?\s?N\.?\s?S\.?\s*[:\-.Nº°O]*\s*([0-9]{2}\.?[0-9]{3}\s?-?\s?[0-9])(?![0-9])/g;

/** The cartório CNS (`11991-7`) in free text; two DIFFERENT CNS = absence. */
export function extrairCns(t: unknown): string | null {
  const achados = new Set<string>();
  for (const m of deaccentUpper(texto(t)).matchAll(CNS_RE)) {
    const c = lerCns(m[1], {}).canonico;
    if (c) achados.add(c);
  }
  return achados.size === 1 ? [...achados][0] : null;
}
