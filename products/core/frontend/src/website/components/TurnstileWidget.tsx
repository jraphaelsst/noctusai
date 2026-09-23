/**
 * Cloudflare Turnstile embed for the public website forms (contract §3
 * `POST /api/website/leads`). Adapted from
 * `products/community/frontend/src/pages/checkout/TurnstileWidget.tsx`
 * (community's `/assinar` checkout, the first product to need Turnstile).
 * This is now the SECOND consumer (N=2 — DRY triage, not yet a MUST-
 * formalize per `KB § PATTERNS/architect/project-execution.md`).
 *
 * NOC-REMEDIATE[seed-promotion]: lift to `@noctusai/lib` at the third
 * consumer, or sooner if the tech-lead calls it at N=2.
 *
 * The FE never validates the token — it only obtains one from Cloudflare
 * and forwards it as `turnstile_token`; the backend verifies it against
 * Cloudflare's siteverify endpoint (contract §3, 403 `turnstile_failed`).
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
      <p className="nx-form-error" data-testid="turnstile-unavailable">
        Verificação de segurança indisponível no momento. Você pode tentar enviar mesmo assim.
      </p>
    );
  }

  return <div ref={containerRef} data-testid="turnstile-widget" />;
}
