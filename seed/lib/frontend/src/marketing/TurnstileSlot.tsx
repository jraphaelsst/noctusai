import { useEffect, useRef } from "react";

const SCRIPT_SRC = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";

interface TurnstileApi {
  render(el: HTMLElement, opts: Record<string, unknown>): string;
  remove(widgetId: string): void;
}
declare global {
  interface Window { turnstile?: TurnstileApi }
}

/** Build-time site key (`VITE_TURNSTILE_SITE_KEY`); empty string when unset. */
export function readTurnstileSiteKey(): string {
  const key = (import.meta as { env?: Record<string, string | undefined> }).env?.VITE_TURNSTILE_SITE_KEY;
  return key?.trim() ?? "";
}

function loadScript(): Promise<void> {
  if (window.turnstile) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(`script[src="${SCRIPT_SRC}"]`);
    const el = existing ?? Object.assign(document.createElement("script"), { src: SCRIPT_SRC, async: true, defer: true });
    el.addEventListener("load", () => resolve(), { once: true });
    el.addEventListener("error", () => reject(new Error("turnstile script failed")), { once: true });
    if (!existing) document.head.appendChild(el);
  });
}

/**
 * Cloudflare Turnstile widget slot.
 *
 * No site key => renders NOTHING and never reports a token. That is the
 * backend's early-dev bypass posture (no secret configured => no verification),
 * and it is not faked here: the form simply sends no `turnstileToken`.
 */
export function TurnstileSlot({ siteKey, onToken }: { siteKey: string; onToken: (token: string | null) => void }) {
  const host = useRef<HTMLDivElement>(null);

  // Mounting a third-party widget is syncing with an external system.
  useEffect(() => {
    if (!siteKey || !host.current) return;
    let widgetId: string | undefined;
    let cancelled = false;
    loadScript()
      .then(() => {
        if (cancelled || !host.current || !window.turnstile) return;
        widgetId = window.turnstile.render(host.current, {
          sitekey: siteKey,
          callback: (t: string) => onToken(t),
          "expired-callback": () => onToken(null),
          "error-callback": () => onToken(null),
        });
      })
      .catch(() => onToken(null));
    return () => {
      cancelled = true;
      if (widgetId && window.turnstile) window.turnstile.remove(widgetId);
    };
  }, [siteKey, onToken]);

  if (!siteKey) return null;
  return <div ref={host} data-testid="turnstile-slot" />;
}
