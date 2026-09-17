/**
 * Dados cadastrais da imobiliária (migration 100) — the Configurações subtab.
 *
 * The agency's own qualification: razão social, CNPJ, CRECI PJ, address. Every
 * generated instrument needs it twice — once in the header naming who
 * intermediated, once in the corretagem clause naming who is owed the
 * commission.
 *
 * 🔴 NEVER 404s, AND THE FORM IS ALWAYS SAVEABLE.
 * An org that has never opened this tab reads as every field null, not as an
 * error and not as an empty object. The save is a PUT that upserts, so first
 * save and every later one are the same call, and a partly-filled form is
 * accepted — somebody fills this in over several sittings, and refusing it
 * until complete would discard what they had typed.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

export interface DadosImobiliaria {
  razao_social: string | null;
  nome_fantasia: string | null;
  cnpj: string | null;
  /** The brokerage licence. This is the field that keeps these columns
   *  product-local rather than on the shared tenant row — a CRECI means
   *  nothing to the other twelve products on this platform. */
  creci_pj: string | null;
  responsavel_nome: string | null;
  responsavel_creci: string | null;
  telefone: string | null;
  email: string | null;
  endereco_cep: string | null;
  endereco_logradouro: string | null;
  endereco_numero: string | null;
  endereco_complemento: string | null;
  endereco_bairro: string | null;
  endereco_cidade: string | null;
  endereco_uf: string | null;
  // ─── Migration 117 (contract F6) — the office's own operational answers,
  // required by the contract generator (contrato_gerador/derivacao.py) and
  // absent from the UI until this slice — see settings_router.py's
  // `DadosImobiliariaBody` for the exact contract these mirror.
  /** The e-signature platform's name (e.g. "ClickSign"), printed on the
   *  generated instrument's signature clause. */
  plataforma_assinatura_nome: string | null;
  /** The e-signature platform's URL. HTTPS-only — embedded verbatim into a
   *  legal document, so the backend refuses `http://` at the boundary; the
   *  form mirrors that refusal instead of relying on the round-trip. */
  plataforma_assinatura_url: string | null;
  /** R$/day fine for a holdover after the contractual "posse" deadline.
   *  Currency, not a percentage — `>= 0`. */
  posse_multa_diaria: number | null;
  /** Default window (days) a "pendência" gets before it is overdue. `> 0`.
   *  The DB defaults this to 10 for a brand-new row, but a `GET` on an org
   *  that has never saved this tab returns every field as `null` (the
   *  no-row shape), this one included. */
  prazo_pendencias_padrao_dias: number | null;
  updated_at: string | null;
}

export type DadosImobiliariaPatch = Partial<Omit<DadosImobiliaria, "updated_at">>;

const BASE = "/api/settings/imobiliaria";
const KEY = ["sw", "settings", "imobiliaria"] as const;

/**
 * 🔴 TWO loading signals, never `isLoading` and never a bare `isFetching`:
 * `showSkeleton` is true only on the FIRST load (nothing to show yet), and
 * `isRefreshing` is the quiet indicator for a refetch over data that is
 * already on screen — the save mutation re-seeds the cache directly (see
 * `useSalvarDadosImobiliaria`), but a background refetch from elsewhere
 * (tab refocus, another tab's invalidation) must not blank a filled-in
 * form. → KB § PATTERNS/frontend/lying-loading-state.md
 */
export function useDadosImobiliaria() {
  const query = useQuery({
    queryKey: KEY,
    queryFn: () => api.get<DadosImobiliaria>(BASE),
  });
  return {
    ...query,
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

export function useSalvarDadosImobiliaria() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (dados: DadosImobiliariaPatch) =>
      api.put<DadosImobiliaria>(BASE, dados),
    // The server returns the saved row, so seeding the cache with it is
    // exact — no refetch, and no window where the form shows what was typed
    // while the cache still holds what was there before.
    onSuccess: (data) => qc.setQueryData(KEY, data),
  });
}
