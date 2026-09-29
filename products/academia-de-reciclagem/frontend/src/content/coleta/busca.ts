/**
 * Pure lookups behind `/coleta`'s search box — "digite seu bairro, condomínio
 * ou rua". Accent- and case-insensitive, because nobody types "Sáb" or
 * "Carapicuíba" the way a prefeitura PDF spells them.
 */
import { DIAS, type Dia, type Municipio, type Rota } from './tipos';

export function normalizar(texto: string): string {
  return texto
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .trim();
}

export interface Resultado {
  municipio: Municipio;
  rota: Rota;
  /** The bairro (or street, when matched via `ruas`) that matched the query. */
  termo: string;
  /** Set when the match came from the street index. */
  rua?: string;
}

/** Minimum query length — a 1–2 letter query matches half the region. */
export const MIN_BUSCA = 3;

export function buscar(municipios: Municipio[], consulta: string, limite = 40): Resultado[] {
  const q = normalizar(consulta);
  if (q.length < MIN_BUSCA) return [];

  const resultados: Resultado[] = [];
  const vistos = new Set<string>();
  const add = (r: Resultado) => {
    const chave = `${r.municipio.slug}|${r.rota.setor ?? ''}|${r.rota.tipo}|${r.rota.dias.join()}|${r.termo}|${r.rua ?? ''}`;
    if (vistos.has(chave)) return;
    vistos.add(chave);
    resultados.push(r);
  };

  for (const municipio of municipios) {
    for (const rota of municipio.rotas) {
      for (const bairro of rota.bairros) {
        if (normalizar(bairro).includes(q)) add({ municipio, rota, termo: bairro });
      }
      if (rota.setor && normalizar(rota.setor).includes(q)) add({ municipio, rota, termo: rota.setor });
    }
    for (const rua of municipio.ruas ?? []) {
      if (!normalizar(rua.rua).includes(q)) continue;
      for (const rota of municipio.rotas.filter((r) => r.setor === rua.setor)) {
        add({ municipio, rota, termo: rua.bairro, rua: rua.rua });
      }
    }
  }
  return resultados.slice(0, limite);
}

export function diaDeHoje(agora: Date = new Date()): Dia {
  return DIAS[agora.getDay()];
}

export function passaNoDia(rota: Rota, dia: Dia): boolean {
  return rota.dias.includes(dia);
}
