/**
 * Types for `/coleta` — the public "calendário de coleta por município".
 *
 * Every fact on that page is TRANSCRIBED from a public source (prefeitura
 * PDF / page, concessionária, press) and carries that source + its date:
 * none of these municipalities publishes a machine-readable schedule
 * (no API, CSV or dados-abertos set — researched 2026-09-29), so the
 * page is only as current as the documents it cites, and says so.
 *
 * Expanding coverage = add a `<slug>.ts` beside this file with its rows
 * and register it in `index.ts`.
 */

export type Dia = 'seg' | 'ter' | 'qua' | 'qui' | 'sex' | 'sab' | 'dom';

export const DIAS: Dia[] = ['dom', 'seg', 'ter', 'qua', 'qui', 'sex', 'sab'];

export const DIA_CURTO: Record<Dia, string> = {
  dom: 'Dom', seg: 'Seg', ter: 'Ter', qua: 'Qua', qui: 'Qui', sex: 'Sex', sab: 'Sáb',
};

export const DIA_LONGO: Record<Dia, string> = {
  dom: 'domingo', seg: 'segunda-feira', ter: 'terça-feira', qua: 'quarta-feira',
  qui: 'quinta-feira', sex: 'sexta-feira', sab: 'sábado',
};

/** `comum` = coleta domiciliar (lixo orgânico/rejeito); `seletiva` = recicláveis. */
export type TipoColeta = 'comum' | 'seletiva';

/** One line of a published schedule: a setor (or bairro group) → days + period. */
export interface Rota {
  /** The source's own sector label ("Setor 24 – Fazendinha (INT)"), when it has one. */
  setor?: string;
  /** Bairros / condomínios / vias exactly as the source names them. */
  bairros: string[];
  /** Empty only when the source gives no weekdays (e.g. just "Diário") — then `frequencia` says so. */
  dias: Dia[];
  /** The source's own frequency wording, shown instead of the weekday strip when `dias` is empty. */
  frequencia?: string;
  /** Period as the source states it ("diurno", "noturno", "manhã/tarde"…); absent when not stated. */
  periodo?: string;
  tipo: TipoColeta;
  /** Source caveat for this line (a typo in the original, a conflicting copy…). */
  nota?: string;
}

/** A street → setor index, for sources that publish street-level lists. */
export interface Rua {
  rua: string;
  bairro: string;
  setor: string;
}

export interface PontoEntrega {
  nome: string;
  endereco: string;
  horario?: string;
  /** What it accepts, as published. */
  aceita?: string;
}

export interface Contato {
  rotulo: string;
  valor: string;
  /** `tel:` / `https://wa.me/` / `mailto:` link when the value is dialable/linkable. */
  href?: string;
}

export interface Fonte {
  titulo: string;
  url: string;
  /** Date of the document itself (ISO `YYYY-MM` or `YYYY-MM-DD`) — not the date we read it; absent when the source is undated. */
  data?: string;
  oficial: boolean;
}

/**
 * How much of the município the page actually covers — shown to the reader,
 * so an incomplete município never looks complete.
 */
export type Cobertura = 'completa' | 'parcial' | 'sem-calendario';

export interface Municipio {
  slug: string;
  nome: string;
  cobertura: Cobertura;
  /** One-paragraph plain-language summary shown at the top of the município. */
  resumo: string;
  operador?: string;
  rotas: Rota[];
  ruas?: Rua[];
  ecopontos: PontoEntrega[];
  /** Other drop-off options (PEVs, cooperativas, cata-bagulho). */
  outros: PontoEntrega[];
  contatos: Contato[];
  /** Known caveats about currency/accuracy — rendered as a visible notice, never hidden. */
  avisos: string[];
  fontes: Fonte[];
}
