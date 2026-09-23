/**
 * WebsiteSettings runtime provider.
 *
 * Contract §4: the server injects one
 * `<script id="nx-settings" type="application/json">…</script>` in `<head>`
 * with the PUBLIC settings JSON. The FE reads it SYNCHRONOUSLY on hydrate;
 * when absent (local dev, or the placeholder never got replaced) it falls
 * back to `content/defaults.ts`.
 *
 * To avoid a hydration mismatch, the INITIAL render (both server and first
 * client paint) always uses `defaultSettings` — exactly what the prerender
 * step built the static HTML against. A `useEffect` then reads the injected
 * script and, if it differs, applies it as a normal post-mount state update
 * (never during hydration itself). No `window`/`document` at module scope.
 */
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { defaultSettings } from "../content/defaults";
import type { WebsiteSettings } from "../content/types";

const SettingsContext = createContext<WebsiteSettings>(defaultSettings);

function readInjectedSettings(): WebsiteSettings | null {
  if (typeof document === "undefined") return null;
  const el = document.getElementById("nx-settings");
  if (!el || !el.textContent) return null;
  const text = el.textContent.trim();
  // The placeholder is still literally `__NX_SETTINGS__` in local dev/tests
  // where no server post-processing ran — treat it as "absent", not a parse
  // error.
  if (text === "__NX_SETTINGS__" || text.length === 0) return null;
  try {
    return JSON.parse(text) as WebsiteSettings;
  } catch {
    return null;
  }
}

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<WebsiteSettings>(defaultSettings);

  useEffect(() => {
    const injected = readInjectedSettings();
    if (injected) setSettings(injected);
  }, []);

  return <SettingsContext.Provider value={settings}>{children}</SettingsContext.Provider>;
}

export function useWebsiteSettings(): WebsiteSettings {
  return useContext(SettingsContext);
}
