/**
 * Condensed views over `/coleta` data — what the page actually SHOWS.
 *
 * The sources are organised by setor (30+ per city), but a resident only
 * cares about "which days, day or night". Every city has just 2–4 distinct
 * day patterns, so the page groups by pattern (`agruparPorDias`) and
 * collapses a search hit's comum + seletiva rows into one answer
 * (`agruparResultados`). Labels are plain Portuguese, not source jargon.
 */
import type { Resultado } from './busca';
import { DIA_CURTO, type Dia, type Municipio, type Rota, type TipoColeta } from './tipos';

const SEMANA: Dia[] = ['seg', 'ter', 'qua', 'qui', 'sex', 'sab', 'dom'];
const SEG_A_SAB: Dia[] = ['seg', 'ter', 'qua', 'qui', 'sex', 'sab'];

const DIA_TITULO: Record<Dia, string> = {
  seg: 'Segunda', ter: 'Terça', qua: 'Quarta', qui: 'Quinta', sex: 'Sexta', sab: 'Sábado', dom: 'Domingo',
};

const ordenar = (dias: Dia[]) => [...dias].sort((a, b) => SEMANA.indexOf(a) - SEMANA.indexOf(b));

/** "Seg · Qua · Sex" — or "Seg a Sáb" / "Todos os dias" for the full runs. */
export function diasCurtos(dias: Dia[]): string {
  const d = ordenar(dias);
  if (d.length === 7) return 'Todos os dias';
  if (d.length === 6 && SEG_A_SAB.every((x) => d.includes(x))) return 'Seg a Sáb';
  return d.map((x) => DIA_CURTO[x]).join(' · ');
}

/** "Segunda, quarta e sexta" — or "Segunda a sábado" / "Todos os dias". */
export function diasPorExtenso(dias: Dia[]): string {
  const d = ordenar(dias);
  if (d.length === 7) return 'Todos os dias';
  if (d.length === 6 && SEG_A_SAB.every((x) => d.includes(x))) return 'Segunda a sábado';
  const nomes = d.map((x, i) => (i === 0 ? DIA_TITULO[x] : DIA_TITULO[x].toLowerCase()));
  if (nomes.length <= 1) return nomes.join('');
  return `${nomes.slice(0, -1).join(', ')} e ${nomes[nomes.length - 1]}`;
}

/** The source's period wording, in plain words ("diurno" → "de dia"). */
export function periodoLegivel(periodo?: string): string | undefined {
  if (!periodo) return undefined;
  const p = periodo.toLowerCase();
  if (p.startsWith('diurno')) return p.replace('diurno', 'de dia').replace(/\s*\((.*)\)/, ', $1');
  if (p.startsWith('noturno')) return p.replace('noturno', 'à noite').replace(/\s*\((.*)\)/, ', $1');
  if (p === 'manhã/tarde') return 'manhã e tarde';
  if (p === 'tarde/noite') return 'tarde e noite';
  return periodo;
}

export interface Grupo {
  dias: Dia[];
  /** Set when the source gives no weekdays — shown instead of `dias`. */
  frequencia?: string;
  periodo?: string;
  bairros: string[];
  notas: string[];
}

/** Day shifts sort before night shifts within the same days. */
const turno = (periodo?: string) => (periodo?.includes('noite') ? 1 : 0);

/** One group per distinct (days, period) pattern, bairros de-duplicated in source order. */
export function agruparPorDias(rotas: Rota[], tipo: TipoColeta): Grupo[] {
  const grupos = new Map<string, Grupo>();
  for (const r of rotas) {
    if (r.tipo !== tipo) continue;
    const dias = ordenar(r.dias);
    const periodo = periodoLegivel(r.periodo);
    const chave = `${dias.join()}|${r.frequencia ?? ''}|${periodo ?? ''}`;
    let g = grupos.get(chave);
    if (!g) {
      g = { dias, frequencia: r.frequencia, periodo, bairros: [], notas: [] };
      grupos.set(chave, g);
    }
    for (const b of r.bairros) if (!g.bairros.includes(b)) g.bairros.push(b);
    if (r.nota && !g.notas.includes(r.nota)) g.notas.push(r.nota);
  }
  // Groups with known days first, in weekday order; "days unknown" last.
  return [...grupos.values()].sort((a, b) => {
    if (!a.dias.length || !b.dias.length) return b.dias.length - a.dias.length;
    return SEMANA.indexOf(a.dias[0]) - SEMANA.indexOf(b.dias[0]) || turno(a.periodo) - turno(b.periodo);
  });
}

/** One search answer: a place, with its comum and seletiva lines side by side. */
export interface Local {
  municipio: Municipio;
  nome: string;
  rua?: string;
  comum: Rota[];
  seletiva: Rota[];
}

export function agruparResultados(resultados: Resultado[]): Local[] {
  const locais = new Map<string, Local>();
  for (const r of resultados) {
    const chave = `${r.municipio.slug}|${r.rua ?? ''}|${r.termo}`;
    let l = locais.get(chave);
    if (!l) {
      l = { municipio: r.municipio, nome: r.termo, rua: r.rua, comum: [], seletiva: [] };
      locais.set(chave, l);
    }
    const lista = r.rota.tipo === 'comum' ? l.comum : l.seletiva;
    if (!lista.includes(r.rota)) lista.push(r.rota);
  }
  return [...locais.values()];
}

/** "Seg · Qua · Sex, de dia" for one rota (or its frequency text when days are unknown). */
export function resumoRota(rota: Rota): string {
  const quando = rota.dias.length ? diasCurtos(rota.dias) : rota.frequencia ?? 'dias não informados';
  const periodo = periodoLegivel(rota.periodo);
  return periodo ? `${quando}, ${periodo}` : quando;
}
