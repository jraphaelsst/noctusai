/**
 * A daily-limit 429 points to where the limit is raised (geracao-contract.md §9.4.1): Configurações → Limites
 * diários. Offered only to org owner/admin — the people the PUT accepts; everyone else keeps the plain message.
 */
import { useCallback } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { useEffectiveSSOContext } from "@noctusai/lib/design-system";
import { ROTA_LIMITES_DIARIOS } from "@/hooks/useLimitesGeracao";

export const ROTULO_AJUSTAR_LIMITES = "Ajustar limites";

/** Owner/admin of the effective org: exactly the backend's `require_org_admin_for` roles. */
export function usePodeAjustarLimites(): boolean {
  const ctx = useEffectiveSSOContext();
  return ctx.org.role === "owner" || ctx.org.role === "admin";
}

/** True for an HTTP 429 (the seed `ApiError`, duck-typed so any module instance's error is read). */
export function eLimiteDiario(err: unknown): boolean {
  return (err as { status?: unknown } | null | undefined)?.status === 429;
}

function irParaLimites(): void {
  window.location.assign(ROTA_LIMITES_DIARIOS);
}

/** Inline link under a daily-limit message; renders nothing for someone who cannot raise the limit. */
export function LinkAjustarLimites() {
  const pode = usePodeAjustarLimites();
  if (!pode) return null;
  return (
    <Link to={ROTA_LIMITES_DIARIOS} className="text-sm font-medium underline" data-testid="link-ajustar-limites">
      {ROTULO_AJUSTAR_LIMITES} em Configurações → Limites diários
    </Link>
  );
}

/**
 * `toast.error(mensagem)`, plus an "Ajustar limites" action when `err` is a daily-limit 429 and the user can raise
 * it. Use in place of a bare `toast.error` wherever a generation can hit its daily cap. Router-free on purpose (the
 * headline forms also render outside a router, e.g. in the Esteira dialog's tests): the action is a navigation.
 */
export function useToastErroGeracao(): (mensagem: string, err: unknown) => void {
  const pode = usePodeAjustarLimites();
  return useCallback(
    (mensagem: string, err: unknown) => {
      if (pode && eLimiteDiario(err)) {
        toast.error(mensagem, {
          action: { label: ROTULO_AJUSTAR_LIMITES, onClick: () => irParaLimites() },
        });
      } else {
        toast.error(mensagem);
      }
    },
    [pode],
  );
}
