/**
 * Public tier-listing hook — community-m2-contract.md amendment A17.
 *
 * `GET /api/planos/publicos` is a DIFFERENT, narrower endpoint than module
 * 1's authenticated `GET /api/planos` — this was a real contract gap this
 * engineer surfaced (`/assinar` had no public way to list tiers) that the
 * tech-lead closed as A17. `PlanoPublico` is deliberately NOT the `Plano`
 * type from `@/hooks/usePlanos`: the public shape omits `ref_externo`,
 * `membros_ativos`, `entitlements.conteudo_ids`/`grupos_whatsapp`, `ativo`,
 * and timestamps — typing it as `Plano` would invite `/assinar` to read
 * fields the server will never send on this route. `nivel_grupoterapia` +
 * `ordem` were added for the Ninho Vazio tier cards (CONTRACT.md §Planos
 * públicos).
 *
 * The authenticated `/planos` back-office page is UNCHANGED — it keeps
 * consuming `usePlanos` from `@/hooks/usePlanos` (module 1's endpoint).
 */
import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { Ciclo } from "@/hooks/usePlanos";
import type { CheckoutMetodo } from "@/hooks/useCheckout";
import type { NivelGrupoterapia } from "@/hooks/useEu";

/** The four display flags only — never the `conteudo_ids`/`grupos_whatsapp` id lists. */
export interface BeneficiosPublicos {
  feed: boolean;
  forum: boolean;
  chat: boolean;
  eventos: boolean;
}

export interface PlanoPublico {
  id: string;
  nome: string;
  descricao: string | null;
  preco_centavos: number;
  ciclo: Ciclo;
  beneficios: BeneficiosPublicos;
  /** Derived from `plano_gateway_refs` — `[]` means not yet available for
   * any payment method (the page must render it as unavailable, not hide
   * it silently). */
  metodos_disponiveis: CheckoutMetodo[];
  /** What the tier includes of grupoterapia (`entitlements.grupoterapia`). */
  nivel_grupoterapia: NivelGrupoterapia;
  /** Tier order (Gratuito 0 · Ouvinte 1 · Premium 2). */
  ordem: number;
}

/** Tiers in their editorial order (`ordem`, then price) — the order the
 * Landing and the signup show them in. */
export function ordenarPlanosPublicos(planos: PlanoPublico[]): PlanoPublico[] {
  return [...planos].sort((a, b) => a.ordem - b.ordem || a.preco_centavos - b.preco_centavos);
}

/** Whether the public forms need a Turnstile token, and the PUBLIC site
 * key to render the widget with (runtime, from the org key store — not a
 * build arg). `obrigatorio && !site_key` = forms unavailable. */
export interface CaptchaPublico {
  obrigatorio: boolean;
  site_key: string | null;
}

export interface PlanoPublicoListResponse {
  items: PlanoPublico[];
  total: number;
  captcha: CaptchaPublico;
}

/** PUBLIC — no auth, rate-limited server-side. Powers `/assinar`. */
export function usePlanosPublicos() {
  return useQuery({
    queryKey: ["planos-publicos"],
    queryFn: () => api.get<PlanoPublicoListResponse>("/api/planos/publicos"),
  });
}
