/**
 * CaptchaCampo — the captcha slot of this product's public forms
 * (`/cadastro`, `/assinar`), driven by the BACKEND's runtime state
 * (`GET /api/planos/publicos` → `captcha`, CONTRACT.md §Planos públicos),
 * never by a build-time env var.
 *
 * Soft-launch captcha-off mode (user decision 2026-10-01):
 * - `desligado` — no Turnstile keys configured: no widget, no copy, Submit
 *   enabled. The backend accepts the form without a token.
 * - `obrigatorio` — render `TurnstileWidget` with the runtime site key;
 *   Submit stays disabled until a token arrives (unchanged behaviour).
 * - `indisponivel` — secret configured but no site key: the form cannot be
 *   submitted at all, so say so plainly ("Cadastro temporariamente
 *   indisponível") instead of a widget that can never load.
 * - `carregando` — state not known yet: Submit disabled, nothing rendered.
 *
 * If the planos query FAILED there is no state to read; the form falls
 * back to `desligado` and the backend stays the authority — a required
 * captcha then answers 403 with its own message, rendered as any error.
 */
import { TurnstileWidget } from "@/components/TurnstileWidget";
import type { CaptchaPublico } from "@/hooks/usePlanosPublicos";

export type EstadoCaptcha = "carregando" | "desligado" | "indisponivel" | "obrigatorio";

export function estadoCaptcha(captcha: CaptchaPublico | null | undefined, carregando: boolean): EstadoCaptcha {
  if (!captcha) return carregando ? "carregando" : "desligado";
  if (!captcha.obrigatorio) return "desligado";
  return captcha.site_key ? "obrigatorio" : "indisponivel";
}

/** Whether the captcha lets the form submit right now. */
export function captchaPermiteEnvio(estado: EstadoCaptcha, token: string): boolean {
  if (estado === "desligado") return true;
  if (estado === "obrigatorio") return token.length > 0;
  return false;
}

export interface CaptchaCampoProps {
  estado: EstadoCaptcha;
  siteKey: string | null | undefined;
  onVerify: (token: string) => void;
  onExpire: () => void;
}

export function CaptchaCampo({ estado, siteKey, onVerify, onExpire }: CaptchaCampoProps) {
  if (estado === "obrigatorio" && siteKey) {
    return <TurnstileWidget siteKey={siteKey} onVerify={onVerify} onExpire={onExpire} />;
  }
  if (estado === "indisponivel") {
    return (
      <p className="text-sm text-destructive" role="status" data-testid="captcha-indisponivel">
        Cadastro temporariamente indisponível. Tente novamente mais tarde.
      </p>
    );
  }
  return null;
}
