/**
 * TurnstileWidget — Cloudflare Turnstile embed for the public `/assinar`
 * checkout page (community-m2-contract.md product decision P2).
 *
 * Co-located with `Assinar.tsx` rather than promoted to `@noctusai/lib`:
 * this is the FIRST public form on this product to need Turnstile, so
 * there is no cross-product recurrence yet (N=1). The contract's seam is
 * on the BACKEND side — "put the Protocol+Fake+Real in the seed
 * (`noctusai_lib.integrations`), not in the product" — which is a Python
 * verifier the backend engineer owns; this FE widget is a thin embed of
 * Cloudflare's own script with no seed equivalent to consume. Flagged as a
 * `scoped-improvement:` (promote to `@noctusai/lib` at the second public
 * form that needs a captcha) rather than built shared on day one.
 *
 * The FE never validates the token — it only obtains one from Cloudflare
 * and forwards it as `turnstile_token`. The BACKEND verifies it against
 * Cloudflare's siteverify endpoint before any gateway call (P2). A
 * missing/expired/invalid token still reaches the backend (the Submit
 * button is disabled without a token, but a token can expire between
 * render and submit) — in that case the backend's strict 403
 * `{"detail": "Verificação de segurança falhou. Recarregue a página e
 * tente novamente."}` is rendered like any other backend error via
 * `errorMessage`/`<FormError/>`, never swallowed or replaced by a generic
 * client-side message.
 */
import { useEffect, useRef, useState } from "react";

const SCRIPT_SRC = "https://challenges.cloudflare.com/turnstile/v0/api.js";

declare global {
  interface Window {
    turnstile?: {
      render: (
        container: HTMLElement,
        options: {
          sitekey: string;
          callback: (token: string) => void;
          "expired-callback"?: () => void;
          "error-callback"?: () => void;
        },
      ) => string;
      remove: (widgetId: string) => void;
    };
  }
}

let scriptLoadPromise: Promise<void> | null = null;

function loadTurnstileScript(): Promise<void> {
  if (typeof window === "undefined") return Promise.resolve();
  if (window.turnstile) return Promise.resolve();
  if (scriptLoadPromise) return scriptLoadPromise;
  scriptLoadPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(`script[src="${SCRIPT_SRC}"]`);
    if (existing) {
      existing.addEventListener("load", () => resolve());
      existing.addEventListener("error", () => reject(new Error("turnstile-script-failed")));
      return;
    }
    const script = document.createElement("script");
    script.src = SCRIPT_SRC;
    script.async = true;
    script.defer = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("turnstile-script-failed"));
    document.head.appendChild(script);
  });
  return scriptLoadPromise;
}

export interface TurnstileWidgetProps {
  siteKey: string;
  onVerify: (token: string) => void;
  onExpire?: () => void;
}

/**
 * Renders the Cloudflare Turnstile challenge and calls `onVerify` with the
 * resulting token. Renders a quiet fallback note (no widget) when the
 * script fails to load or no site key is configured — the page still
 * functions with the Submit button disabled (no token available), and any
 * bypass attempt is caught server-side by the 403.
 */
export function TurnstileWidget({ siteKey, onVerify, onExpire }: TurnstileWidgetProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const widgetIdRef = useRef<string | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    if (!siteKey) {
      setLoadFailed(true);
      return;
    }
    let cancelled = false;
    loadTurnstileScript()
      .then(() => {
        if (cancelled || !containerRef.current || !window.turnstile) return;
        widgetIdRef.current = window.turnstile.render(containerRef.current, {
          sitekey: siteKey,
          callback: onVerify,
          "expired-callback": onExpire,
          "error-callback": () => setLoadFailed(true),
        });
      })
      .catch(() => {
        if (!cancelled) setLoadFailed(true);
      });
    return () => {
      cancelled = true;
      if (widgetIdRef.current && window.turnstile) {
        window.turnstile.remove(widgetIdRef.current);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteKey]);

  if (loadFailed) {
    return (
      <p className="text-xs text-muted-foreground" data-testid="turnstile-unavailable">
        Verificação de segurança indisponível no momento. Você pode tentar enviar mesmo assim.
      </p>
    );
  }

  return <div ref={containerRef} data-testid="turnstile-widget" />;
}
