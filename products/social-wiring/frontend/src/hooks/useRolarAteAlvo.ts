/**
 * Land on a CONTROL, not just on its screen — the contract readiness list's
 * "Resolver" (`faltando[].destino.alvo`, `contrato_gerador.derivacao.ALVO_*`).
 *
 * Two entry points, one mechanism:
 *   - `rolarAteAlvo(id)` — for an in-dialog jump (switch the card subpage,
 *     then scroll). The target usually is NOT in the DOM yet: the subpage
 *     mounts first and its data arrives after, so this polls briefly for the
 *     element rather than assuming it exists.
 *   - `useRolarAteHash()` — for a routed destino (`/imoveis/X#alvo`). React
 *     Router does not scroll to a hash on navigation, and the page renders its
 *     cards only after its query resolves, so the same poll runs off
 *     `location.hash`.
 *
 * Gives up quietly after `tentativas` — the screen itself is still the right
 * place, the operator just is not scrolled to the field. Never throws.
 */
import { useEffect } from "react";
import { useLocation } from "react-router-dom";

const INTERVALO_MS = 100;

export function rolarAteAlvo(id: string, tentativas = 50): () => void {
  let restantes = tentativas;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const tentar = () => {
    const el = document.getElementById(id);
    if (el) {
      el.scrollIntoView?.({ behavior: "smooth", block: "center" });
      // Focus so a keyboard user lands there too; the targets carry
      // `tabIndex={-1}` for exactly this.
      el.focus?.({ preventScroll: true });
      return;
    }
    restantes -= 1;
    if (restantes > 0) timer = setTimeout(tentar, INTERVALO_MS);
  };
  tentar();
  return () => {
    if (timer) clearTimeout(timer);
  };
}

export function useRolarAteHash(): void {
  const { hash } = useLocation();
  useEffect(() => {
    const id = decodeURIComponent(hash.replace(/^#/, ""));
    if (!id) return;
    return rolarAteAlvo(id);
  }, [hash]);
}
