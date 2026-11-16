/**
 * Library-side fields the platform-wide Biblioteca adds (contract §11.2). These are the additive
 * lines for `PerfilMonitorado` / `ViralDetalhe`; they live here as intersections so FE-1 does not
 * edit `types/geracao.ts` (collision class C6 — FE-2/FE-4 own it). When FE-4 folds them into
 * `geracao.ts` these intersections become redundant (identical props) and can be dropped.
 */
import type { EstruturaRef } from './estruturas'
import type { PerfilMonitorado, ViralDetalhe } from './geracao'

export type PerfilBiblioteca = PerfilMonitorado & {
  /** false = library-only profile (imported, no ingestion). */
  monitorar: boolean
  estruturas_total: number
  /** Present when the list/detail was asked with `marca_id`. */
  selecionado_pela_marca?: boolean
}
/** `GET /biblioteca/perfis` — library-wide, paged (contract §4.2). */
export type PerfisPage = { items: PerfilBiblioteca[]; total: number }

export type ViralDetalheBiblioteca = ViralDetalhe & {
  estruturas?: EstruturaRef[]
  origem_inclusao?: 'sync' | 'link_manual'
}
