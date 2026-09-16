/**
 * Edição de Fotos — capability guards.
 *
 * `GET /capacidades` (contract §2) is the ONLY source of truth for what a
 * caller may do in this feature — the role matrix (contract §1) is resolved
 * server-side from `org_role` + `noctus_users.role` + the `photo_curator`
 * grant, and the FE never re-derives it from SSO metadata (org role, plan,
 * etc.). These are thin, pure guard functions over a `Capacidades` object so
 * every organ (and every product consuming this feature) reads the SAME gate
 * instead of five slightly-different `role === 'owner' || role === 'admin'`
 * checks.
 *
 * 🔴 The AI-verdict gate (`podeVerVeredito`) is the one that matters most:
 * the backend withholds `avaliacao` from `FotoRevisao` by table separation
 * (see `./hooks.ts`) when the caller can't see it — this guard exists so a
 * consumer never has a REASON to reach for `.avaliacao` unconditionally, but
 * it is a UX nicety, not the security boundary (that lives server-side).
 */
import type { Capacidades } from './hooks';

/** `true` only for a fully-loaded `Capacidades` — every guard below defaults closed while it is `undefined`/`null` (still loading, or the query failed). */
function hasCapacidades(c: Capacidades | null | undefined): c is Capacidades {
  return c != null;
}

export function podeCriarLote(capacidades: Capacidades | null | undefined): boolean {
  return hasCapacidades(capacidades) && capacidades.pode_criar_lote;
}

/** Gates rendering the AI verdict (score/recommendation/reason) anywhere in the UI — always `false` for corretores. */
export function podeVerVeredito(capacidades: Capacidades | null | undefined): boolean {
  return hasCapacidades(capacidades) && capacidades.pode_ver_veredito;
}

export function podeGerirPool(capacidades: Capacidades | null | undefined): boolean {
  return hasCapacidades(capacidades) && capacidades.pode_gerir_pool;
}

export function podeAprovarRegras(capacidades: Capacidades | null | undefined): boolean {
  return hasCapacidades(capacidades) && capacidades.pode_aprovar_regras;
}

export function podeAtivarGuia(capacidades: Capacidades | null | undefined): boolean {
  return hasCapacidades(capacidades) && capacidades.pode_ativar_guia;
}

/**
 * Whether Econômico (Batch API) mode can be offered. `false` while
 * `capacidades` is still loading — the caller reads
 * `economicoBloqueadoMotivo` for the reason to show (e.g.
 * `modelo_sem_batch`) once it resolves.
 */
export function economicoDisponivel(capacidades: Capacidades | null | undefined): boolean {
  return hasCapacidades(capacidades) && capacidades.economico_disponivel;
}

export function economicoBloqueadoMotivo(capacidades: Capacidades | null | undefined): string | null {
  return hasCapacidades(capacidades) ? capacidades.economico_bloqueado_motivo : null;
}

/** `null` while loading/unresolved — distinct from `capacidades.dashboard` being genuinely absent for a corretor (who has neither dashboard). */
export function dashboardScope(capacidades: Capacidades | null | undefined): 'org' | 'platform' | null {
  return hasCapacidades(capacidades) ? capacidades.dashboard : null;
}

/** No image-editing model is configured for the org — batch creation is blocked (contract §2, deliberately no platform default). */
export function modeloConfigurado(capacidades: Capacidades | null | undefined): boolean {
  return hasCapacidades(capacidades) && capacidades.modelo_configurado;
}

export function tiposEdicaoAtivos(capacidades: Capacidades | null | undefined): string[] {
  return hasCapacidades(capacidades) ? capacidades.tipos_edicao_ativos : [];
}

export function limiteFotosPorLote(capacidades: Capacidades | null | undefined): number | null {
  return hasCapacidades(capacidades) ? capacidades.limites.fotos_por_lote : null;
}

export function limiteBytesPorFoto(capacidades: Capacidades | null | undefined): number | null {
  return hasCapacidades(capacidades) ? capacidades.limites.bytes_por_foto : null;
}
